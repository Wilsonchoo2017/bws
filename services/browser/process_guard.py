"""OS-level browser process management.

Handles killing stale Camoufox/Firefox processes and clearing
profile lock files left by crashed browsers.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from pathlib import Path

logger = logging.getLogger("bws.browser.process_guard")


def clear_stale_profile_lock(profile_path: Path) -> None:
    """Remove Firefox profile lock files left by a crashed browser."""
    for lock_name in (".parentlock", "parent.lock", "lock"):
        lock_file = profile_path / lock_name
        if lock_file.exists():
            logger.info("Removing stale profile lock: %s", lock_file)
            lock_file.unlink(missing_ok=True)


def kill_browser_processes(profile_name: str) -> None:
    """Force-kill any Camoufox/Firefox processes for a profile."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", f"{profile_name}-profile"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in proc.stdout.strip().split() if p.isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                logger.info("Force-killed browser process pid=%d (%s)", pid, profile_name)
            except ProcessLookupError:
                pass
    except Exception:
        logger.debug("Failed to kill browser processes for %s", profile_name, exc_info=True)


def kill_browser_processes_graceful(profile_name: str) -> None:
    """Send SIGTERM (graceful) to browser processes for a profile."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", profile_name],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in proc.stdout.strip().split() if p.isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                logger.warning("Killed orphaned browser process pid=%d (%s)", pid, profile_name)
            except ProcessLookupError:
                pass
    except Exception:
        logger.debug("Failed to clean up orphaned browsers for %s", profile_name)
