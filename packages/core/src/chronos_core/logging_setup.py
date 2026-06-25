"""Centralized logging: a shared init for the API + worker processes that (1) formats logs
consistently, (2) persists WARNING+ records to the ``log_record`` ring buffer so an operator
can read them in the Admin Portal, and (3) supports **runtime log-level control** via the
Config Service (no redeploy).

The DB handler is non-blocking: ``emit`` only appends to an in-process bounded deque; an async
``drain_log_buffer`` task batch-inserts to Postgres. Both the api lifespan and the worker start
that drain task plus a periodic level refresher.
"""

from __future__ import annotations

import collections
import logging
from datetime import UTC, datetime

from chronos_core import config_service, registry
from chronos_core.db import session_scope
from chronos_core.models.log_record import LogRecord
from chronos_core.settings import get_settings

_LOG_FORMAT = "%(levelname)s %(name)s: %(message)s"
_BUFFER_MAX = 5000          # in-memory cap before a drain (deque drops oldest past this)
_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}

# Bounded in-process buffer of pending WARNING+ records (dicts), drained to Postgres.
_buffer: collections.deque[dict] = collections.deque(maxlen=_BUFFER_MAX)

_process_component = "service:worker"   # set by init_logging
_process_level_key = "logging.worker.level"
_configured = False

# logger-module → component_id, derived from agent commands (relate-smart → relate_smart …).
_MODULE_TO_COMPONENT = {
    m.command.replace("-", "_"): m.id
    for m in registry.REGISTRY
    if m.kind == "agent" and m.command
}
_BOTS = {
    "post": "agent:bots.post", "interact": "agent:bots.interact",
    "scheduler": "agent:bots.scheduler", "bootstrap": "agent:bots.scheduler",
}


def component_for_logger(name: str, default: str) -> str:
    """Best-effort map a logger name to a registry component id (falls back to the process)."""
    if name.startswith("chronos.api"):
        return "service:api"
    if name.startswith("chronos.monitoring"):
        return "agent:monitor"
    if name.startswith("chronos.agents."):
        parts = name.split(".")
        if len(parts) >= 4 and parts[2] == "bots":
            return _BOTS.get(parts[3], default)
        if len(parts) >= 3:
            return _MODULE_TO_COMPONENT.get(parts[2], default)
    return default


class DbRingBufferHandler(logging.Handler):
    """A logging handler that buffers WARNING+ records for async persistence (never blocks)."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("chronos.logging"):
                return  # never re-capture our own drain errors (feedback loop)
            _buffer.append({
                "component_id": component_for_logger(record.name, _process_component),
                "logger": record.name[:128],
                "level": record.levelname[:16],
                "message": self.format(record)[:8000],
                "ts": datetime.now(UTC),
            })
        except Exception:  # noqa: BLE001 - logging must never raise
            pass


def init_logging(process_component: str) -> None:
    """Configure logging for a process. ``process_component`` is its registry id
    (``service:api`` or ``service:worker``); it tags otherwise-unmapped records and selects
    the runtime level key. Idempotent."""
    global _process_component, _process_level_key, _configured
    _process_component = process_component
    _process_level_key = (
        "logging.api.level" if process_component == "service:api" else "logging.worker.level"
    )
    if _configured:
        return

    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    # Only add a stdout handler when nothing configured one (the worker/CLI). Under uvicorn the
    # server already installs stream handlers — adding our own would double every line.
    if not root.handlers:
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(sh)

    if not any(isinstance(h, DbRingBufferHandler) for h in root.handlers):
        db = DbRingBufferHandler(level=logging.WARNING)
        db.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(db)
    _configured = True


async def drain_log_buffer(interval: float = 3.0) -> None:
    """Periodically flush buffered WARNING+ records into ``log_record``. Run as a task."""
    import asyncio  # noqa: PLC0415

    while True:
        await asyncio.sleep(interval)
        batch = []
        while _buffer:
            batch.append(_buffer.popleft())
        if not batch:
            continue
        try:
            async with session_scope() as session:
                session.add_all(LogRecord(**r) for r in batch)
        except Exception:  # noqa: BLE001 - a DB blip must not kill the drain loop
            logging.getLogger("chronos.logging").debug("log drain failed", exc_info=True)


async def refresh_log_levels(session) -> str:
    """Apply the configured level to the ``chronos`` loggers. Returns the level applied."""
    default = await config_service.get(session, "logging.default.level", "INFO")
    level = await config_service.get(session, _process_level_key, default)
    if level not in _LEVELS:
        level = "INFO"
    for name in ("chronos", "chronos_agents", "chronos_api"):
        logging.getLogger(name).setLevel(level)
    return level


async def log_level_refresher(interval: float = 30.0) -> None:
    """Poll the Config Service and apply runtime log-level changes. Run as a task."""
    import asyncio  # noqa: PLC0415

    while True:
        try:
            async with session_scope() as session:
                await refresh_log_levels(session)
        except Exception:  # noqa: BLE001
            logging.getLogger("chronos.logging").debug("level refresh failed", exc_info=True)
        await asyncio.sleep(interval)
