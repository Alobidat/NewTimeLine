"""chronos_core — shared library for Chronos (NewTimeLine).

Holds the canonical data shapes and pure logic reused across services:
- ``domain``  : pure temporal-axis + severity logic (no I/O)
- ``models``  : SQLAlchemy ORM (the schema; single source of truth)
- ``schemas`` : Pydantic API DTOs
- ``db``      : async engine/session
- ``settings``: env-based config
- ``config_service`` : DB-backed runtime config (ADR-0006)
"""

__version__ = "0.1.0"
