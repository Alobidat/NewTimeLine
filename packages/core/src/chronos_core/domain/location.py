"""Pure location resolution helpers for the geocoder cascade (ADR-0020).

No I/O, no LLM — deterministic lookups over curated tables so the geocoder can resolve a
location for *every* event without a network round-trip when possible:

  * ``extract_countries(text…)`` — scan free text for country names / demonyms (cascade
    step 4: "analyse the event info and assign one or more locations").
  * ``centroid(country)`` — a country's approximate centroid (lat, lon) so an extracted or
    agency-derived country becomes a map point with no Nominatim call.
  * ``domain_country(domain)`` — the country of a news agency / source host (cascade step 5,
    the last resort).

Tables are intentionally curated and small; they grow over time. The text step is rules-based
now and may be upgraded to an LLM pass later (same "rules now, LLM later" pattern as ADR-0018).
"""

from __future__ import annotations

import re

# Approximate country centroids (lat, lon). Canonical country name → point. Curated for the
# common cases + the US/Iran/Gulf PoC region; extend as coverage grows.
COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "United States": (39.8, -98.6),
    "Iran": (32.4, 53.7),
    "Iraq": (33.0, 43.7),
    "Israel": (31.4, 35.0),
    "Saudi Arabia": (24.0, 45.0),
    "Qatar": (25.3, 51.2),
    "United Arab Emirates": (23.9, 54.3),
    "Kuwait": (29.3, 47.5),
    "Bahrain": (26.0, 50.5),
    "Oman": (21.5, 55.9),
    "Yemen": (15.6, 48.0),
    "Syria": (35.0, 38.5),
    "Lebanon": (33.9, 35.9),
    "Jordan": (31.3, 36.5),
    "Turkey": (39.0, 35.2),
    "Egypt": (26.8, 30.8),
    "United Kingdom": (54.0, -2.0),
    "France": (46.2, 2.2),
    "Germany": (51.2, 10.4),
    "Russia": (61.5, 105.3),
    "Ukraine": (48.4, 31.2),
    "China": (35.9, 104.2),
    "Japan": (36.2, 138.3),
    "India": (22.0, 79.0),
    "Pakistan": (30.4, 69.3),
    "Afghanistan": (33.9, 67.7),
    "Canada": (56.1, -106.3),
    "Mexico": (23.6, -102.6),
    "Brazil": (-14.2, -51.9),
    "Argentina": (-38.4, -63.6),
    "Australia": (-25.3, 133.8),
    "Spain": (40.5, -3.7),
    "Italy": (41.9, 12.6),
    "Poland": (51.9, 19.1),
    "South Korea": (36.5, 127.9),
    "North Korea": (40.3, 127.5),
    "Indonesia": (-2.5, 118.0),
    "South Africa": (-30.6, 22.9),
    "Nigeria": (9.1, 8.7),
    "Greece": (39.1, 21.8),
    "Switzerland": (46.8, 8.2),
    "Netherlands": (52.1, 5.3),
    "Sweden": (60.1, 18.6),
    "Norway": (60.5, 8.5),
    "Libya": (26.3, 17.2),
    "Sudan": (12.9, 30.2),
    "Venezuela": (6.4, -66.6),
    "Cuba": (21.5, -77.8),
}

# Aliases / demonyms / common short forms → canonical country name.
_ALIASES: dict[str, str] = {
    "usa": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "us": "United States", "america": "United States", "american": "United States",
    "washington": "United States",
    "iranian": "Iran", "tehran": "Iran", "persia": "Iran", "persian": "Iran",
    "iraqi": "Iraq", "baghdad": "Iraq",
    "israeli": "Israel", "jerusalem": "Israel", "tel aviv": "Israel",
    "saudi": "Saudi Arabia", "riyadh": "Saudi Arabia",
    "emirati": "United Arab Emirates", "uae": "United Arab Emirates", "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates",
    "qatari": "Qatar", "doha": "Qatar",
    "kuwaiti": "Kuwait", "yemeni": "Yemen", "omani": "Oman", "bahraini": "Bahrain",
    "syrian": "Syria", "damascus": "Syria", "lebanese": "Lebanon", "beirut": "Lebanon",
    "jordanian": "Jordan", "amman": "Jordan",
    "turkish": "Turkey", "ankara": "Turkey", "istanbul": "Turkey", "türkiye": "Turkey",
    "egyptian": "Egypt", "cairo": "Egypt",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "britain": "United Kingdom",
    "british": "United Kingdom", "england": "United Kingdom", "london": "United Kingdom",
    "french": "France", "paris": "France",
    "german": "Germany", "berlin": "Germany",
    "russian": "Russia", "moscow": "Russia", "soviet": "Russia", "ussr": "Russia",
    "ukrainian": "Ukraine", "kyiv": "Ukraine", "kiev": "Ukraine",
    "chinese": "China", "beijing": "China", "peking": "China",
    "japanese": "Japan", "tokyo": "Japan",
    "indian": "India", "new delhi": "India", "delhi": "India",
    "pakistani": "Pakistan", "islamabad": "Pakistan",
    "afghan": "Afghanistan", "kabul": "Afghanistan",
    "canadian": "Canada", "mexican": "Mexico",
    "brazilian": "Brazil", "argentine": "Argentina", "argentinian": "Argentina",
    "australian": "Australia", "spanish": "Spain", "madrid": "Spain",
    "italian": "Italy", "rome": "Italy", "polish": "Poland",
    "korean": "South Korea", "seoul": "South Korea", "pyongyang": "North Korea",
    "indonesian": "Indonesia", "jakarta": "Indonesia",
    "libyan": "Libya", "tripoli": "Libya", "sudanese": "Sudan",
    "venezuelan": "Venezuela", "caracas": "Venezuela", "cuban": "Cuba", "havana": "Cuba",
}

# News agency / source host → country (cascade last resort). Matched by domain suffix.
_DOMAIN_COUNTRY: dict[str, str] = {
    "bbc.co.uk": "United Kingdom", "bbc.com": "United Kingdom",
    "theguardian.com": "United Kingdom", "reuters.com": "United Kingdom",
    "cnn.com": "United States", "nytimes.com": "United States",
    "washingtonpost.com": "United States", "apnews.com": "United States",
    "foxnews.com": "United States", "nbcnews.com": "United States",
    "npr.org": "United States", "bloomberg.com": "United States",
    "aljazeera.com": "Qatar", "aljazeera.net": "Qatar",
    "presstv.ir": "Iran", "tasnimnews.com": "Iran", "irna.ir": "Iran", "mehrnews.com": "Iran",
    "rt.com": "Russia", "tass.com": "Russia", "sputniknews.com": "Russia",
    "xinhuanet.com": "China", "globaltimes.cn": "China", "scmp.com": "China",
    "dw.com": "Germany", "spiegel.de": "Germany",
    "lemonde.fr": "France", "france24.com": "France", "afp.com": "France",
    "haaretz.com": "Israel", "timesofisrael.com": "Israel", "jpost.com": "Israel",
    "arabnews.com": "Saudi Arabia", "alarabiya.net": "Saudi Arabia",
    "thenationalnews.com": "United Arab Emirates", "gulfnews.com": "United Arab Emirates",
    "dawn.com": "Pakistan", "thehindu.com": "India", "timesofindia.indiatimes.com": "India",
    "smh.com.au": "Australia", "abc.net.au": "Australia",
    "cbc.ca": "Canada", "elpais.com": "Spain",
}

# Build a single regex of all known surface forms (longest first so "saudi arabia" wins over
# "arabia"-like fragments). Word-boundary anchored, case-insensitive.
_SURFACE_FORMS: dict[str, str] = {
    **{name.lower(): name for name in COUNTRY_CENTROIDS},
    **_ALIASES,
}
_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(_SURFACE_FORMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def centroid(country: str) -> tuple[float, float] | None:
    """Approximate (lat, lon) centroid for a canonical country name, or None if unknown."""
    return COUNTRY_CENTROIDS.get(country)


def extract_countries(*texts: str | None) -> list[str]:
    """Return canonical country names mentioned across the given texts, in first-seen order.

    Resolves country names, demonyms ("Iranian"), and well-known capitals ("Tehran").
    Deduplicated; only countries we have a centroid for are returned (so each is mappable).
    """
    seen: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in _PATTERN.finditer(text):
            country = _SURFACE_FORMS.get(match.group(1).lower())
            if country and country not in seen and country in COUNTRY_CENTROIDS:
                seen.append(country)
    return seen


def domain_country(domain: str | None) -> str | None:
    """Country of a news agency / source host, matched by domain suffix. None if unknown."""
    if not domain:
        return None
    d = domain.strip().lower().lstrip(".")
    if d.startswith("www."):
        d = d[4:]
    for host, country in _DOMAIN_COUNTRY.items():
        if d == host or d.endswith("." + host):
            return country
    return None
