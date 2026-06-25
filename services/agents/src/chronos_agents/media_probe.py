"""Media-probe agent — measure stored video clips and extract a poster thumbnail.

The upload path stores a clip binary as-is; its real pixel dimensions, duration, and a poster
frame are unknown unless the client happened to send them. This agent fills that gap with
``ffprobe`` (dimensions + duration) and ``ffmpeg`` (one poster frame → JPEG in the object
store), so the feed/galleries get a real poster and the media-quality guard can decide a
clip's hero eligibility on its **measured width** (chronos_core.domain.media_policy).

It is the first slice of the Creator-Studio render backend: ffmpeg lives in the agents image,
and later transcode/compositing jobs (variants, duet/stitch, green-screen) build on the same
subprocess plumbing. Bounded + best-effort: a probe failure on one clip leaves its row
untouched and never aborts the batch. The worker enqueues it on upload and on the maintenance
tick; ``--all`` sweeps the backlog once.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile

from chronos_core import objectstore
from chronos_core.db import session_scope
from chronos_core.models.media import Media
from sqlalchemy import or_, select, update

log = logging.getLogger("chronos.agents.media_probe")
AGENT = "media-probe"
COMPONENT = "agent:media.probe"

# Cap the poster's longest dimension so a 4K phone frame doesn't become a multi-MB thumbnail.
POSTER_MAX_WIDTH = 1280
_PROC_TIMEOUT = 60  # seconds per ffprobe/ffmpeg invocation


def _ffprobe(path: str) -> dict | None:
    """Return ``{width, height, duration_s}`` for the video at ``path`` via ffprobe, or ``None``.

    Only the keys it can determine are included. Honors a rotation tag so a portrait phone clip
    reports portrait dimensions (ffprobe gives the pre-rotation frame size)."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", path],
            capture_output=True, timeout=_PROC_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    try:
        meta = json.loads(proc.stdout)
    except ValueError:
        return None
    vstream = next(
        (s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None
    )
    if vstream is None:
        return None
    w = int(vstream.get("width") or 0) or None
    h = int(vstream.get("height") or 0) or None
    # A 90/270° rotation tag means the displayed frame is the transpose of the coded frame.
    rotate = str((vstream.get("tags") or {}).get("rotate") or "").lstrip("-")
    if rotate in ("90", "270") and w and h:
        w, h = h, w
    out: dict = {}
    if w:
        out["width"] = w
    if h:
        out["height"] = h
    dur = meta.get("format", {}).get("duration")
    if dur:
        try:
            out["duration_s"] = int(float(dur))
        except ValueError:
            pass
    return out or None


def _ffposter(path: str) -> bytes | None:
    """Extract a single poster frame as JPEG bytes via ffmpeg (seek ~1s, fall back to frame 0
    for very short clips). Scaled down to [POSTER_MAX_WIDTH]. ``None`` if extraction fails."""
    for seek in ("1", "0"):
        try:
            proc = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-ss", seek, "-i", path,
                 "-frames:v", "1", "-vf", f"scale=min({POSTER_MAX_WIDTH}\\,iw):-2",
                 "-q:v", "3", "-c:v", "mjpeg", "-f", "image2pipe", "-"],
                capture_output=True, timeout=_PROC_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    return None


def _probe_blob(data: bytes) -> dict:
    """Write ``data`` to a temp file and run ffprobe + ffmpeg against it. Returns a dict with any
    of ``width/height/duration_s`` plus ``poster`` (raw JPEG bytes) that could be determined."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        out: dict = _ffprobe(path) or {}
        poster = _ffposter(path)
        if poster:
            out["poster"] = poster
        return out
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


async def _probe_one(media_id, storage_key: str) -> dict | None:
    """Probe one stored clip: pull the binary, measure it, store its poster, and return the
    DB fields to persist (``width/height/duration_s/thumbnail_key``). Heavy work runs off the
    event loop. ``None`` when nothing could be determined."""
    raw = await asyncio.to_thread(objectstore.get_bytes, storage_key)
    if not raw:
        return None
    probed = await asyncio.to_thread(_probe_blob, raw)
    fields = {k: probed[k] for k in ("width", "height", "duration_s") if probed.get(k) is not None}
    poster = probed.get("poster")
    if poster:
        poster_key = f"posters/{media_id}.jpg"
        await asyncio.to_thread(
            objectstore.put_bytes, poster_key, poster, content_type="image/jpeg"
        )
        fields["thumbnail_key"] = poster_key
    return fields or None


async def probe_pending(*, batch: int = 50, full: bool = False) -> dict:
    """Probe stored video clips that still lack measured dimensions, duration, or a poster.

    Idempotent: each clip is selected only while a field is missing, so reruns are cheap and a
    transient failure is retried next tick. ``full`` sweeps the whole backlog at once.
    """
    totals = {"scanned": 0, "probed": 0, "poster": 0, "failed": 0}
    limit = 1_000_000 if full else batch

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Media.id, Media.storage_key)
                .where(
                    Media.kind == "video",
                    Media.status == "stored",
                    Media.storage_key.is_not(None),
                    or_(
                        Media.width.is_(None),
                        Media.height.is_(None),
                        Media.duration_s.is_(None),
                        Media.thumbnail_key.is_(None),
                    ),
                )
                .limit(limit)
            )
        ).all()

    for media_id, storage_key in rows:
        totals["scanned"] += 1
        try:
            fields = await _probe_one(media_id, storage_key)
        except Exception:  # noqa: BLE001 - one bad clip must never abort the batch
            log.warning("media-probe failed for %s", media_id, exc_info=True)
            totals["failed"] += 1
            continue
        if not fields:
            totals["failed"] += 1
            continue
        async with session_scope() as session:
            await session.execute(update(Media).where(Media.id == media_id).values(**fields))
        totals["probed"] += 1
        if fields.get("thumbnail_key"):
            totals["poster"] += 1

    log.info("media-probe done: %s", totals)
    return totals
