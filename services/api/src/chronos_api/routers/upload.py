"""User-generated video event upload (ADR-0029, social-and-feed §3).

    POST /upload   (multipart/form-data)
      file:        the video binary (required)
      title:       str (required)
      t_start:     float signed year (required — the ADR-0020 *time* invariant)
      actors:      str, comma/newline-separated names (required — *actors*)
      locations:   str, comma/newline-separated place names (required — *location*) ...
      geo_label / lat / lon: optional explicit coordinates (resolved via the cascade otherwise)
      links:       str, comma-separated event uuids the clip relates to (required — *link(s)*)
      summary / time_precision / duration_s / width / height: optional metadata

Write-gated (``require_verified_actor``). The binary is stored in the object store; we then
create the hero ``media`` + a ``pending`` event, tag actors/location, record the user links,
and **enqueue the geocode cascade** (ADR-0020) so the event gets a map location even when no
explicit coordinates were given. Missing time/location/actors/links → **400**. Size/type are
bounded by config (``upload.max_bytes`` / ``upload.allowed_mime``).
"""

from __future__ import annotations

import logging
import uuid

import httpx
import redis as redislib
from chronos_core import config_service, objectstore, run_queue, upload as upload_core
from chronos_core.models.user import User
from chronos_core.run_queue import push_job
from chronos_core.schemas.event import GeoPoint
from chronos_core.schemas.privacy import PrivacySettings
from chronos_core.settings import get_settings
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.auth_stub import require_verified_actor
from chronos_api.deps import get_session

log = logging.getLogger("chronos.api.upload")

router = APIRouter(prefix="/upload", tags=["upload"])

_DEFAULT_MAX_BYTES = 209_715_200  # 200 MB
_DEFAULT_ALLOWED = ["video/mp4", "video/webm", "video/quicktime", "video/ogg"]


def _split(raw: str | None) -> list[str]:
    """Split a comma/newline-separated form field into trimmed, non-empty tokens."""
    if not raw:
        return []
    parts = raw.replace("\n", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def _parse_uuids(tokens: list[str]) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for tok in tokens:
        try:
            out.append(uuid.UUID(tok))
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"invalid event id in links: {tok!r}"
            ) from exc
    return out


def _enqueue_geocode() -> None:
    """Run the ADR-0020 geocode cascade for the freshly-created event (fire-and-forget)."""
    try:
        r = redislib.from_url(get_settings().redis_url)
        try:
            push_job(r, "geocode", {})
        finally:
            r.close()
    except Exception:  # noqa: BLE001 - never fail an upload because the queue is down
        log.warning("upload: failed to enqueue geocode job", exc_info=True)


async def _fetch_source(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Download a clip from an external [url] (the no-file-picker path used by web clients).

    Returns ``(bytes, mime)``; raises a 4xx/5xx ``HTTPException`` on a bad URL, an oversize
    body, or a transport error so the caller surfaces it like any other upload failure.
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as c:
            resp = await c.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"could not fetch source_url: {exc}"
        ) from exc
    data = resp.content
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"source exceeds the {max_bytes}-byte limit",
        )
    mime = (resp.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()
    return data, mime


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile | None = File(default=None),
    source_url: str | None = Form(default=None),
    title: str = Form(...),
    t_start: float | None = Form(default=None),
    actors: str | None = Form(default=None),
    locations: str | None = Form(default=None),
    links: str | None = Form(default=None),
    summary: str | None = Form(default=None),
    geo_label: str | None = Form(default=None),
    lat: float | None = Form(default=None),
    lon: float | None = Form(default=None),
    time_precision: str | None = Form(default=None),
    duration_s: int | None = Form(default=None),
    width: int | None = Form(default=None),
    height: int | None = Form(default=None),
    category: str | None = Form(default=None),
    audience: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    actor: uuid.UUID = Depends(require_verified_actor),
) -> dict:
    """Upload a video clip + metadata → an auto-published user video event at the chosen
    audience (default = the user's ``default_post_audience`` privacy setting)."""
    # --- required-metadata enforcement (ADR-0020 every-event invariant) ---------------
    if not title.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "title is required")
    if t_start is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "time (t_start) is required")
    actor_names = _split(actors)
    if not actor_names:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "at least one actor is required")
    location_names = _split(locations)
    has_location = bool(location_names or geo_label or (lat is not None and lon is not None))
    if not has_location:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "a location (place name, geo_label, or lat/lon) is required"
        )
    link_ids = _parse_uuids(_split(links))
    if not link_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "at least one linked event id is required"
        )

    # --- the clip binary: an uploaded file, or an external source_url (no-picker path) ---
    max_bytes = int(await config_service.get(session, "upload.max_bytes", _DEFAULT_MAX_BYTES))
    allowed = await config_service.get(session, "upload.allowed_mime", _DEFAULT_ALLOWED)
    if file is not None:
        data = await file.read()
        mime = file.content_type or "application/octet-stream"
    elif source_url and source_url.strip():
        data, mime = await _fetch_source(source_url.strip(), max_bytes)
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "a clip file or source_url is required"
        )

    # --- size / type limits (config-tunable) ------------------------------------------
    if allowed and mime not in allowed:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"unsupported content type: {mime}"
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty upload")
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file exceeds the {max_bytes}-byte limit",
        )

    # --- store the binary in the object store -----------------------------------------
    ext = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov",
           "video/ogg": "ogv"}.get(mime, "bin")
    storage_key = f"uploads/{actor}/{uuid.uuid4().hex}.{ext}"
    try:
        objectstore.put_bytes(storage_key, data, content_type=mime)
    except Exception as exc:  # noqa: BLE001
        log.exception("upload: object-store write failed")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "media store unavailable"
        ) from exc

    geo = GeoPoint(lon=lon, lat=lat) if (lat is not None and lon is not None) else None

    # Resolve the post audience: explicit form value, else the user's default_post_audience.
    chosen_audience = (audience or "").strip().lower()
    if chosen_audience not in ("public", "followers", "friends"):
        user = await session.get(User, actor)
        privacy = PrivacySettings.from_prefs(user.prefs if user else None)
        chosen_audience = privacy.default_post_audience

    event = await upload_core.create_video_event(
        session,
        user_id=actor,
        title=title.strip(),
        summary=summary,
        t_start=t_start,
        time_precision=time_precision,
        storage_key=storage_key,
        mime=mime,
        bytes_len=len(data),
        geo=geo,
        geo_label=geo_label,
        actor_names=actor_names,
        location_names=location_names,
        link_event_ids=link_ids,
        duration_s=duration_s,
        width=width,
        height=height,
        category=category,
        visibility=chosen_audience,
    )
    await session.flush()

    # Resolve a map location via the ADR-0020 cascade (skip if explicit coords supplied). The
    # event is published immediately, so the geocode agent picks it up right away.
    if geo is None:
        _enqueue_geocode()
    # Async LLM moderation pass (Phase 6) — fire-and-forget; flags land in the admin queue.
    run_queue.enqueue("moderate-event", {"event_id": str(event.id)})

    return {
        "event_id": str(event.id),
        "status": event.status.value if hasattr(event.status, "value") else str(event.status),
        "visibility": (
            event.visibility.value if hasattr(event.visibility, "value")
            else str(event.visibility)
        ),
    }
