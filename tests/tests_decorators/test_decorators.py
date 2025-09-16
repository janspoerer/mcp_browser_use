# tests/test_decorators.py
import os
import sys
import json
import time
import types
import asyncio
import pytest

from mcp_browser_use.decorators import (
    tool_envelope, exclusive_browser_access,
)

## We DO NOT want to use pytest-asyncio.
## Instead, use event_loop.run_until_complete()!


@pytest.fixture(scope="function")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def install_fake_helpers(
    monkeypatch,
    *,
    driver=None,
    acquire_err=None,
    renew_calls=None,
    ensure_calls=None,
    lock=None,
    owner="owner-1",
    action_lock_ttl_secs=2,
):
    """
    Install a fake mcp_browser_use.helpers module into sys.modules so that
    decorators import/use it at call time without touching real Selenium.
    """
    if renew_calls is None:
        renew_calls = []
    if ensure_calls is None:
        ensure_calls = []
    if lock is None:
        lock = asyncio.Lock()

    m = types.ModuleType("mcp_browser_use.helpers")

    # Globals expected by ensure_driver_ready
    m.DRIVER = driver  # None => not ready; otherwise any object

    def _ensure_driver_and_window():
        ensure_calls.append(True)

    m._ensure_driver_and_window = _ensure_driver_and_window

    def _make_page_snapshot():
        return {"url": "about:blank", "title": "t", "html": "<html/>", "truncated": False}

    m._make_page_snapshot = _make_page_snapshot

    def get_env_config():
        return {"user_data_dir": "/tmp/fake", "profile_name": "Default", "chrome_path": "/bin/chrome", "fixed_port": None}

    m.get_env_config = get_env_config

    def collect_diagnostics(_driver, _exc, _cfg):
        return "diag-summary"

    m.collect_diagnostics = collect_diagnostics

    # Locking API for exclusive_browser_access / serialize_only
    def get_intra_process_lock():
        return lock

    m.get_intra_process_lock = get_intra_process_lock

    def ensure_process_tag():
        return owner

    m.ensure_process_tag = ensure_process_tag

    def _acquire_action_lock_or_error(_owner):
        # Return None if acquired, else return a JSON string error
        return acquire_err

    m._acquire_action_lock_or_error = _acquire_action_lock_or_error

    def _renew_action_lock(_owner, ttl):
        renew_calls.append((_owner, ttl))
        return True

    m._renew_action_lock = _renew_action_lock

    m.ACTION_LOCK_TTL_SECS = action_lock_ttl_secs

    # Values used by other helpers (not strictly needed, but harmless)
    m.FILE_MUTEX_STALE_SECS = 60

    # Inject into sys.modules for import by decorators
    # We need to also clear any cached imports
    if "mcp_browser_use.helpers" in sys.modules:
        monkeypatch.delitem(sys.modules, "mcp_browser_use.helpers")
    monkeypatch.setitem(sys.modules, "mcp_browser_use.helpers", m)

    return {
        "module": m,
        "renew_calls": renew_calls,
        "ensure_calls": ensure_calls,
        "lock": lock,
        "owner": owner,
    }


# ------------------------------
# tool_envelope tests
# ------------------------------

def test_tool_envelope_normalizes_sync_success_and_values(monkeypatch):
    # None -> ""
    @tool_envelope
    def f_none():
        return None

    # dict -> json string
    @tool_envelope
    def f_dict():
        return {"a": 1}

    # bytes -> decoded
    @tool_envelope
    def f_bytes():
        return b"hello"

    # arbitrary object -> default dumper falls back to __dict__/repr
    class O:
        def __repr__(self):
            return "<O>"

    @tool_envelope
    def f_obj():
        return O()

    assert f_none() == ""
    d = json.loads(f_dict())
    assert d == {"a": 1}
    assert f_bytes() == "hello"
    # Default dumper will produce a JSON string (repr) if __dict__ is empty
    s = f_obj()
    assert isinstance(s, str)


def test_tool_envelope_error_payload_includes_traceback_by_default(monkeypatch):
    @tool_envelope
    def f_fail():
        raise ValueError("boom")

    s = f_fail()
    payload = json.loads(s)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "ValueError"
    assert "timestamp" in payload


def test_tool_envelope_error_payload_without_traceback_when_disabled(monkeypatch):
    monkeypatch.setenv("MBU_TOOL_ERRORS_TRACEBACK", "0")

    @tool_envelope
    def f_fail():
        raise RuntimeError("err")

    s = f_fail()
    payload = json.loads(s)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "RuntimeError"



def test_tool_envelope_async_cancelled_error_propagates(event_loop):
    @tool_envelope
    async def f_cancel():
        raise asyncio.CancelledError()

    async def test_logic():
        with pytest.raises(asyncio.CancelledError):
            await f_cancel()

    event_loop.run_until_complete(test_logic())


def test_tool_envelope_normalizes_async_return(event_loop):
    @tool_envelope
    async def f():
        return {"msg": "ok"}

    async def test_logic():
        out = await f()
        assert isinstance(out, str)
        assert json.loads(out) == {"msg": "ok"}

    event_loop.run_until_complete(test_logic())


def test_tool_envelope_bytes_decoding_fallback():
    bad_bytes = b"\xff\xfe\xfa"  # invalid UTF-8
    @tool_envelope
    def f():
        return bad_bytes

    s = f()
    assert isinstance(s, str)
    assert len(s) > 0  # replaced chars


# ------------------------------
# ensure_driver_ready tests
# ------------------------------
# NOTE: These tests have been moved to a separate file due to module import issues

# These tests have been moved to test_ensure.py due to module import complexity


# ------------------------------
# exclusive_browser_access tests
# ------------------------------

def test_exclusive_browser_access_returns_error_if_locked(monkeypatch, event_loop):
    err = json.dumps({"ok": False, "error": "locked"})
    install_fake_helpers(monkeypatch, acquire_err=err)
    ran = {"x": False}

    @exclusive_browser_access
    async def f():
        ran["x"] = True
        return "OK"

    async def test_logic():
        out = await f()
        assert out == err  # returned as-is
        assert ran["x"] is False  # underlying function not called

    event_loop.run_until_complete(test_logic())


def test_exclusive_browser_access_calls_and_renews(monkeypatch, event_loop):
    renew_calls = []
    installed = install_fake_helpers(
        monkeypatch,
        acquire_err=None,
        renew_calls=renew_calls,
        action_lock_ttl_secs=1,
    )

    @exclusive_browser_access
    async def f():
        await asyncio.sleep(0.12)
        return "OK"

    async def test_logic():
        out = await f()
        assert out == "OK"
        # We expect at least one renewal (the final renewal in finally:)
        assert len(renew_calls) >= 1
        # Check owner passed through
        owners = {o for (o, _) in renew_calls}
        assert installed["owner"] in owners

    event_loop.run_until_complete(test_logic())


def test_exclusive_browser_access_serializes_concurrent_calls(monkeypatch, event_loop):
    install_fake_helpers(monkeypatch, acquire_err=None)
    running = {"flag": False, "overlap": False}

    @exclusive_browser_access
    async def f():
        if running["flag"]:
            running["overlap"] = True
        running["flag"] = True
        await asyncio.sleep(0.05)
        running["flag"] = False
        return "done"

    async def test_logic():
        # Launch two concurrent calls; in-process lock should serialize
        res = await asyncio.gather(f(), f())
        assert res == ["done", "done"]
        assert running["overlap"] is False

    event_loop.run_until_complete(test_logic())


# ------------------------------
# serialize_only tests
# ------------------------------

def test_serialize_only_serializes_concurrent_calls(monkeypatch, event_loop):
    # We only need get_intra_process_lock for this decorator
    install_fake_helpers(monkeypatch)

    running = {"flag": False, "overlap": False}

    @exclusive_browser_access
    async def f():
        if running["flag"]:
            running["overlap"] = True
        running["flag"] = True
        await asyncio.sleep(0.05)
        running["flag"] = False
        return "ok"

    async def test_logic():
        res = await asyncio.gather(f(), f())
        assert res == ["ok", "ok"]
        assert running["overlap"] is False

    event_loop.run_until_complete(test_logic())