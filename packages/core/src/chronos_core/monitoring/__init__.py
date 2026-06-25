"""System-health monitoring subsystem.

The collector (run as a worker ticker — see chronos_agents.worker) probes every registered
component, samples per-container + host resource utilization via the Docker Engine API, and
writes ``component_health`` snapshots + ``metric_sample`` time-series the Admin Portal reads.
Self-contained (no Prometheus): httpx over the Docker unix socket + stdlib for host stats.
"""

from chronos_core.monitoring.collector import Collector, run_monitor

__all__ = ["Collector", "run_monitor"]
