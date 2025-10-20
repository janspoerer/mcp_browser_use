"""Window registry for tracking browser window ownership across processes."""

import os
import json
import time
import psutil
from pathlib import Path
from typing import Dict, Any, Optional

import logging
logger = logging.getLogger(__name__)


def _window_registry_path() -> str:
    """Get path to window registry file for this profile."""
    from ..helpers import profile_key, get_env_config, LOCK_DIR

    key = profile_key(get_env_config())
    return str(Path(LOCK_DIR) / f"{key}.window_registry.json")


def _read_window_registry() -> Dict[str, Any]:
    """Read the window registry. Returns empty dict if not found or invalid."""
    path = _window_registry_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_window_registry(registry: Dict[str, Any]):
    """Write window registry atomically using temp file + rename."""
    path = _window_registry_path()
    tmp = f"{path}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass  # Non-critical if write fails


def _register_window(agent_id: str, target_id: str, window_id: Optional[int]):
    """Register a window as owned by this agent."""
    registry = _read_window_registry()
    registry[agent_id] = {
        "target_id": target_id,
        "window_id": window_id,
        "pid": os.getpid(),
        "last_heartbeat": time.time(),
        "created_at": time.time(),
    }
    _write_window_registry(registry)


def _update_window_heartbeat(agent_id: str):
    """Update the heartbeat timestamp for this agent's window."""
    registry = _read_window_registry()
    if agent_id in registry:
        registry[agent_id]["last_heartbeat"] = time.time()
        _write_window_registry(registry)


def _unregister_window(agent_id: str):
    """Remove this agent's window from the registry."""
    registry = _read_window_registry()
    if agent_id in registry:
        del registry[agent_id]
        _write_window_registry(registry)


def cleanup_orphaned_windows(driver, *, close_on_stale: bool = False):
    """
    Close windows owned by dead processes. Optionally close very stale windows if explicitly enabled.

    - Default behavior: only close when the owning PID no longer exists.
    - Stale heartbeats are logged but not closed by default to avoid killing idle sessions.

    Args:
        driver: Selenium WebDriver instance
        close_on_stale: If True, also close windows with stale heartbeats (default False)
    """
    from ..helpers import WINDOW_REGISTRY_STALE_THRESHOLD

    # If you have a registry/file lock, acquire it here
    # with _registry_lock():
    registry = _read_window_registry()
    now = time.time()

    to_remove: list[str] = []
    changed = False

    # Optional: detect already-missing targets to avoid noisy close attempts
    try:
        targets_resp = driver.execute_cdp_cmd("Target.getTargets", {})
        known_targets = {t.get("targetId") for t in targets_resp.get("targetInfos", [])}
    except Exception:
        known_targets = None  # fall back to best-effort without pre-check

    for agent_id, info in list(registry.items()):
        pid = info.get("pid")
        last_hb = info.get("last_heartbeat")
        target_id = info.get("target_id")

        # Robustness: skip weird records
        if target_id is None:
            logger.info(f"Removing registry entry with no target_id: agent={agent_id}, pid={pid}")
            to_remove.append(agent_id)
            changed = True
            continue

        # Compute states safely
        try:
            is_dead = bool(pid) and not psutil.pid_exists(int(pid))
        except Exception:
            # If pid cannot be parsed, treat as unknown (do not close)
            is_dead = False

        is_stale = False
        if isinstance(last_hb, (int, float)):
            try:
                is_stale = (now - float(last_hb)) > WINDOW_REGISTRY_STALE_THRESHOLD
            except Exception:
                is_stale = False

        # If target is already gone, just drop the registry entry
        if known_targets is not None and target_id not in known_targets:
            logger.info(f"Target already gone; pruning registry entry: agent={agent_id}, target={target_id}")
            to_remove.append(agent_id)
            changed = True
            continue

        # Decide whether to close
        should_close = is_dead or (close_on_stale and is_stale)
        if not should_close:
            if is_stale:
                logger.debug(f"Stale heartbeat but not closing (agent={agent_id}, pid={pid})")
            continue

        # Try to close the target
        try:
            res = driver.execute_cdp_cmd("Target.closeTarget", {"targetId": target_id})
            success = (res.get("success", True) if isinstance(res, dict) else True)
            logger.info(
                f"Closed orphaned window: agent={agent_id}, target={target_id}, "
                f"dead={is_dead}, stale={is_stale}, success={success}"
            )
        except Exception as e:
            # Even if we fail to close a window of a dead process, remove the entry to avoid leaks
            logger.debug(f"Could not close target {target_id} for agent {agent_id}: {e}")

        to_remove.append(agent_id)
        changed = True

    # Clean up registry
    if to_remove:
        for agent_id in to_remove:
            registry.pop(agent_id, None)
        _write_window_registry(registry)
        logger.info(f"Cleaned up {len(to_remove)} window registry entry(ies)")
    elif changed:
        # In case we changed something else
        _write_window_registry(registry)


__all__ = [
    '_window_registry_path',
    '_read_window_registry',
    '_write_window_registry',
    '_register_window',
    '_update_window_heartbeat',
    '_unregister_window',
    'cleanup_orphaned_windows',
]
