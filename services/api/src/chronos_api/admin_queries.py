"""Read/aggregation helpers for the Admin API.

Everything the portal shows is assembled here from three generic sources — the component
**registry** (manifests), the **config specs** (typed config metadata), and **agent_runs**
(health/history) — so new components need no new query code.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from chronos_core import config_service, registry
from chronos_core.config_spec import SPECS, public_value
from chronos_core.domain.health import RunInfo, derive_health
from chronos_core.registry import ComponentManifest
from chronos_core.runs import recent_runs
from chronos_core.schemas.admin import (
    ComponentView,
    ConfigEntry,
    HealthView,
    IntegrityView,
    RunView,
    StorageView,
    SystemView,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _run_view(r) -> RunView:
    return RunView(
        id=r.id, component_id=r.component_id, command=r.command, status=r.status,
        started_at=r.started_at, finished_at=r.finished_at, stats=r.stats, error=r.error,
    )


async def all_config_values(session: AsyncSession) -> dict:
    """Every config value currently set in the DB (key → value)."""
    return await config_service.get_many(session, "")


def config_entries(
    values: dict, *, component_id: str | None = None, scope: str | None = None
) -> list[ConfigEntry]:
    """Build config entries (spec + current value) optionally filtered by component/scope."""
    out: list[ConfigEntry] = []
    for spec in SPECS:
        if component_id is not None and spec.component_id != component_id:
            continue
        if scope is not None and spec.scope != scope:
            continue
        value = values.get(spec.key, spec.default)
        out.append(
            ConfigEntry(
                key=spec.key, type=spec.type, scope=spec.scope, label=spec.label,
                help=spec.help, component_id=spec.component_id,
                value=public_value(spec.key, value), default=spec.default,
                minimum=spec.minimum, maximum=spec.maximum, choices=spec.choices,
                secret=spec.secret,
            )
        )
    return out


async def component_health_view(
    session: AsyncSession, component_id: str, now: datetime
) -> HealthView:
    """Derive a component's health from its recent runs."""
    runs = await recent_runs(session, component_id, limit=20)
    infos = [RunInfo(r.status, r.started_at, r.finished_at) for r in runs]
    return HealthView(**asdict(derive_health(infos, now)))


async def component_view(
    session: AsyncSession, m: ComponentManifest, now: datetime, values: dict
) -> ComponentView:
    """Assemble a component's view (manifest + enabled state + health)."""
    enabled = values.get(m.enabled_key) if m.enabled_key else None
    return ComponentView(
        id=m.id, kind=m.kind, title=m.title, description=m.description,
        capabilities=m.capabilities, actions=m.actions, config_prefix=m.config_prefix,
        enabled=enabled, health=await component_health_view(session, m.id, now), doc=m.doc,
    )


async def counts(session: AsyncSession) -> dict[str, int]:
    """Headline entity counts for the overview."""
    row = (
        await session.execute(
            text(
                "SELECT (SELECT count(*) FROM events) AS events, "
                "(SELECT count(*) FROM entities) AS entities, "
                "(SELECT count(*) FROM event_relations) AS relations, "
                "(SELECT count(*) FROM media) AS media, "
                "(SELECT count(*) FROM sources) AS sources"
            )
        )
    ).first()
    return {
        "events": row.events, "entities": row.entities, "relations": row.relations,
        "media": row.media, "sources": row.sources,
    }


async def integrity(session: AsyncSession) -> IntegrityView:
    """Count published events missing a required field (Location / Actors / Media) — ADR-0020.

    This is the worklist the geocoder + enricher consume and the coverage the portal shows."""
    row = (
        await session.execute(
            text(
                "SELECT count(*) AS published, "
                "count(*) FILTER (WHERE geom IS NULL) AS missing_location, "
                "count(*) FILTER (WHERE NOT EXISTS ("
                "  SELECT 1 FROM event_entities ee WHERE ee.event_id = e.id "
                "  AND ee.role = 'actor')) AS missing_actors, "
                "count(*) FILTER (WHERE NOT EXISTS ("
                "  SELECT 1 FROM event_media em WHERE em.event_id = e.id)) AS missing_media "
                "FROM events e WHERE e.status = 'published'"
            )
        )
    ).first()
    return IntegrityView(
        published=row.published,
        missing_location=row.missing_location,
        missing_actors=row.missing_actors,
        missing_media=row.missing_media,
    )


async def storage(session: AsyncSession) -> StorageView:
    """Media usage by status/disposition + stored bytes, plus headline totals."""
    by_status = {
        r.status: r.c
        for r in (await session.execute(
            text("SELECT status, count(*) AS c FROM media GROUP BY status")
        )).all()
    }
    by_disp = {
        r.disposition: r.c
        for r in (await session.execute(
            text("SELECT disposition, count(*) AS c FROM media GROUP BY disposition")
        )).all()
    }
    stored_bytes = await session.scalar(
        text("SELECT coalesce(sum(bytes), 0) FROM media WHERE status = 'stored'")
    )
    return StorageView(
        media_by_status=by_status, media_by_disposition=by_disp,
        media_stored_bytes=int(stored_bytes or 0), totals=await counts(session),
        integrity=await integrity(session),
    )


async def system(session: AsyncSession, environment: str, queue_depth: int = 0) -> SystemView:
    """System status + pipeline throughput metrics."""
    running, config_keys, events_1h, runs_1h = (
        await session.scalar(
            text("SELECT count(*) FROM agent_runs WHERE status = 'running'")
        ),
        await session.scalar(text("SELECT count(*) FROM config")),
        await session.scalar(
            text("SELECT count(*) FROM events WHERE created_at > now() - interval '1 hour'")
        ),
        await session.scalar(
            text(
                "SELECT count(*) FROM agent_runs "
                "WHERE status = 'ok' AND finished_at > now() - interval '1 hour'"
            )
        ),
    )
    return SystemView(
        environment=environment, database="ok",
        config_keys=int(config_keys or 0),
        components=len(registry.REGISTRY),
        running_agents=int(running or 0),
        queue_depth=queue_depth,
        events_last_hour=int(events_1h or 0),
        runs_last_hour=int(runs_1h or 0),
    )
