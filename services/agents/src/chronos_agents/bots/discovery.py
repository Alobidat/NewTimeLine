"""Free, license-verified video discovery for AI users.

Given a topic query, returns playable clips whose license is *verified free* (via
:func:`chronos_agents.sources.licensing.is_free_license`) — the only clips a bot is allowed to
post. Providers (each behind an ``bots.sources.<id>.enabled`` toggle):

- **Wikimedia Commons** — keyless; reuses :func:`sources.wikimedia.commons_videos` (CC/PD, license
  read from ``LicenseShortName``). Strong for science/space/nature/history.
- **NASA** Image & Video Library — keyless; agency footage is **public domain**.
- **Pexels** video API — needs ``bots.sources.pexels.api_key``; fixed free Pexels License. The
  breadth source (sports/finance/news/travel/tech B-roll).
- **Internet Archive** — keyless; ``mediatype:movies`` filtered to a *free* ``licenseurl``
  (public-domain / CC0 / CC BY / CC BY-SA). Deep archival breadth (history/news/culture/PD film).
  ``youtube-*`` re-uploads are excluded (uploader-asserted licenses are untrustworthy).
- **Pixabay** video API — needs ``bots.sources.pixabay.api_key``; Pixabay Content License (free,
  commercial-OK, no attribution). A second modern-topic breadth source alongside Pexels.

Every candidate is license-gated; a clip with no recognisably-free license is dropped (fail-
closed). All provider calls are best-effort — a failing provider yields ``[]``, never raises.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx
from chronos_core import config_service
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_agents.sources.licensing import is_free_license, normalize_license
from chronos_agents.sources.wikimedia import USER_AGENT, commons_videos

log = logging.getLogger("chronos.agents.bots.discovery")

_PLAYABLE = {"video/mp4", "video/webm"}


@dataclass(frozen=True)
class FreeClip:
    """One license-verified, browser-playable clip ready to post."""

    url: str             # direct playable file URL (mp4/webm)
    source_url: str      # provenance page (the event's source)
    title: str
    provider: str        # commons | nasa | pexels | archive | pixabay
    license: str         # normalized, verified-free
    mime: str = "video/mp4"
    description: str | None = None
    credit: str | None = None
    width: int | None = None
    height: int | None = None
    duration_s: int | None = None
    year: float | None = None


async def find_free_clips(
    client: httpx.AsyncClient,
    session: AsyncSession,
    query: str,
    *,
    limit: int = 8,
) -> list[FreeClip]:
    """License-verified clips for ``query`` across the enabled free-video providers."""
    allow_nc = bool(await config_service.get(session, "bots.allow_noncommercial", False))
    max_width = int(await config_service.get(session, "agents.media.max_clip_width", 720))
    out: list[FreeClip] = []

    async def enabled(pid: str) -> bool:
        return bool(await config_service.get(session, f"bots.sources.{pid}.enabled", True))

    if await enabled("commons"):
        out += await _commons(client, query, limit=limit, max_width=max_width, allow_nc=allow_nc)
    if len(out) < limit and await enabled("nasa"):
        out += await _nasa(client, query, limit=limit - len(out))
    if len(out) < limit and await enabled("archive"):
        out += await _archive(client, query, limit=limit - len(out), allow_nc=allow_nc)
    if len(out) < limit and await enabled("pexels"):
        key = await config_service.get(session, "bots.sources.pexels.api_key", "")
        if key:
            out += await _pexels(client, query, key, limit=limit - len(out), max_width=max_width)
    if len(out) < limit and await enabled("pixabay"):
        key = await config_service.get(session, "bots.sources.pixabay.api_key", "")
        if key:
            out += await _pixabay(client, query, key, limit=limit - len(out), max_width=max_width)

    # Dedup by direct url, cap.
    seen: set[str] = set()
    deduped: list[FreeClip] = []
    for c in out:
        if c.url in seen:
            continue
        seen.add(c.url)
        deduped.append(c)
    return deduped[:limit]


async def _commons(
    client: httpx.AsyncClient, query: str, *, limit: int, max_width: int, allow_nc: bool
) -> list[FreeClip]:
    vids = await commons_videos(client, query, limit=limit * 2, max_width=max_width)
    out: list[FreeClip] = []
    for v in vids:
        if not is_free_license(v.license, allow_noncommercial=allow_nc):
            continue
        out.append(
            FreeClip(
                url=v.url, source_url=v.page_url, title=v.title, provider="commons",
                license=normalize_license(v.license) or "CC", mime=v.mime,
                description=v.description, credit=v.credit, width=v.width, height=v.height,
                duration_s=v.duration_s, year=v.year,
            )
        )
        if len(out) >= limit:
            break
    return out


async def _nasa(client: httpx.AsyncClient, query: str, *, limit: int) -> list[FreeClip]:
    """NASA Image & Video Library — agency footage is public domain (keyless)."""
    try:
        resp = await client.get(
            "https://images-api.nasa.gov/search",
            params={"q": query, "media_type": "video"}, timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        items = resp.json().get("collection", {}).get("items", [])
    except Exception:
        log.warning("nasa search failed for %r", query, exc_info=True)
        return []

    out: list[FreeClip] = []
    for item in items[: limit * 2]:
        data = (item.get("data") or [{}])[0]
        nasa_id = data.get("nasa_id")
        href = item.get("href")  # collection.json listing the asset files
        if not nasa_id or not href:
            continue
        mp4 = await _nasa_asset_mp4(client, href)
        if not mp4:
            continue
        out.append(
            FreeClip(
                url=mp4, source_url=f"https://images.nasa.gov/details-{nasa_id}",
                title=(data.get("title") or nasa_id)[:140], provider="nasa",
                license="Public Domain (NASA)", mime="video/mp4",
                description=data.get("description"), credit=data.get("center") or "NASA",
            )
        )
        if len(out) >= limit:
            break
    return out


async def _nasa_asset_mp4(client: httpx.AsyncClient, collection_href: str) -> str | None:
    """Resolve a NASA item's playable mp4 from its asset collection.json (best-effort)."""
    try:
        resp = await client.get(collection_href, timeout=15.0, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        files = resp.json()
    except Exception:
        return None
    if not isinstance(files, list):
        return None
    mp4s = [f for f in files if isinstance(f, str) and f.lower().split("?")[0].endswith(".mp4")]
    if not mp4s:
        return None
    # Prefer a mid/mobile rendition over the huge "orig" master.
    for tag in ("~mobile.mp4", "~small.mp4", "~medium.mp4"):
        for f in mp4s:
            if f.endswith(tag):
                return _https(f)
    return _https(mp4s[0])


async def _pexels(
    client: httpx.AsyncClient, query: str, key: str, *, limit: int, max_width: int
) -> list[FreeClip]:
    """Pexels video API — fixed free Pexels License (needs an API key)."""
    try:
        resp = await client.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "per_page": min(limit * 2, 30)},
            headers={"Authorization": key}, timeout=20.0,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
    except Exception:
        log.warning("pexels search failed for %r", query, exc_info=True)
        return []

    out: list[FreeClip] = []
    for v in videos:
        best = _pexels_best_file(v.get("video_files") or [], max_width)
        if not best:
            continue
        out.append(
            FreeClip(
                url=best["link"], source_url=v.get("url") or best["link"],
                title=(_pexels_title(v.get("url")) or query)[:140],
                provider="pexels", license="Pexels License (free)", mime="video/mp4",
                credit=(v.get("user") or {}).get("name") or "Pexels",
                width=best.get("width"), height=best.get("height"), duration_s=v.get("duration"),
            )
        )
        if len(out) >= limit:
            break
    return out


def _pexels_best_file(files: list[dict], max_width: int) -> dict | None:
    """Largest mp4 rendition at or under ``max_width`` (else the smallest available)."""
    mp4s = [f for f in files if (f.get("file_type") == "video/mp4") and f.get("link")]
    if not mp4s:
        return None
    under = [f for f in mp4s if 0 < (f.get("width") or 0) <= max_width]
    pool = under or mp4s
    return max(pool, key=lambda f: f.get("width") or 0) if under else min(
        pool, key=lambda f: f.get("width") or 1 << 30
    )


def _pexels_title(page_url: str | None) -> str | None:
    """Derive a readable title from a Pexels video page URL slug."""
    if not page_url:
        return None
    slug = page_url.rstrip("/").split("/")[-1]
    return slug.replace("-", " ").strip() or None


# --- Internet Archive (keyless) -------------------------------------------------------------

# Only request movies whose licenseurl is recognisably free (PD / CC0 / CC BY / CC BY-SA); the
# is_free_license gate below is still authoritative (defence in depth). ``youtube-*`` items are
# user re-uploads with uploader-asserted licenses we don't trust.
_IA_FREE_Q = (
    r"licenseurl:*publicdomain* OR licenseurl:*\/licenses\/by\/* "
    r"OR licenseurl:*\/licenses\/by-sa\/*"
)


async def _archive(
    client: httpx.AsyncClient, query: str, *, limit: int, allow_nc: bool
) -> list[FreeClip]:
    """Internet Archive movies under a free license (keyless). Resolves a direct mp4 per item."""
    # Scope the topic match to title/subject/description (full-text matching is too noisy for
    # relevance) and let IA's default relevance sort rank. The LLM gate in post.py is the final
    # relevance arbiter; this just keeps the candidate set on-topic enough to be worth judging.
    topic = f"(title:({query}) OR subject:({query}) OR description:({query}))"
    params = [
        ("q", f"mediatype:movies AND ({_IA_FREE_Q}) AND NOT identifier:youtube-* AND {topic}"),
        ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "licenseurl"),
        ("fl[]", "year"), ("fl[]", "creator"), ("fl[]", "description"),
        ("rows", str(limit * 3)), ("output", "json"),
    ]
    try:
        resp = await client.get(
            "https://archive.org/advancedsearch.php", params=params, timeout=20.0,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        docs = (resp.json().get("response") or {}).get("docs") or []
    except Exception:
        log.warning("archive.org search failed for %r", query, exc_info=True)
        return []

    out: list[FreeClip] = []
    for doc in docs:
        identifier = doc.get("identifier")
        lic = _ia_license(doc.get("licenseurl"))
        if not identifier or not is_free_license(lic, allow_noncommercial=allow_nc):
            continue
        picked = await _ia_mp4(client, identifier)
        if not picked:
            continue
        name, width, height = picked
        out.append(
            FreeClip(
                url=f"https://archive.org/download/{identifier}/{name}",
                source_url=f"https://archive.org/details/{identifier}",
                title=str(doc.get("title") or identifier)[:140], provider="archive",
                license=normalize_license(lic) or "Public Domain", mime="video/mp4",
                description=_ia_text(doc.get("description")),
                credit=_ia_text(doc.get("creator")) or "Internet Archive",
                width=width, height=height, year=_ia_year(doc.get("year")),
            )
        )
        if len(out) >= limit:
            break
    return out


async def _ia_mp4(
    client: httpx.AsyncClient, identifier: str
) -> tuple[str, int | None, int | None] | None:
    """Pick the smallest .mp4 rendition (the web derivative) from an item's file list."""
    try:
        resp = await client.get(
            f"https://archive.org/metadata/{identifier}", timeout=15.0,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        files = resp.json().get("files") or []
    except Exception:
        return None
    mp4s = [f for f in files if str(f.get("name", "")).lower().endswith(".mp4")]
    if not mp4s:
        return None

    def _size(f: dict) -> int:
        try:
            return int(f.get("size") or 0)
        except (TypeError, ValueError):
            return 0

    sized = [f for f in mp4s if _size(f) > 0]
    best = min(sized or mp4s, key=lambda f: _size(f) or 1 << 62)
    return best["name"], _ia_int(best.get("width")), _ia_int(best.get("height"))


def _ia_license(licenseurl: str | None) -> str | None:
    """Map an Internet Archive ``licenseurl`` to a license string is_free_license understands."""
    u = (licenseurl or "").lower()
    if not u:
        return None
    if "publicdomain/zero" in u or "/zero/" in u:
        return "CC0"
    if "publicdomain" in u:
        return "Public Domain"
    m = re.search(r"/licenses/([a-z-]+)/(\d(?:\.\d)?)", u)
    if m:
        return f"CC {m.group(1).upper()} {m.group(2)}"
    return licenseurl


def _ia_year(raw) -> float | None:
    m = re.search(r"-?\d{1,4}", str(raw or ""))
    return float(m.group()) if m else None


def _ia_int(raw) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _ia_text(raw) -> str | None:
    """IA fields may be a str or a list of strs; join to one short string."""
    if isinstance(raw, list):
        raw = "; ".join(str(x) for x in raw if x)
    text = str(raw).strip() if raw else ""
    return text[:500] or None


# --- Pixabay (keyed) ------------------------------------------------------------------------


async def _pixabay(
    client: httpx.AsyncClient, query: str, key: str, *, limit: int, max_width: int
) -> list[FreeClip]:
    """Pixabay video API — Pixabay Content License (free, commercial-OK; needs an API key)."""
    try:
        resp = await client.get(
            "https://pixabay.com/api/videos/",
            params={"key": key, "q": query, "per_page": min(max(limit * 2, 3), 50),
                    "safesearch": "true"},
            timeout=20.0,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except Exception:
        log.warning("pixabay search failed for %r", query, exc_info=True)
        return []

    out: list[FreeClip] = []
    for v in hits:
        best = _pixabay_best_file(v.get("videos") or {}, max_width)
        if not best or not best.get("url"):
            continue
        tags = str(v.get("tags") or query)
        out.append(
            FreeClip(
                url=best["url"], source_url=v.get("pageURL") or best["url"],
                title=tags[:140], provider="pixabay", license="Pixabay License (free)",
                mime="video/mp4", credit=v.get("user") or "Pixabay",
                width=best.get("width") or None, height=best.get("height") or None,
                duration_s=v.get("duration"),
            )
        )
        if len(out) >= limit:
            break
    return out


def _pixabay_best_file(videos: dict, max_width: int) -> dict | None:
    """Largest Pixabay rendition at or under ``max_width`` (else the smallest available)."""
    files = [f for f in videos.values() if isinstance(f, dict) and f.get("url")]
    if not files:
        return None
    under = [f for f in files if 0 < (f.get("width") or 0) <= max_width]
    if under:
        return max(under, key=lambda f: f.get("width") or 0)
    return min(files, key=lambda f: f.get("width") or 1 << 30)


def _https(url: str) -> str:
    return ("https:" + url) if url.startswith("//") else url
