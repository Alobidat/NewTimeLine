"""Media archival policy (pure, no I/O) — decide whether to **store a media binary
locally** or merely **link** to it, and when a stored copy may be released.

Why this exists (ADR-0018): media attached to hot/sensitive events tends to **disappear**
from its origin under political, government, or social pressure. The system must capture
such media locally *before* it vanishes, while not wasting storage on media that lives on
stable, durable hosts. The decision is re-evaluated over time as availability is observed.

Three dispositions:
- ``pin``     — store locally, **never auto-release** (high takedown risk; external
  availability is never sufficient confidence because pressure can remove all copies).
- ``archive`` — store locally **now**, eligible for release later **iff** it proves durable
  (hot topics, ephemeral origins). "Capture first, decide retention later."
- ``link``    — reference only (low sensitivity + already on a durable, corroborated host).

All scores are 0–100. Thresholds are module defaults; workers may override from config.
"""

from __future__ import annotations

# Clips-first / no-text-only policy (ADR-0023, event-presentation.md §4). Media kinds that
# count as a "clip" — the format we most prefer. Images are the floor; an event with neither
# image nor clip is "text-only" and held back / flagged for media acquisition.
CLIP_KINDS = {"video"}


def has_required_media(image_count: int, clip_count: int) -> bool:
    """Whether an event meets the clips-first floor: **at least one image** (ADR-0023).

    Clips are preferred but optional; an image is the minimum so no event is text-only.
    Pure — callers pass counts of image-kind and clip-kind ``event_media``.
    """
    return image_count >= 1


# The hero resolution floor (ADR-0024): an image narrower than this reads as a thumbnail and
# must never be an event's hero. Single source of truth — feed, attach, and the quality guard
# all use this (config ``agents.media.min_image_width`` can override). Below GALLERY_MIN_WIDTH
# an image is an icon/placeholder and is dropped entirely.
MIN_IMAGE_WIDTH = 640
GALLERY_MIN_WIDTH = 200
# A clip narrower than this (when its width is known) is too low-res to be the hero.
MIN_CLIP_WIDTH = 240


def is_decent_image(width: int | None, *, min_width: int = GALLERY_MIN_WIDTH) -> bool:
    """Whether an image is large enough to keep at all (not an icon/placeholder) — the
    **gallery** floor. Unknown width passes here (galleries tolerate not-yet-measured images);
    a *known* width below ``min_width`` is dropped.
    """
    return width is None or width >= min_width


def hero_eligible(
    kind: str,
    width: int | None,
    *,
    min_width: int = MIN_IMAGE_WIDTH,
    min_clip_width: int = MIN_CLIP_WIDTH,
) -> bool:
    """Whether a media item may be an event's **hero** (ADR-0024 quality floor).

    A clip is eligible (only a *known* sub-floor clip width is rejected). An image is eligible
    only when its width is **measured and ≥ ``min_width``** — an unmeasured or tiny image is
    never promoted to hero (the gap that let RSS thumbnails through). The media-quality guard
    measures unknown widths so eligibility can be decided.
    """
    if kind in CLIP_KINDS:
        return width is None or width >= min_clip_width
    return width is not None and width >= min_width


def media_role_rank(kind: str, index: int, *, prefer_clips: bool = True) -> tuple[str, int]:
    """Pick the ``(role, rank)`` for one media item so a **clip is the hero** when present.

    ``index`` is the item's position within its own kind (0 = first clip / first image).
    With ``prefer_clips`` (ADR-0024), the first video becomes the ``hero`` and ranks ahead
    of images; the first image is the hero only when there's no clip. Pure — the caller
    decides ordering by passing kinds in clip-first order.
    """
    is_clip = kind in CLIP_KINDS
    if prefer_clips and is_clip and index == 0:
        return ("hero", 0)
    if not prefer_clips and kind == "image" and index == 0:
        return ("hero", 0)
    # Clips rank just under the hero; images and other media follow.
    base = 1 if is_clip else 10
    return ("gallery", base + index)


def media_richness(image_count: int, clip_count: int) -> str:
    """Classify an event's media richness: ``none`` | ``image`` | ``clip``.

    ``clip`` (best) when a video is present, ``image`` when only images, ``none`` when
    neither. Drives clips-first ordering and the media-gap worklist.
    """
    if clip_count >= 1:
        return "clip"
    if image_count >= 1:
        return "image"
    return "none"


PIN_SENSITIVITY = 60          # at/above this, pin locally and never auto-release
LINK_MAX_SENSITIVITY = 30     # below this, a durable host may be linked instead of stored
RELEASE_THRESHOLD = 70        # persistence_confidence at/above which an archive may release

# Category/tag tokens that raise takedown risk (political / government / social pressure).
SENSITIVE_CATEGORIES = {"conflict", "politics", "protest", "military", "crime", "disaster"}
SENSITIVE_TAGS = {
    "war", "protest", "censorship", "human-rights", "election", "coup", "killed",
    "massacre", "police", "surveillance", "leak", "scandal", "terror", "genocide",
    "crackdown", "uprising", "sanctions", "espionage", "detained",
}

# Origins where media is fundamentally ephemeral (often the *only* host of citizen footage).
EPHEMERAL_SOURCE_KINDS = {"social", "user_upload"}
EPHEMERAL_DOMAINS = {
    "twitter.com", "x.com", "t.co", "facebook.com", "fb.watch", "instagram.com",
    "tiktok.com", "telegram.org", "t.me", "youtu.be",
}
# Hosts/kinds considered durable enough to link rather than store.
DURABLE_SOURCE_KINDS = {"encyclopedia", "primary_doc", "dataset"}
DURABLE_DOMAINS = {
    "wikipedia.org", "wikimedia.org", "commons.wikimedia.org", "wikidata.org",
    "archive.org", "loc.gov", "un.org", "europa.eu", "nasa.gov",
}


def _host_suffix_match(domain: str | None, suffixes: set[str]) -> bool:
    if not domain:
        return False
    d = domain.lower().removeprefix("www.")
    return any(d == s or d.endswith("." + s) for s in suffixes)


def score_sensitivity(
    category: str | None, tags: list[str] | None, *, source_kind: str | None = None
) -> int:
    """Takedown-risk score (0–100) from an event's category/tags and the media's origin."""
    score = 0
    if category and category.lower() in SENSITIVE_CATEGORIES:
        score += 40
    hits = sum(1 for t in (tags or []) if t.lower() in SENSITIVE_TAGS)
    score += min(hits, 3) * 15
    if source_kind in EPHEMERAL_SOURCE_KINDS:
        score += 20  # citizen footage of sensitive events is the classic disappearing case
    return max(0, min(score, 100))


def origin_ephemerality(source_kind: str | None, domain: str | None) -> str:
    """Classify how durable the media's host is: ``ephemeral`` | ``mixed`` | ``durable``."""
    if source_kind in EPHEMERAL_SOURCE_KINDS or _host_suffix_match(domain, EPHEMERAL_DOMAINS):
        return "ephemeral"
    if source_kind in DURABLE_SOURCE_KINDS or _host_suffix_match(domain, DURABLE_DOMAINS):
        return "durable"
    return "mixed"


def decide_disposition(
    sensitivity: int,
    ephemerality: str,
    *,
    stable_sources: int = 0,
    persistence_confidence: int = 0,
    default_archive: bool = True,
) -> str:
    """Choose ``pin`` | ``archive`` | ``link`` from the current signals.

    Archive-first: an ambiguous (``mixed``) item defaults to local capture so we never
    lose it for want of a signal; storage is reclaimed later only once it proves durable.
    """
    if sensitivity >= PIN_SENSITIVITY:
        return "pin"
    if ephemerality == "ephemeral":
        return "archive"
    if ephemerality == "durable" and sensitivity < LINK_MAX_SENSITIVITY and stable_sources >= 1:
        return "link"
    # mixed / not-yet-corroborated durable:
    return "archive" if default_archive else "link"


def persistence_confidence(stable_sources: int, days_survived: float) -> int:
    """Confidence (0–100) that the media will remain available *without* our copy —
    grows with the number of independent stable hosts and how long it has survived."""
    conf = min(stable_sources, 3) * 20  # 0..60
    conf += min(max(days_survived, 0.0), 90.0) / 90.0 * 30  # 0..30 over ~3 months
    if stable_sources >= 1 and days_survived >= 30:
        conf += 10  # durability bonus
    return max(0, min(int(round(conf)), 100))


def should_release(
    disposition: str,
    sensitivity: int,
    persistence_confidence_score: int,
    *,
    pinned: bool = False,
    threshold: int = RELEASE_THRESHOLD,
) -> bool:
    """Whether a locally-stored binary may be dropped (keeping thumbnail + links).

    Sensitive/pinned media is **never** auto-released — its whole risk is that external
    availability can be coerced away."""
    if pinned or disposition == "pin" or sensitivity >= PIN_SENSITIVITY:
        return False
    return disposition == "archive" and persistence_confidence_score >= threshold
