"""PoC seeder: the US ↔ Iran relationship as a curated history web (Tier-1, no LLM).

This is the proof-of-concept dataset behind the product's signature journey — search a
place/actor, land on an anchor event (the 2020 Soleimani strike), then **dig back** through
what led to it (1953 coup → 1979 revolution → hostage crisis → JCPOA collapse) and **forward**
to what it caused (Iran's retaliation). It exercises the whole stack end-to-end:

- **events** anchored on time + place, with neutral summaries and real Wikipedia **sources**;
- **entities** (US, Iran as place-actors; key people; topics) tagged with roles — the anchors
  that make "all events linking the US and Iran" work;
- **event_relations** — explicit ``causal``/``precursor`` edges forming the chain the
  ``/events/{id}/chain`` endpoint walks (the relation-linker later adds same-place/same-actor
  edges automatically from the shared entities);
- **media** spanning the archival policy (ADR-0018): a low-sensitivity encyclopedic image
  → *link*, a sensitive-but-durable image → *archive*, citizen footage of a strike → *pin*.

Curated illustrative data (real, documented events with real sources); idempotent — safe to
re-run, and safe to run alongside the live feeds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from chronos_core import repository
from chronos_core.db import session_scope
from chronos_core.models.enums import TimePrecision
from chronos_core.models.event import Event
from chronos_core.schemas.event import EventCreate, GeoPoint
from sqlalchemy import select

from chronos_agents.publish import load_weights
from chronos_agents.sources import wikimedia

log = logging.getLogger("chronos.agents.seed_iran_us")
AGENT = "seed:iran-us"

# Wikimedia requires a descriptive User-Agent (a generic one gets 403'd).
_UA = wikimedia.USER_AGENT


@dataclass(frozen=True)
class _Ent:
    name: str
    kind: str   # place | person | org | topic
    role: str   # actor | location | subject | affected
    qid: str | None = None


@dataclass(frozen=True)
class _Ev:
    key: str
    t_start: float
    title: str
    category: str
    summary: str
    lon: float
    lat: float
    place: str
    precision: TimePrecision = TimePrecision.YEAR
    t_end: float | None = None
    tags: list[str] = field(default_factory=list)
    entities: list[_Ent] = field(default_factory=list)
    sources: list[tuple[str, str]] = field(default_factory=list)  # (url, title)
    # Origin kind for the event's lead image (drives the archival decision, ADR-0018).
    # The image URL itself is fetched live from the event's Wikipedia article.
    image_origin: str = "encyclopedia"  # encyclopedia | news | social


# Shared entities (Wikidata QIDs where well-known) — countries modeled as place-actors so the
# graph is "anchored on the two locations US and Iran" while still acting as parties.
US = _Ent("United States", "place", "actor", "Q30")
IRAN = _Ent("Iran", "place", "actor", "Q794")
IRAQ = _Ent("Iraq", "place", "actor", "Q796")
UK = _Ent("United Kingdom", "place", "actor", "Q145")


def _loc(name: str) -> _Ent:
    return _Ent(name, "place", "location")


def _person(name: str, qid: str | None = None) -> _Ent:
    return _Ent(name, "person", "actor", qid)


EVENTS: list[_Ev] = [
    _Ev(
        key="relations1883", t_start=1883.0, title="US–Persia diplomatic relations established",
        category="history", precision=TimePrecision.YEAR,
        summary="The United States and Persia (Iran) open formal diplomatic relations, the "
                "start of a long and turbulent bilateral history.",
        lon=51.39, lat=35.69, place="Tehran, Persia", tags=["diplomacy"],
        entities=[US, IRAN, _loc("Tehran")],
        sources=[("https://en.wikipedia.org/wiki/Iran%E2%80%93United_States_relations",
                  "Iran–United States relations")],
    ),
    _Ev(
        key="coup1953", t_start=1953.58, title="1953 Iranian coup d'état (Operation Ajax)",
        category="politics", precision=TimePrecision.MONTH,
        summary="A US- and UK-backed coup overthrows Prime Minister Mohammad Mossadegh after "
                "his nationalization of Iranian oil, restoring the Shah's power.",
        lon=51.39, lat=35.69, place="Tehran, Iran", tags=["coup", "espionage"],
        entities=[US, IRAN, UK, _person("Mohammad Mossadegh", "Q190900"), _loc("Tehran")],
        sources=[("https://en.wikipedia.org/wiki/1953_Iranian_coup_d%27%C3%A9tat",
                  "1953 Iranian coup d'état")],
    ),
    _Ev(
        key="revolution1979", t_start=1979.04, title="Iranian Revolution",
        category="politics", precision=TimePrecision.MONTH,
        summary="Mass uprisings topple the US-backed Shah; Ayatollah Khomeini returns and an "
                "Islamic Republic is established, upending US–Iran ties.",
        lon=51.39, lat=35.69, place="Tehran, Iran", tags=["uprising", "revolution"],
        entities=[US, IRAN, _person("Ruhollah Khomeini", "Q44090"), _loc("Tehran")],
        sources=[("https://en.wikipedia.org/wiki/Iranian_Revolution", "Iranian Revolution")],
    ),
    _Ev(
        key="hostage1979", t_start=1979.84, title="Iran hostage crisis begins",
        category="conflict", precision=TimePrecision.DAY,
        summary="Revolutionary students seize the US embassy in Tehran, holding 52 Americans "
                "for 444 days and rupturing diplomatic relations.",
        lon=51.42, lat=35.70, place="US Embassy, Tehran", tags=["detained", "crisis"],
        entities=[US, IRAN, _loc("Tehran")],
        sources=[("https://en.wikipedia.org/wiki/Iran_hostage_crisis", "Iran hostage crisis")],
    ),
    _Ev(
        key="severed1980", t_start=1980.29, title="US severs diplomatic relations with Iran",
        category="politics", precision=TimePrecision.MONTH,
        summary="Washington formally cuts diplomatic ties with Tehran amid the hostage crisis; "
                "relations remain severed for decades.",
        lon=-77.04, lat=38.90, place="Washington, D.C.", tags=["sanctions"],
        entities=[US, IRAN, _loc("Washington")],
        sources=[("https://en.wikipedia.org/wiki/Iran%E2%80%93United_States_relations",
                  "Iran–United States relations")],
    ),
    _Ev(
        key="iraniraqwar1980", t_start=1980.0, t_end=1988.0,
        title="Iran–Iraq War (US tilt to Iraq)", category="conflict",
        precision=TimePrecision.YEAR,
        summary="During the eight-year Iran–Iraq War the US increasingly backs Iraq, deepening "
                "US–Iran hostility in the Gulf.",
        lon=48.0, lat=31.0, place="Iran–Iraq border", tags=["war"],
        entities=[US, IRAN, IRAQ, _person("Saddam Hussein", "Q1394")],
        sources=[("https://en.wikipedia.org/wiki/Iran%E2%80%93Iraq_War", "Iran–Iraq War")],
    ),
    _Ev(
        key="vincennes1988", t_start=1988.5, title="USS Vincennes downs Iran Air Flight 655",
        category="conflict", precision=TimePrecision.DAY,
        summary="A US warship in the Strait of Hormuz shoots down a civilian Iranian airliner, "
                "killing 290 people; the US later expresses regret but does not apologize.",
        lon=56.27, lat=26.66, place="Strait of Hormuz", tags=["killed", "military"],
        entities=[US, IRAN, _loc("Strait of Hormuz")],
        sources=[("https://en.wikipedia.org/wiki/Iran_Air_Flight_655", "Iran Air Flight 655")],
    ),
    _Ev(
        key="jcpoa2015", t_start=2015.53, title="JCPOA nuclear deal signed",
        category="politics", precision=TimePrecision.DAY,
        summary="Iran and world powers (incl. the US) agree to limit Iran's nuclear program in "
                "exchange for sanctions relief.",
        lon=16.37, lat=48.21, place="Vienna, Austria", tags=["sanctions", "diplomacy"],
        entities=[US, IRAN, _Ent("nuclear program", "topic", "subject")],
        sources=[("https://en.wikipedia.org/wiki/Joint_Comprehensive_Plan_of_Action", "JCPOA")],
    ),
    _Ev(
        key="withdrawal2018", t_start=2018.35, title="US withdraws from the JCPOA",
        category="politics", precision=TimePrecision.DAY,
        summary="The US unilaterally exits the nuclear deal and reimposes 'maximum pressure' "
                "sanctions on Iran.",
        lon=-77.04, lat=38.90, place="Washington, D.C.", tags=["sanctions"],
        entities=[US, IRAN, _person("Donald Trump", "Q22686")],
        sources=[("https://en.wikipedia.org/wiki/United_States_withdrawal_from_the_Joint_Comprehensive_Plan_of_Action",
                  "US withdrawal from the JCPOA")],
    ),
    _Ev(
        key="soleimani2020", t_start=2020.008, title="US drone strike kills Qasem Soleimani",
        category="conflict", precision=TimePrecision.DAY,
        summary="A US drone strike at Baghdad airport kills Iranian general Qasem Soleimani, "
                "sharply escalating US–Iran confrontation.",
        lon=44.23, lat=33.26, place="Baghdad, Iraq", tags=["killed", "military"],
        entities=[US, IRAN, IRAQ, _person("Qasem Soleimani", "Q316"),
                  _person("Donald Trump", "Q22686"), _loc("Baghdad")],
        sources=[("https://en.wikipedia.org/wiki/Assassination_of_Qasem_Soleimani",
                  "Assassination of Qasem Soleimani")],
        image_origin="social",  # citizen footage of a sensitive strike → pinned locally
    ),
    _Ev(
        key="iranstrike2020", t_start=2020.022,
        title="Iran missile strike on US bases (Operation Martyr Soleimani)",
        category="conflict", precision=TimePrecision.DAY,
        summary="In retaliation, Iran launches ballistic missiles at US forces at Al Asad and "
                "Erbil bases in Iraq.",
        lon=42.44, lat=33.79, place="Al Asad Airbase, Iraq", tags=["military", "war"],
        entities=[US, IRAN, IRAQ, _loc("Al Asad Airbase")],
        sources=[("https://en.wikipedia.org/wiki/2020_Iranian_strikes_on_U.S._forces_in_Iraq",
                  "2020 Iranian strikes on U.S. forces in Iraq")],
    ),
]

# Curated cause→effect chain (src is the earlier/cause). The relation-linker adds the
# co-occurrence edges (same-place/same-actor) automatically from the shared entities.
RELATIONS: list[tuple[str, str, str]] = [
    ("coup1953", "revolution1979", "causal"),
    ("revolution1979", "hostage1979", "causal"),
    ("hostage1979", "severed1980", "causal"),
    ("revolution1979", "iraniraqwar1980", "precursor"),
    ("iraniraqwar1980", "vincennes1988", "precursor"),
    ("severed1980", "jcpoa2015", "precursor"),  # decades of estrangement → the nuclear deal
    ("jcpoa2015", "withdrawal2018", "precursor"),
    ("withdrawal2018", "soleimani2020", "causal"),
    ("soleimani2020", "iranstrike2020", "causal"),
    ("relations1883", "coup1953", "precursor"),
]


async def _upsert_event(session, client: httpx.AsyncClient, ev: _Ev, weights) -> Event:
    """Find an existing event by title or create it, then attach sources/entities/media.

    The lead image is resolved live from the event's Wikipedia article, so it is a real,
    fetchable URL (the media-fetcher then archives it per ADR-0018)."""
    event = await session.scalar(select(Event).where(Event.title == ev.title))
    if event is None:
        event = await repository.create_event(
            session,
            EventCreate(
                title=ev.title, summary=ev.summary, t_start=ev.t_start, t_end=ev.t_end,
                time_precision=ev.precision, category=ev.category, tags=ev.tags,
                geo=GeoPoint(lon=ev.lon, lat=ev.lat), geo_label=ev.place,
                created_by_agent=AGENT,
            ),
            weights=weights,
        )
    for url, title in ev.sources:
        source = await repository.get_or_create_source(
            session, url=url, title=title, publisher="Wikipedia", kind="encyclopedia"
        )
        await repository.link_source(session, event, source, added_by=AGENT, weights=weights)
    for e in ev.entities:
        entity = await repository.get_or_create_entity(
            session, kind=e.kind, name=e.name, external_id=e.qid
        )
        await repository.link_entity(session, event, entity, role=e.role, added_by=AGENT)
    if ev.sources:
        image = await wikimedia.wiki_image(client, ev.sources[0][0])
        if image:
            await repository.discover_media(
                session, event, url=image, kind="image",
                source_kind=ev.image_origin, role="hero", added_by=AGENT,
            )
        # Real video clip from the same Wikipedia article, when one exists (WebM only).
        clip = await wikimedia.wiki_video(client, ev.sources[0][0])
        if clip:
            url, caption = clip
            media = await repository.discover_media(
                session, event, url=url, kind="video", mime="video/webm",
                source_kind="encyclopedia", role="gallery", added_by=AGENT,
            )
            # Wikimedia is a durable, CORS-friendly host, so let the client play the clip
            # directly (instant, no wait on the fetch worker); media-fetch may still archive
            # the bytes per ADR-0018.
            media.embed_url = url
            if caption:
                media.caption = caption
    return event


async def seed_iran_us() -> dict:
    """Seed the curated US–Iran history web (idempotent). Returns counts."""
    async with session_scope() as session, httpx.AsyncClient(headers={"User-Agent": _UA}) as client:
        weights = await load_weights(session)
        ids: dict[str, object] = {}
        for ev in EVENTS:
            event = await _upsert_event(session, client, ev, weights)
            ids[ev.key] = event.id

        edges = 0
        for src, dst, kind in RELATIONS:
            created = await repository.link_relation(
                session, src_event=ids[src], dst_event=ids[dst],
                kind=kind, weight=0.9, created_by=AGENT,
            )
            edges += 1 if created else 0

    totals = {"events": len(EVENTS), "relations": len(RELATIONS), "new_edges": edges}
    log.info("seed iran-us: %s", totals)
    return totals
