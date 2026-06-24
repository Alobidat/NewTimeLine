"""License gating for AI-user video discovery — **fail-closed**.

The hard rule (per product decision): a clip is only eligible to post if its license string,
read from the source's own metadata, is recognisably *free* (public domain or a permissive
Creative Commons / free-stock license). A clip with **no parseable license is rejected**, never
posted on a guess. :func:`is_free_license` is the single gate every free-video source passes its
candidates through; :func:`normalize_license` maps the raw string onto the ≤64-char value stored
on ``media.license`` for audit + on-card credit.

By default non-commercial (``NC``) licenses are **rejected** (commercial-safe). Set
``bots.allow_noncommercial`` true to permit CC BY-NC for non-commercial display.
"""

from __future__ import annotations

import re

# Recognisably-free license markers (public domain + permissive CC + named free-stock licenses).
_FREE_PATTERNS = (
    r"\bcc0\b",
    r"public[\s-]*domain",
    r"\bpdm\b",
    r"\bno[\s-]*restrictions\b",
    r"\bcc[\s-]*by(?:[\s-]*sa)?(?:[\s-]*\d(?:\.\d)?)?\b",  # CC BY / CC BY-SA (+ version)
    r"\bcreative[\s-]*commons[\s-]*attribution\b",
    r"\bpexels\b",
    r"\bpixabay\b",
    r"\bunsplash\b",
    r"\bcoverr\b",
    r"\bmixkit\b",
    r"\bnasa\b",
)
_FREE_RE = re.compile("|".join(_FREE_PATTERNS), re.IGNORECASE)

# Non-free markers that must NOT appear (ND forbids the derivative display we do; "all rights
# reserved"/copyright/proprietary are obviously out). NC is conditional (see allow_noncommercial).
_NONCOMMERCIAL_RE = re.compile(r"\bnc\b|non[\s-]*commercial", re.IGNORECASE)
_NODERIV_RE = re.compile(r"\bnd\b|no[\s-]*deriv", re.IGNORECASE)
_RESERVED_RE = re.compile(
    r"all[\s-]*rights[\s-]*reserved|copyright|proprietary|fair[\s-]*use", re.IGNORECASE
)


def is_free_license(raw: str | None, *, allow_noncommercial: bool = False) -> bool:
    """True iff ``raw`` is a recognisably-free license. Fail-closed: ``None``/unknown → False."""
    if not raw or not raw.strip():
        return False
    text = raw.strip()
    if _RESERVED_RE.search(text):
        return False
    if _NODERIV_RE.search(text):
        return False
    if _NONCOMMERCIAL_RE.search(text) and not allow_noncommercial:
        return False
    return bool(_FREE_RE.search(text))


def normalize_license(raw: str | None) -> str | None:
    """The license string to store on ``media.license`` (≤64 chars), or None if unusable."""
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return cleaned[:64] or None
