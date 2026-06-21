"""Video seeder: populate the feed with real, freely-licensed news/history **video clips**.

Why this exists: the TikTok-style For-You feed is video-first, but a fresh box has only
image heroes — so new users see no clips. This seeder fills the corpus with browser-playable
clips pulled from **Wikimedia Commons** (CC / public-domain, durable, CORS-friendly), grouped
into curated news/history topics so the result has real *relations* and *history*, not a flat
pile.

Deliberately NOT YouTube / TikTok / Instagram: their terms forbid download, and their embeds
can't be played by the client's ``video_player`` (which needs direct mp4/webm bytes, served via
``/media/{id}/raw``). Commons WebM clips play directly.

For each topic we fetch N Commons videos and, per clip, create a PUBLISHED event with a time
(from the clip's metadata date, else the topic's hint), the topic's place + actor/topic
entities (the anchors the relation-linker and feed interest-match key on), and the clip as the
**hero** media. Within a topic the events are chained chronologically (``precursor`` edges);
cross-topic co-occurrence edges come for free from the shared entities once ``agents relate``
runs. Idempotent: an event is matched by title before being (re)created.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx
from chronos_core import repository
from chronos_core.db import session_scope
from chronos_core.models.event import Event
from chronos_core.schemas.event import EventCreate, GeoPoint
from sqlalchemy import select

from chronos_agents.publish import load_weights
from chronos_agents.sources import wikimedia

log = logging.getLogger("chronos.agents.seed_video")

AGENT = "seed.video"
_UA = wikimedia.USER_AGENT


@dataclass(frozen=True)
class _Ent:
    name: str
    kind: str        # place | person | org | topic
    role: str        # actor | location | subject
    qid: str | None = None


@dataclass(frozen=True)
class _Topic:
    key: str
    query: str               # Wikimedia Commons search string
    title: str               # human topic label (used when a clip title is too thin)
    summary: str             # fallback event summary
    year: float              # fallback t_start when a clip carries no date
    place: str               # geo_label
    lon: float
    lat: float
    category: str
    tags: list[str]
    entities: list[_Ent]
    count: int = 6


# Place/actor anchors reused across topics so the relation-linker draws cross-topic edges.
_USA = _Ent("United States", "place", "actor", "Q30")
_NASA = _Ent("NASA", "org", "actor", "Q23548")
_SPACE = _Ent("space exploration", "topic", "subject")
_NATURE = _Ent("natural disaster", "topic", "subject")


# ── Curated topics (news + history themes with strong free-video coverage on Commons) ──────
TOPICS: list[_Topic] = [
    _Topic("apollo", "Apollo program moon landing", "Apollo Moon landings",
           "NASA's Apollo program landed the first humans on the Moon.", 1969.0,
           "Cape Canaveral, USA", -80.60, 28.39, "science",
           ["space", "history", "nasa"],
           [_USA, _NASA, _SPACE, _Ent("Neil Armstrong", "person", "actor", "Q1615")]),
    _Topic("shuttle", "Space Shuttle launch", "Space Shuttle era",
           "NASA's Space Shuttle flew crews and cargo to orbit for three decades.", 1985.0,
           "Kennedy Space Center, USA", -80.65, 28.52, "science",
           ["space", "nasa", "spaceflight"],
           [_USA, _NASA, _SPACE]),
    _Topic("mars", "Mars rover NASA", "Mars exploration",
           "Robotic rovers explore the surface of Mars.", 2012.0,
           "Mars", 0.0, 0.0, "science",
           ["space", "mars", "nasa", "robotics"],
           [_NASA, _SPACE, _Ent("Mars", "place", "subject", "Q111")]),
    _Topic("spacex", "SpaceX rocket launch", "Commercial spaceflight",
           "SpaceX pioneered reusable orbital rockets.", 2018.0,
           "Boca Chica, USA", -97.15, 25.99, "science",
           ["space", "spacex", "rockets"],
           [_USA, _SPACE, _Ent("SpaceX", "org", "actor", "Q193701")]),
    _Topic("volcano", "volcanic eruption", "Volcanic eruptions",
           "Explosive volcanic eruptions reshape landscapes and disrupt life.", 2010.0,
           "Iceland", -19.02, 63.63, "disaster",
           ["volcano", "nature", "disaster"],
           [_NATURE, _Ent("volcano", "topic", "subject", "Q8072")]),
    _Topic("hurricane", "hurricane storm satellite", "Hurricanes & storms",
           "Tropical cyclones bring destructive winds and flooding.", 2017.0,
           "Atlantic Ocean", -45.0, 25.0, "disaster",
           ["weather", "hurricane", "disaster"],
           [_NATURE, _Ent("tropical cyclone", "topic", "subject", "Q79602")]),
    _Topic("earthquake", "earthquake aftermath footage", "Earthquakes",
           "Major earthquakes strike with little warning.", 2011.0,
           "Japan", 142.37, 38.32, "disaster",
           ["earthquake", "nature", "disaster"],
           [_NATURE, _Ent("earthquake", "topic", "subject", "Q7944")]),
    _Topic("ww2", "World War II footage", "World War II",
           "The Second World War reshaped the global order.", 1943.0,
           "Europe", 10.0, 50.0, "conflict",
           ["history", "war", "ww2"],
           [_Ent("World War II", "topic", "subject", "Q362"),
            _Ent("Allies of World War II", "org", "actor", "Q208533")]),
    _Topic("berlinwall", "Berlin Wall 1989", "Fall of the Berlin Wall",
           "The Berlin Wall fell in 1989, ending decades of division.", 1989.85,
           "Berlin, Germany", 13.38, 52.52, "history",
           ["history", "coldwar", "germany"],
           [_Ent("Germany", "place", "location", "Q183"),
            _Ent("Cold War", "topic", "subject", "Q8683")]),
    _Topic("inauguration", "United States presidential inauguration", "US presidents",
           "US presidential inaugurations and addresses.", 2009.05,
           "Washington, D.C., USA", -77.01, 38.89, "politics",
           ["politics", "usa", "history"],
           [_USA, _Ent("President of the United States", "topic", "subject", "Q11696")]),
    _Topic("olympics", "Olympic Games opening ceremony", "Olympic Games",
           "The Olympic Games gather the world's athletes.", 2012.6,
           "London, UK", -0.12, 51.51, "culture",
           ["sport", "olympics", "culture"],
           [_Ent("Olympic Games", "topic", "subject", "Q5389")]),
    _Topic("protest", "protest demonstration march", "Protests & movements",
           "Mass protests and civil movements demand change.", 2019.0,
           "Hong Kong", 114.17, 22.32, "politics",
           ["politics", "protest", "society"],
           [_Ent("protest", "topic", "subject", "Q273120")]),
    _Topic("aviation", "early aviation flight history", "Aviation history",
           "From the first powered flight to the jet age.", 1950.0,
           "Kitty Hawk, USA", -75.67, 36.06, "history",
           ["history", "aviation", "technology"],
           [_USA, _Ent("aviation", "topic", "subject", "Q765633")]),
    _Topic("eclipse", "solar eclipse totality", "Astronomical events",
           "Total solar eclipses sweep narrow paths across the Earth.", 2017.6,
           "United States", -98.0, 39.0, "science",
           ["astronomy", "science", "nature"],
           [_Ent("solar eclipse", "topic", "subject", "Q3887")]),
    _Topic("wildlife", "wildlife nature documentary", "Wildlife & nature",
           "The natural world in motion.", 2015.0,
           "Africa", 21.0, 0.0, "nature",
           ["nature", "wildlife", "science"],
           [_Ent("wildlife", "topic", "subject", "Q186521")]),
]


async def _seed_topic(session, client, topic: _Topic, weights) -> list:
    """Create (or find) one event per Commons clip for ``topic``. Returns event ids in
    chronological order (for the precursor chain)."""
    clips = await wikimedia.commons_videos(client, topic.query, limit=topic.count)
    rows: list[tuple[float, object]] = []  # (t_start, event_id) for chronological chaining
    for idx, clip in enumerate(clips):
        # A stable, readable title; small per-index jitter keeps same-year clips orderable.
        base_title = clip.title[:140] if len(clip.title) > 12 else f"{topic.title}: {clip.title}"
        # Anchor at the curated topic year, NOT the clip's file metadata date — Commons'
        # DateTimeOriginal is when the file was created/uploaded (e.g. a 2019 upload of 1969
        # Apollo footage), so it can't be trusted as the historical event time. The per-index
        # offset just keeps a topic's clips ordered + distinct for the chronological chain.
        t_start = topic.year + idx * 0.05

        event = await session.scalar(select(Event).where(Event.title == base_title))
        if event is None:
            event = await repository.create_event(
                session,
                EventCreate(
                    title=base_title,
                    summary=(clip.description or topic.summary)[:600],
                    t_start=t_start, t_end=t_start, time_precision="year",
                    category=topic.category, tags=topic.tags,
                    geo=GeoPoint(lon=topic.lon, lat=topic.lat), geo_label=topic.place,
                    created_by_agent=AGENT,
                ),
                weights=weights,
            )

        # Provenance: the Commons File: page as an encyclopedia source.
        source = await repository.get_or_create_source(
            session, url=clip.page_url, title=clip.title,
            publisher="Wikimedia Commons", kind="encyclopedia",
        )
        await repository.link_source(session, event, source, added_by=AGENT, weights=weights)

        # Topic anchors (places/actors/subjects) — the relation-linker + interest-match key.
        for e in topic.entities:
            entity = await repository.get_or_create_entity(
                session, kind=e.kind, name=e.name, external_id=e.qid
            )
            await repository.link_entity(session, event, entity, role=e.role, added_by=AGENT)

        # The clip itself → hero. embed_url lets the client play it instantly (Commons is a
        # durable, CORS-friendly host); media-fetch may still archive the bytes per ADR-0018.
        media = await repository.discover_media(
            session, event, url=clip.url, kind="video", mime=clip.mime,
            role="hero", rank=0, width=clip.width, height=clip.height,
            duration_s=clip.duration_s, caption=clip.title,
            source_kind="encyclopedia", added_by=AGENT,
        )
        media.embed_url = clip.url
        if clip.license:
            media.license = clip.license[:64]
        if clip.credit:
            media.credit = clip.credit

        rows.append((t_start, event.id))

    rows.sort(key=lambda r: r[0])
    return [eid for _, eid in rows]


async def seed_video(*, per_topic: int = 6, max_total: int = 100) -> dict:
    """Seed video-hero events across the curated topics, then chain each topic chronologically.

    Run ``agents relate`` afterwards to add the cross-topic co-occurrence edges from the shared
    entities. Idempotent. Returns counts."""
    total_events = 0
    total_edges = 0
    async with session_scope() as session, httpx.AsyncClient(headers={"User-Agent": _UA}) as client:
        weights = await load_weights(session)
        for topic in TOPICS:
            if total_events >= max_total:
                break
            t = _Topic(**{**topic.__dict__, "count": min(per_topic, max_total - total_events)})
            ids = await _seed_topic(session, client, t, weights)
            total_events += len(ids)
            # Chronological precursor chain within the topic (the earlier event "leads to" the
            # next) — the history the /chain endpoint walks.
            for src, dst in zip(ids, ids[1:]):
                if await repository.link_relation(
                    session, src_event=src, dst_event=dst,
                    kind="precursor", weight=0.8, created_by=AGENT,
                ):
                    total_edges += 1
            log.info("seed-video: topic %s -> %d clips", topic.key, len(ids))

    totals = {"events": total_events, "chain_edges": total_edges, "topics": len(TOPICS)}
    log.info("seed-video done: %s", totals)
    return totals
