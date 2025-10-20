"""
Global constants and configuration defaults.
No dependencies - safe to import from anywhere.

This module extracts constants from helpers.py to break circular dependencies.
"""

import os

# ============================================================================
# Lock Configuration
# ============================================================================

ACTION_LOCK_TTL_SECS = int(os.getenv("MCP_ACTION_LOCK_TTL", "30"))
"""Time-to-live for action locks in seconds."""

ACTION_LOCK_WAIT_SECS = int(os.getenv("MCP_ACTION_LOCK_WAIT", "60"))
"""Maximum time to wait for action lock acquisition in seconds."""

FILE_MUTEX_STALE_SECS = int(os.getenv("MCP_FILE_MUTEX_STALE_SECS", "60"))
"""Consider file mutex stale after this many seconds."""


# ============================================================================
# Window Registry Configuration
# ============================================================================

WINDOW_REGISTRY_STALE_THRESHOLD = int(os.getenv("MCP_WINDOW_REGISTRY_STALE_SECS", "300"))
"""Consider window registry entry stale after this many seconds."""


# ============================================================================
# Rendering Configuration
# ============================================================================

MAX_SNAPSHOT_CHARS = int(os.getenv("MCP_MAX_SNAPSHOT_CHARS", "10000"))
"""Maximum characters in HTML snapshots."""


# ============================================================================
# Chrome Startup Configuration
# ============================================================================

START_LOCK_WAIT_SEC = 8.0
"""How long to wait to acquire the startup lock."""

RENDEZVOUS_TTL_SEC = 24 * 3600
"""How long a rendezvous file is considered valid (24 hours)."""


# ============================================================================
# Feature Flags
# ============================================================================

ALLOW_ATTACH_ANY = os.getenv("MCP_ATTACH_ANY_PROFILE", "0") == "1"
"""Allow attaching to any Chrome profile, not just the configured one."""


__all__ = [
    "ACTION_LOCK_TTL_SECS",
    "ACTION_LOCK_WAIT_SECS",
    "FILE_MUTEX_STALE_SECS",
    "WINDOW_REGISTRY_STALE_THRESHOLD",
    "MAX_SNAPSHOT_CHARS",
    "START_LOCK_WAIT_SEC",
    "RENDEZVOUS_TTL_SEC",
    "ALLOW_ATTACH_ANY",
]
