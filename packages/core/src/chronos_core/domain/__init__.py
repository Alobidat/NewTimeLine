"""Pure domain logic (no I/O): temporal axis + severity scoring.

Kept dependency-free so it is cheap to unit-test and reuse. See module docstrings.
"""

from chronos_core.domain import entities, health, media_policy, severity, temporal

__all__ = ["temporal", "severity", "entities", "media_policy", "health"]
