# tests/_utils.py (or directly in your test file)
import sys, types, asyncio, json, importlib

def install_fake_helpers(monkeypatch, *, driver=None, allow_acquire=True):
    """
    Install a stub at 'mcp_browser_use.helpers' and set package attribute.
    Returns {'module': stub_module, 'ensure_calls': list}.
    """
    import mcp_browser_use as pkg

    # Drop any previously-loaded real helpers
    sys.modules.pop("mcp_browser_use.helpers", None)

    m = types.ModuleType("mcp_browser_use.helpers")

    # Track ensure calls
    ensure_calls = []
    def _ensure_driver_and_window():
        ensure_calls.append(1)
    m._ensure_driver_and_window = _ensure_driver_and_window

    # DRIVER gate used by ensure_driver_ready
    m.DRIVER = driver

    # serialize_only needs an asyncio.Lock
    _lock = asyncio.Lock()
    def get_intra_process_lock():
        return _lock
    m.get_intra_process_lock = get_intra_process_lock

    # exclusive_browser_access needs these
    m.ACTION_LOCK_TTL_SECS = 2
    def ensure_process_tag():
        return "TEST_TAG"
    m.ensure_process_tag = ensure_process_tag

    def _acquire_action_lock_or_error(owner):
        if allow_acquire:
            return None
        return json.dumps({"ok": False, "error": "locked", "owner": "other"})
    m._acquire_action_lock_or_error = _acquire_action_lock_or_error

    def _renew_action_lock(owner, ttl):
        pass
    m._renew_action_lock = _renew_action_lock

    # ensure_driver_ready extras
    def _make_page_snapshot():
        return {"url": "about:blank", "title": "", "html": "", "truncated": False}
    m._make_page_snapshot = _make_page_snapshot

    def collect_diagnostics(driver, exc, config):
        return "DIAG"
    m.collect_diagnostics = collect_diagnostics

    def get_env_config():
        return {}
    m.get_env_config = get_env_config

    # Install stub in import cache and on the package
    monkeypatch.setitem(sys.modules, "mcp_browser_use.helpers", m)
    monkeypatch.setattr(pkg, "helpers", m, raising=False)

    # Sanity check: an import now returns the stub
    reimported = importlib.import_module("mcp_browser_use.helpers")
    assert reimported is m
    return {"module": m, "ensure_calls": ensure_calls}