"""Host resource readings via the stdlib (no psutil).

Disk from ``os.statvfs``; memory from ``/proc/meminfo``; CPU busy fraction from ``/proc/stat``
(the collector diffs successive reads into a percentage). When the host root is bind-mounted
at ``/host`` (compose, read-only) we read disk from there for a host-accurate figure;
otherwise we fall back to the container's own view of ``/``.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger("chronos.monitoring.host")

_DISK_PATH = "/host" if os.path.exists("/host") else "/"
_MEMINFO = "/host/proc/meminfo" if os.path.exists("/host/proc/meminfo") else "/proc/meminfo"
_STAT = "/host/proc/stat" if os.path.exists("/host/proc/stat") else "/proc/stat"


def disk_usage() -> dict[str, float]:
    """total/used bytes + used percent for the data volume."""
    try:
        st = os.statvfs(_DISK_PATH)
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        return {
            "disk_total_bytes": float(total),
            "disk_used_bytes": float(used),
            "disk_used_pct": (used / total * 100.0) if total else 0.0,
        }
    except OSError:
        log.warning("disk_usage failed for %s", _DISK_PATH, exc_info=True)
        return {}


def mem_usage() -> dict[str, float]:
    """total/available bytes + used percent from /proc/meminfo."""
    try:
        vals: dict[str, int] = {}
        with open(_MEMINFO) as f:
            for line in f:
                k, _, rest = line.partition(":")
                if k in ("MemTotal", "MemAvailable"):
                    vals[k] = int(rest.strip().split()[0]) * 1024  # kB → bytes
        total = vals.get("MemTotal")
        avail = vals.get("MemAvailable")
        if not total:
            return {}
        used = total - (avail or 0)
        return {
            "mem_total_bytes": float(total),
            "mem_used_bytes": float(used),
            "mem_used_pct": used / total * 100.0,
        }
    except (OSError, ValueError):
        log.warning("mem_usage failed", exc_info=True)
        return {}


def cpu_times() -> tuple[int, int] | None:
    """(total_jiffies, idle_jiffies) from the aggregate ``cpu`` line of /proc/stat."""
    try:
        with open(_STAT) as f:
            parts = f.readline().split()
        if not parts or parts[0] != "cpu":
            return None
        nums = [int(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0)  # idle + iowait
        return sum(nums), idle
    except (OSError, ValueError):
        return None


def load_avg() -> float | None:
    """1-minute load average (host)."""
    try:
        return os.getloadavg()[0]
    except OSError:
        return None
