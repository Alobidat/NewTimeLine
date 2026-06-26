"""Media-transcode agent — give every stored clip a web-playable mp4 variant.

Source clips arrive in whatever the uploader had (mov/quicktime, webm/VP9, oversized 4K, …),
which doesn't play uniformly across browsers. This agent ensures each stored video has one
``web`` rendition in [MediaVariant]: an H.264/AAC mp4 capped at [MAX_WIDTH], with ``+faststart``
so it streams immediately. A clip that's *already* web-safe gets a **passthrough** variant row
pointing at its original key (no re-encode, no extra storage) so it's evaluated exactly once.

The media router prefers the ``web`` variant when serving ``/media/{id}/raw``. Builds on the
same ffmpeg plumbing as the media-probe agent; bounded + best-effort + idempotent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile

import httpx
from chronos_core import objectstore
from chronos_core.db import session_scope
from chronos_core.models.media import Media, MediaVariant
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

log = logging.getLogger("chronos.agents.media_transcode")
AGENT = "media-transcode"
COMPONENT = "agent:media.transcode"

WEB = "web"  # the default web-safe rendition label
MAX_WIDTH = 1280  # cap the long edge so a 4K source doesn't ship 4K to phones
WEB_SAFE_CODECS = {"h264"}
WEB_SAFE_MIME = {"video/mp4"}
# Even an h264/mp4 source is re-encoded when it's this large: a high-bitrate original (e.g. a
# 175 MB clip) is slow to start on a phone AND the API serves /raw by loading the whole object
# into memory per range request. Re-encoding at the cap shrinks it to a streamable size.
_MAX_PASSTHROUGH_BYTES = 16 * 1024 * 1024
_PROBE_TIMEOUT = 60
_TRANSCODE_TIMEOUT = 600  # a re-encode can take a while; the worker runs one job at a time

# Dispositions whose external source we may rehost locally (capture-first, ADR-0018). "link"
# media is link-only (licensing) and stays proxied at play time — never downloaded here.
_LOCALIZABLE = ("pin", "archive")
# Polite UA so Wikimedia upload hosts serve the download rather than 403/429 a bare client.
_UA = "ChronosBot/0.1 (+https://github.com/Alobidat/NewTimeLine) media-transcode"
# Cap the source download so one pathological 4K original can't exhaust the worker's memory.
_SOURCE_MAX_BYTES = 600 * 1024 * 1024


async def _fetch_source(url: str | None) -> bytes | None:
    """Download an external clip's bytes (one sequential GET, polite UA) so we can transcode it
    into a local web variant — instead of hot-linking the origin at play time, which Wikimedia
    rate-limits (429 → the clip never plays). Best-effort: any failure leaves the clip proxied."""
    if not url:
        return None
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=httpx.Timeout(60.0, read=120.0)
        ) as client:
            resp = await client.get(url, headers={"User-Agent": _UA})
            resp.raise_for_status()
            data = resp.content
    except Exception:  # noqa: BLE001 - network/HTTP failure → leave for a later retry
        log.warning("media-transcode: source fetch failed for %s", url, exc_info=True)
        return None
    if len(data) > _SOURCE_MAX_BYTES:
        log.info("media-transcode: source too large (%d bytes); skipping %s", len(data), url)
        return None
    return data


def _probe_codec_dims(path: str) -> tuple[str | None, int | None, int | None]:
    """Return ``(codec_name, width, height)`` of the first video stream via ffprobe."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True, timeout=_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None, None
    if proc.returncode != 0 or not proc.stdout:
        return None, None, None
    try:
        meta = json.loads(proc.stdout)
    except ValueError:
        return None, None, None
    vstream = next(
        (s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if vstream is None:
        return None, None, None
    w = int(vstream.get("width") or 0) or None
    h = int(vstream.get("height") or 0) or None
    return vstream.get("codec_name"), w, h


def _needs_transcode(mime: str | None, codec: str | None, width: int | None) -> bool:
    """Whether a clip must be re-encoded: not H.264, not an mp4 container, or wider than the cap."""
    if codec not in WEB_SAFE_CODECS:
        return True
    if (mime or "") not in WEB_SAFE_MIME:
        return True
    return bool(width and width > MAX_WIDTH)


def _build_ffmpeg_args(in_path: str, out_path: str, edit: dict | None = None) -> list[str]:
    """Assemble the ffmpeg command for the web mp4, applying an optional Creator-Studio edit
    (trim window + speed). Trim uses fast input-seek (``-ss`` before ``-i``) plus a ``-t``
    duration; speed retimes video (``setpts``) and audio (``atempo``). Pure string-building, so
    it's unit-tested without invoking ffmpeg."""
    edit = edit or {}
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y"]

    trim_start = edit.get("trim_start")
    trim_end = edit.get("trim_end")
    if trim_start:
        args += ["-ss", f"{float(trim_start):.3f}"]  # input seek = fast; re-encode keeps it exact
    args += ["-i", in_path]
    if trim_end is not None:
        duration = float(trim_end) - float(trim_start or 0.0)
        if duration > 0:
            args += ["-t", f"{duration:.3f}"]

    speed = float(edit["speed"]) if edit.get("speed") else 1.0
    vfilters = [f"scale=min({MAX_WIDTH}\\,iw):-2"]
    if speed != 1.0:
        vfilters.append(f"setpts={1.0 / speed:.6f}*PTS")
    args += ["-vf", ",".join(vfilters)]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if speed != 1.0:
        args += ["-af", f"atempo={speed:.3f}"]  # atempo handles 0.5–2.0 in one pass (media_edit)
    args += ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
    return args


def _transcode_mp4(
    in_path: str, *, edit: dict | None = None
) -> tuple[bytes, int | None, int | None] | None:
    """Re-encode the clip at ``in_path`` to a web mp4. Returns ``(bytes, width, height)`` or None.

    mp4 ``+faststart`` rewrites the moov atom to the front, so the output must be a seekable
    file (not a stdout pipe); we read it back and delete it."""
    out_path = in_path + ".web.mp4"
    try:
        proc = subprocess.run(
            _build_ffmpeg_args(in_path, out_path, edit),
            capture_output=True, timeout=_TRANSCODE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        if proc.returncode != 0 or not os.path.exists(out_path):
            return None
        with open(out_path, "rb") as fh:
            data = fh.read()
        _, w, h = _probe_codec_dims(out_path)
        return data, w, h
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass


def _evaluate(
    data: bytes, mime: str | None, width: int | None, edit: dict | None = None
) -> dict | None:
    """Decide + produce the web variant for a clip blob (runs off the event loop).

    Returns ``{"mode": "transcoded", "data": bytes, "width", "height"}`` for a re-encode, or
    ``{"mode": "passthrough", "width", "height"}`` when the source is already web-safe. ``None``
    when the clip can't be read at all. An ``edit`` (trim/speed) always forces a re-encode — a
    passthrough can't carry edits."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        codec, w, h = _probe_codec_dims(path)
        if codec is None:
            return None  # unreadable / no video stream → leave for a later retry
        if (
            not edit
            and not _needs_transcode(mime, codec, w)
            and len(data) <= _MAX_PASSTHROUGH_BYTES
        ):
            return {"mode": "passthrough", "width": w, "height": h}
        out = _transcode_mp4(path, edit=edit)
        if out is None:
            return None
        ev_data, ew, eh = out
        return {"mode": "transcoded", "data": ev_data, "width": ew, "height": eh}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def _insert_variant(
    media_id, *, storage_key: str, mime: str | None,
    width: int | None, height: int | None, bytes_len: int | None,
) -> None:
    """Insert the ``web`` variant row, ignoring a duplicate (idempotent re-runs)."""
    async with session_scope() as session:
        await session.execute(
            pg_insert(MediaVariant)
            .values(
                media_id=media_id, rendition=WEB, storage_key=storage_key, mime=mime,
                width=width, height=height, bytes=bytes_len, status="stored",
            )
            .on_conflict_do_nothing(constraint="uq_media_variant_rendition")
        )


async def _process(
    media_id, storage_key: str | None, source_url: str | None,
    mime: str | None, width: int | None, edit: dict | None = None
) -> str | None:
    """Produce + persist the web variant for one clip. Returns ``transcoded`` | ``passthrough``.

    Bytes come from local storage when the clip is already stored, else they're downloaded from
    the external origin (Wikimedia etc.) — so an externally-hosted clip ends up served locally
    and never hot-links at play time."""
    if storage_key:
        raw = await asyncio.to_thread(objectstore.get_bytes, storage_key)
    else:
        raw = await _fetch_source(source_url)
    if not raw:
        return None
    result = await asyncio.to_thread(_evaluate, raw, mime, width, edit)
    if result is None:
        return None
    if result["mode"] == "transcoded":
        variant_key = f"variants/{media_id}/web.mp4"
        await asyncio.to_thread(
            objectstore.put_bytes, variant_key, result["data"], content_type="video/mp4"
        )
        await _insert_variant(
            media_id, storage_key=variant_key, mime="video/mp4",
            width=result["width"], height=result["height"], bytes_len=len(result["data"]),
        )
        return "transcoded"
    # Passthrough: the source already plays on the web. For a locally-stored clip, just point the
    # web variant at the original key (no extra storage). For a downloaded external clip we must
    # still persist the bytes — that's the whole point — so it's served locally, not re-fetched.
    if storage_key:
        variant_key = storage_key
        bytes_len = None
    else:
        variant_key = f"variants/{media_id}/web.mp4"
        await asyncio.to_thread(
            objectstore.put_bytes, variant_key, raw, content_type=mime or "video/mp4"
        )
        bytes_len = len(raw)
    await _insert_variant(
        media_id, storage_key=variant_key, mime=mime or "video/mp4",
        width=result["width"], height=result["height"], bytes_len=bytes_len,
    )
    return "passthrough"


async def transcode_pending(*, batch: int = 20, full: bool = False) -> dict:
    """Give each stored video clip lacking a ``web`` variant one (re-encode or passthrough).

    Bounded + idempotent: only clips without a web variant are selected, so reruns are cheap and
    a transient failure is retried next tick. ``full`` processes the whole backlog at once.
    """
    totals = {"scanned": 0, "transcoded": 0, "passthrough": 0, "failed": 0}
    limit = 1_000_000 if full else batch

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(
                    Media.id, Media.storage_key, Media.source_url, Media.mime,
                    Media.width, Media.edit_spec,
                )
                .where(
                    Media.kind == "video",
                    ~exists().where(
                        MediaVariant.media_id == Media.id, MediaVariant.rendition == WEB
                    ),
                    # Either already stored locally, OR an externally-hosted clip we're allowed
                    # to rehost (pin/archive) — download + transcode the latter so it plays
                    # locally instead of hot-linking the origin (which Wikimedia 429s).
                    or_(
                        and_(Media.status == "stored", Media.storage_key.is_not(None)),
                        and_(
                            Media.disposition.in_(_LOCALIZABLE),
                            Media.source_url.is_not(None),
                        ),
                    ),
                )
                .limit(limit)
            )
        ).all()

    for media_id, storage_key, source_url, mime, width, edit_spec in rows:
        totals["scanned"] += 1
        try:
            outcome = await _process(
                media_id, storage_key, source_url, mime, width, edit_spec
            )
        except Exception:  # noqa: BLE001 - one bad clip must never abort the batch
            log.warning("media-transcode failed for %s", media_id, exc_info=True)
            totals["failed"] += 1
            continue
        if outcome is None:
            totals["failed"] += 1
            continue
        totals[outcome] += 1

    log.info("media-transcode done: %s", totals)
    return totals
