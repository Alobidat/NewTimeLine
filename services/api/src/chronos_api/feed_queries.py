"""Feed/recommendation read queries (ADR-0028 / social-and-feed §4-5).

Three tabs, all returning **video-first** events as ``FeedItem`` (event + hero_media_id +
score):

- **foryou**   — a heuristic blend of *recency*, *popularity* (promotes/votes/views),
  *media-richness* (a clip hero ranks first, ADR-0024), and *interest match* (overlap with
  the user's profile), minus already-seen.
- **following** — events authored/tagged by the users + entities the caller follows,
  reverse-chronological with a light popularity nudge.
- **discover** — trending: recent + popular events the caller hasn't seen, with a light
  pseudo-random serendipity jitter.

Scoring weights + page size come from the Config Service (ADR-0019, ``rec.*``/``feed.*``).
Cursors are a simple opaque offset (``"o:<n>"``) — enough for the MVP swipe feed; a
keyset cursor can replace it without changing the client contract.
"""

from __future__ import annotations

import uuid

from chronos_core import config_service
from chronos_core.schemas.interaction import CommentAuthor
from chronos_core.schemas.social import FeedItem, FeedResponse, InteractionItem
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_api.queries import _event_read  # shared event projection

# Event columns + hero media + whether the hero is a video clip (media-richness signal).
_FEED_COLS = """
    e.id, e.title, e.summary, e.t_start, e.t_end, e.time_precision, e.instant,
    e.category, e.tags, e.severity, e.confidence, e.source_count, e.geo_label, e.status,
    e.visibility,
    CASE WHEN e.geom IS NOT NULL THEN ST_X(ST_Centroid(e.geom)) END AS lon,
    CASE WHEN e.geom IS NOT NULL THEN ST_Y(ST_Centroid(e.geom)) END AS lat,
    h.media_id AS hero_media_id,
    h.is_clip AS hero_is_clip,
    h.author_id AS author_id,
    u.handle AS author_handle,
    u.display_name AS author_display_name,
    u.avatar_url AS author_avatar_url
"""

# The clip's author identity (user-generated clips only); paired with `_HERO_JOIN` so the rail
# can show the poster's avatar + a follow affordance without a second round-trip per item.
_AUTHOR_JOIN = "LEFT JOIN users u ON u.id = h.author_id"

# Lateral pick of the event's hero (clip preferred) — exactly one row per event, never broken.
_HERO_JOIN = """
    LEFT JOIN LATERAL (
        SELECT em.media_id,
               (m.kind IN ('video','embed')) AS is_clip,
               m.width AS width,
               -- The uploader, only for user-generated clips; cast the text added_by to uuid.
               -- Agent/seed media (origin_kind <> 'user') has a non-uuid added_by → leave null.
               CASE WHEN m.origin_kind = 'user' THEN em.added_by::uuid END AS author_id
        FROM event_media em JOIN media m ON m.id = em.media_id
        WHERE em.event_id = e.id AND em.role = 'hero'
        ORDER BY em.rank LIMIT 1
    ) h ON true
"""


# Only surface events with something good to show: a clip (video/embed), OR an image that has a
# description AND clears the resolution floor (640px). No hero, a context-less image, or a tiny
# low-res one would render as a black/poor card — which the feed must never do. A NULL width is
# tolerated (unknown until the media-quality agent back-fills it) so we don't hide good images
# pending back-fill. Applied as a WHERE fragment on every feed + related query.
_MIN_IMAGE_WIDTH = 640
_DISPLAYABLE = (
    "h.media_id IS NOT NULL AND (h.is_clip OR ("
    "  e.summary IS NOT NULL AND length(btrim(e.summary)) > 0 "
    f"  AND (h.width IS NULL OR h.width >= {_MIN_IMAGE_WIDTH})"
    "))"
)

# Per-post audience gate (Phase 3). Keyed on the viewer ``:uid`` and the lateral hero
# ``h.author_id`` (non-null only for user-generated clips; agent/seed/bot events have a NULL
# author and are public by construction). Friends rank ABOVE followers, so a friend also
# satisfies a 'followers' post. Anonymous ``:uid`` (the fixed anon UUID) matches no author /
# follow / friendship → only public events pass. Applied as a WHERE fragment on every feed query.
_FRIENDS_EXISTS = (
    "EXISTS (SELECT 1 FROM friendships fr WHERE fr.status='accepted' AND ("
    "  (fr.requester_id = :uid AND fr.addressee_id = h.author_id) "
    "  OR (fr.addressee_id = :uid AND fr.requester_id = h.author_id)))"
)
_VISIBILITY = (
    "(e.visibility = 'public' "
    "  OR h.author_id = :uid "
    "  OR (e.visibility = 'followers' AND ("
    "        EXISTS (SELECT 1 FROM follows f WHERE f.user_id = :uid "
    "                AND f.target_type='user' AND f.target_id = h.author_id) "
    f"        OR {_FRIENDS_EXISTS})) "
    f"  OR (e.visibility = 'friends' AND {_FRIENDS_EXISTS}))"
)


def _parse_cursor(cursor: str | None) -> int:
    """Decode the opaque offset cursor (``o:<n>``). Bad/absent → 0."""
    if not cursor or not cursor.startswith("o:"):
        return 0
    try:
        return max(0, int(cursor[2:]))
    except ValueError:
        return 0


def _next_cursor(offset: int, page: int, got: int) -> str | None:
    """The cursor to fetch the next page, or None when the page wasn't full."""
    return f"o:{offset + page}" if got >= page else None


async def _weights(session: AsyncSession) -> dict[str, float]:
    """For-You blend weights (config-tunable, ADR-0019)."""
    raw = await config_service.get(session, "rec.foryou_weights", {}) or {}
    # ``links`` rewards events that sit in the history web (have related events) — the product's
    # signature is digging back/forward through linked events, so a well-connected event is more
    # rewarding to land on and surfaces the chains the left/right navigation walks.
    base = {"recency": 1.0, "popularity": 0.6, "media": 0.8, "interest": 1.2,
            "seen": 2.0, "links": 0.8}
    base.update({k: float(v) for k, v in raw.items() if k in base})
    return base


async def _page_size(session: AsyncSession, requested: int | None) -> int:
    cfg = int(await config_service.get(session, "feed.page_size", 10))
    if requested is None:
        return cfg
    return max(1, min(requested, 50))


def _item(row) -> FeedItem:
    score = float(getattr(row, "score", 0.0) or 0.0)
    return FeedItem(
        event=_event_read(row),
        hero_media_id=row.hero_media_id,
        hero_is_clip=bool(getattr(row, "hero_is_clip", False)),
        score=score,
        author=_author(row),
    )


def _author(row) -> CommentAuthor | None:
    """The clip's author identity, or None for agent/seed clips (no user author) or projections
    that don't select the author columns. Defensive `getattr` so non-feed callers of `_item` are
    safe (mirrors `_event_read`)."""
    aid = getattr(row, "author_id", None)
    handle = getattr(row, "author_handle", None)
    if aid is None or not handle:
        return None
    return CommentAuthor(
        id=aid,
        handle=handle,
        display_name=getattr(row, "author_display_name", None),
        avatar_url=getattr(row, "author_avatar_url", None),
    )


# --- per-user (profile Posts / Interactions tabs, Phase 3) ----------------------------


async def fetch_user_uploads(
    session: AsyncSession, *, author_id: uuid.UUID, viewer_id: uuid.UUID,
    limit: int = 30, offset: int = 0,
) -> list[FeedItem]:
    """A user's own published posts (hero-attributed to them), newest-first, gated per-post by
    the viewer's audience (``_VISIBILITY``). The profile-level ``posts`` gate is applied by the
    caller before this runs."""
    rows = (
        await session.execute(
            text(
                f"SELECT {_FEED_COLS} FROM events e {_HERO_JOIN} {_AUTHOR_JOIN} "
                "WHERE e.status = 'published' AND h.author_id = :author "
                f"AND {_VISIBILITY} "
                "ORDER BY e.created_at DESC LIMIT :lim OFFSET :off"
            ),
            {"author": author_id, "uid": viewer_id, "lim": limit, "off": offset},
        )
    ).all()
    return [_item(r) for r in rows]


async def fetch_user_reposts(
    session: AsyncSession, *, author_id: uuid.UUID, viewer_id: uuid.UUID,
    limit: int = 30, offset: int = 0,
) -> list[FeedItem]:
    """The events a user has reposted (re-shared), newest-first, each gated per-post by the
    viewer's audience (``_VISIBILITY``). The profile-level ``posts`` gate is applied by the
    caller before this runs."""
    rows = (
        await session.execute(
            text(
                f"SELECT {_FEED_COLS} FROM reposts rp "
                "JOIN events e ON e.id = rp.event_id "
                f"{_HERO_JOIN} {_AUTHOR_JOIN} "
                "WHERE rp.user_id = :author AND e.status = 'published' "
                f"AND {_DISPLAYABLE} AND {_VISIBILITY} "
                "ORDER BY rp.created_at DESC LIMIT :lim OFFSET :off"
            ),
            {"author": author_id, "uid": viewer_id, "lim": limit, "off": offset},
        )
    ).all()
    return [_item(r) for r in rows]


async def fetch_user_interactions(
    session: AsyncSession, *, target_id: uuid.UUID, viewer_id: uuid.UUID, limit: int = 30
) -> list[InteractionItem]:
    """A user's recent actions on events the viewer can see (newest-first). Joins the
    activity log to events and gates each by ``_VISIBILITY``."""
    rows = (
        await session.execute(
            text(
                f"SELECT {_FEED_COLS}, a.kind AS act_kind, a.created_at AS act_at "
                "FROM activity_log a JOIN events e ON e.id = a.target_id "
                f"{_HERO_JOIN} {_AUTHOR_JOIN} "
                "WHERE a.user_id = :target AND a.target_type = 'event' "
                f"AND e.status = 'published' AND {_VISIBILITY} "
                "ORDER BY a.created_at DESC LIMIT :lim"
            ),
            {"target": target_id, "uid": viewer_id, "lim": limit},
        )
    ).all()
    return [
        InteractionItem(kind=r.act_kind, event=_event_read(r), created_at=r.act_at)
        for r in rows
    ]


# --- foryou ---------------------------------------------------------------------------


async def _interest_event_ids(session: AsyncSession, profile, limit: int = 40) -> set[uuid.UUID]:
    """Recent events that share an entity/category the user's profile favours → the candidate
    pool the interest term scores against. Empty profile → empty set (cold start)."""
    entity_ids = [uuid.UUID(k) for k in list(profile.entities)[:20]]
    categories = list(profile.categories)[:10]
    if not entity_ids and not categories:
        return set()
    rows = (
        await session.execute(
            text(
                "SELECT DISTINCT e.id FROM events e "
                "LEFT JOIN event_entities ee ON ee.event_id = e.id "
                "WHERE e.status = 'published' AND ("
                "  ee.entity_id = ANY(:ents) OR e.category = ANY(:cats)) "
                "ORDER BY e.id LIMIT :lim"
            ),
            {"ents": entity_ids or [uuid.UUID(int=0)],
             "cats": categories or [""], "lim": limit},
        )
    ).all()
    return {r.id for r in rows}


async def fetch_foryou(
    session: AsyncSession, *, user_id: uuid.UUID, cursor: str | None, limit: int | None,
    profile=None,
) -> FeedResponse:
    """The ranked For-You feed (ADR-0028). ``profile`` is the caller's interest profile
    (chronos_core.interest.compute_profile); pass it so the interest term is scored."""
    page = await _page_size(session, limit)
    offset = _parse_cursor(cursor)
    w = await _weights(session)
    interest_ids = await _interest_event_ids(session, profile) if profile else set()

    # Scoring blend, all terms in [0,1]-ish so the weights are comparable:
    #   recency    = newer events score higher; (years_ago) decayed over a ~2-year window so
    #                modern events dominate but the term is bounded in (0,1] for all of time.
    #   popularity = promotes + reactions + source_count, log-damped
    #   media      = +1 if the hero is a video clip (clips-first, ADR-0024)
    #   interest   = +1 if the event is in the interest candidate pool
    #   seen       = -1 if the user already has an activity row on it (push it down)
    rows = (
        await session.execute(
            text(
                f"SELECT {_FEED_COLS}, ("
                "  :w_recency * (1.0 / (1.0 + GREATEST(extract(year FROM now()) - e.t_start, 0) "
                "                              / 2.0)) "
                "  + :w_pop * ln(1 + e.source_count "
                "      + COALESCE((SELECT count(*) FROM reactions r WHERE r.event_id = e.id), 0) "
                "      + COALESCE((SELECT GREATEST(sum(p.value),0) FROM promotes p "
                "                  WHERE p.target_type='event' AND p.target_id = e.id), 0)) "
                "  + :w_media * (CASE WHEN h.is_clip THEN 1.0 ELSE 0.0 END) "
                "  + :w_links * ln(1 + (SELECT count(*) FROM event_relations rl "
                "        WHERE rl.src_event = e.id OR rl.dst_event = e.id)) "
                "  + :w_interest * (CASE WHEN e.id = ANY(:interest) THEN 1.0 ELSE 0.0 END) "
                "  - :w_seen * (CASE WHEN EXISTS (SELECT 1 FROM activity_log a "
                "       WHERE a.user_id = :uid AND a.target_type='event' AND a.target_id=e.id) "
                "     THEN 1.0 ELSE 0.0 END) "
                ") AS score "
                f"FROM events e {_HERO_JOIN} {_AUTHOR_JOIN} "
                f"WHERE e.status = 'published' AND {_DISPLAYABLE} AND {_VISIBILITY} "
                "ORDER BY score DESC, e.t_start DESC "
                "LIMIT :lim OFFSET :off"
            ),
            {
                "w_recency": w["recency"], "w_pop": w["popularity"], "w_media": w["media"],
                "w_links": w["links"], "w_interest": w["interest"], "w_seen": w["seen"],
                "interest": list(interest_ids) or [uuid.UUID(int=0)],
                "uid": user_id, "lim": page, "off": offset,
            },
        )
    ).all()
    return FeedResponse(
        tab="foryou",
        items=[_item(r) for r in rows],
        next_cursor=_next_cursor(offset, page, len(rows)),
    )


# --- following ------------------------------------------------------------------------


async def fetch_following(
    session: AsyncSession, *, user_id: uuid.UUID, cursor: str | None, limit: int | None
) -> FeedResponse:
    """Events from the users + entities the caller follows (reverse-chron + light rank).

    An *entity* follow surfaces events the entity is tagged on; a *user* follow surfaces
    events that user authored (``event_media.added_by`` = the user's id — their uploads).
    Followed *events* themselves are included too (so the user sees activity on them)."""
    page = await _page_size(session, limit)
    offset = _parse_cursor(cursor)
    rows = (
        await session.execute(
            text(
                f"SELECT {_FEED_COLS}, 0.0 AS score "
                f"FROM events e {_HERO_JOIN} {_AUTHOR_JOIN} "
                "WHERE e.status = 'published' AND ("
                # entity follows → events tagged with a followed entity
                "  EXISTS (SELECT 1 FROM follows f JOIN event_entities ee ON ee.entity_id = f.target_id "
                "          WHERE f.user_id = :uid AND f.target_type='entity' AND ee.event_id = e.id) "
                # user follows → events that followed user uploaded (added media)
                "  OR EXISTS (SELECT 1 FROM follows f JOIN event_media em "
                "          ON em.added_by = f.target_id::text "
                "          WHERE f.user_id = :uid AND f.target_type='user' AND em.event_id = e.id) "
                # event follows → the followed event itself
                "  OR EXISTS (SELECT 1 FROM follows f WHERE f.user_id = :uid "
                "          AND f.target_type='event' AND f.target_id = e.id) "
                # reposts → events a followed user reposted (re-shared to their followers)
                "  OR EXISTS (SELECT 1 FROM follows f JOIN reposts rp ON rp.user_id = f.target_id "
                "          WHERE f.user_id = :uid AND f.target_type='user' "
                "            AND rp.event_id = e.id)) "
                f"AND {_DISPLAYABLE} AND {_VISIBILITY} "
                "ORDER BY e.t_start DESC, e.severity DESC "
                "LIMIT :lim OFFSET :off"
            ),
            {"uid": user_id, "lim": page, "off": offset},
        )
    ).all()
    return FeedResponse(
        tab="following",
        items=[_item(r) for r in rows],
        next_cursor=_next_cursor(offset, page, len(rows)),
    )


# --- discover -------------------------------------------------------------------------


async def fetch_discover(
    session: AsyncSession, *, user_id: uuid.UUID, cursor: str | None, limit: int | None
) -> FeedResponse:
    """Trending + serendipity: popular recent events the caller hasn't seen, with a light
    deterministic jitter so the feed isn't identical every load."""
    page = await _page_size(session, limit)
    offset = _parse_cursor(cursor)
    rows = (
        await session.execute(
            text(
                f"SELECT {_FEED_COLS}, ("
                "  ln(1 + e.source_count + e.severity "
                "    + COALESCE((SELECT count(*) FROM reactions r WHERE r.event_id = e.id),0) "
                "    + COALESCE((SELECT GREATEST(sum(p.value),0) FROM promotes p "
                "                WHERE p.target_type='event' AND p.target_id=e.id),0)) "
                # Use a *separate* text param for the hash (:uid_text), not :uid: the same bind
                # can't be both text (here) and uuid (the a.user_id filter below) — asyncpg fails
                # to unify the param's type. (`:uid::text` also tripped a text() parse bug.)
                "  + 0.5 * (('x' || substr(md5(e.id::text || :uid_text),1,8))::bit(32)::int "
                "           / 2147483647.0) "  # deterministic per (event,user) serendipity jitter
                ") AS score "
                f"FROM events e {_HERO_JOIN} {_AUTHOR_JOIN} "
                "WHERE e.status = 'published' AND NOT EXISTS ("
                "   SELECT 1 FROM activity_log a WHERE a.user_id = :uid "
                "   AND a.target_type='event' AND a.target_id = e.id) "
                f"AND {_DISPLAYABLE} AND {_VISIBILITY} "
                "ORDER BY score DESC "
                "LIMIT :lim OFFSET :off"
            ),
            {"uid": user_id, "uid_text": str(user_id), "lim": page, "off": offset},
        )
    ).all()
    return FeedResponse(
        tab="discover",
        items=[_item(r) for r in rows],
        next_cursor=_next_cursor(offset, page, len(rows)),
    )
