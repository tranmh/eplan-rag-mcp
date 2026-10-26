import os
import sys
import types
from unittest.mock import MagicMock

import pytest

import eplan_connection as ec


@pytest.fixture
def manager(monkeypatch, tmp_path, fake_clock):
    # Keep generated scripts/logs out of the repository and time deterministic.
    monkeypatch.setattr(ec, "__file__", str(tmp_path / "eplan_connection.py"))
    monkeypatch.setattr(ec, "time", fake_clock)
    m = ec.EPLANConnectionManager()
    m.client = MagicMock()
    m.connected = True
    return m


@pytest.fixture
def fake_eplan_modules(monkeypatch):
    client = MagicMock()
    rc = types.ModuleType("Eplan.EplApi.RemoteClient")
    rc.EplanRemoteClient = MagicMock(return_value=client)
    system = types.ModuleType("System")
    system.TimeSpan = MagicMock()
    for name, mod in {
        "Eplan": types.ModuleType("Eplan"),
        "Eplan.EplApi": types.ModuleType("Eplan.EplApi"),
        "Eplan.EplApi.RemoteClient": rc,
        "System": system,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return client


# --- connect -----------------------------------------------------------------

def test_connect_returns_error_when_api_cannot_load(monkeypatch):
    m = ec.EPLANConnectionManager()

    def fail():
        m.last_error = "No EPLAN installation found"
        return False

    monkeypatch.setattr(m, "_setup_api", fail)
    assert m.connect() == {"success": False, "message": "No EPLAN installation found"}
    assert m.connected is False


def test_connect_success_with_explicit_port(fake_eplan_modules):
    fake_eplan_modules.Ping.return_value = True
    m = ec.EPLANConnectionManager()
    m._clr_initialized = True

    result = m.connect(port="50000")

    assert result == {"success": True, "message": "Connected to EPLAN at localhost:50000", "port": "50000"}
    assert m.connected is True
    assert m.port == "50000"
    fake_eplan_modules.Connect.assert_called_once()
    assert fake_eplan_modules.Connect.call_args[0][:2] == ("localhost", "50000")


def test_connect_autodetects_last_server_port(fake_eplan_modules, monkeypatch):
    fake_eplan_modules.Ping.return_value = True
    m = ec.EPLANConnectionManager()
    m._clr_initialized = True
    monkeypatch.setattr(m, "get_active_servers", lambda: [{"port": "1"}, {"port": "2"}])

    assert m.connect(host="eplanhost")["port"] == "2"


def test_connect_falls_back_to_default_port(fake_eplan_modules, monkeypatch):
    fake_eplan_modules.Ping.return_value = True
    m = ec.EPLANConnectionManager()
    m._clr_initialized = True
    monkeypatch.setattr(m, "get_active_servers", lambda: [])

    assert m.connect()["port"] == ec.EPLANConnectionManager.DEFAULT_PORT


def test_connect_ping_failure(fake_eplan_modules):
    fake_eplan_modules.Ping.return_value = False
    m = ec.EPLANConnectionManager()
    m._clr_initialized = True

    assert m.connect(port="1") == {"success": False, "message": "Connected but ping failed"}
    assert m.connected is False


def test_connect_exception_resets_state(fake_eplan_modules):
    fake_eplan_modules.Connect.side_effect = RuntimeError("refused")
    m = ec.EPLANConnectionManager()
    m._clr_initialized = True
    m.connected = True

    result = m.connect(port="1")

    assert result["success"] is False
    assert "Connection failed: refused" in result["message"]
    assert m.connected is False
    assert m.last_error == result["message"]


def test_ping_and_status_when_not_connected():
    m = ec.EPLANConnectionManager()
    assert m.ping() == {"alive": False, "message": "Not connected"}
    status = m.get_status()
    assert status["connected"] is False and status["port"] is None


def test_disconnect_disposes_client(manager):
    client = manager.client
    assert manager.disconnect() == {"success": True, "message": "Disconnected"}
    client.Disconnect.assert_called_once()
    client.Dispose.assert_called_once()
    assert manager.client is None and manager.connected is False


# --- execute_action ----------------------------------------------------------

def test_execute_action_not_connected():
    m = ec.EPLANConnectionManager()
    assert m.execute_action("anything") == {"success": False, "message": "Not connected"}


def test_execute_action_direct_when_not_quiet(manager):
    result = manager.execute_action("reports /TYPE:PROJECT")

    manager.client.ExecuteAction.assert_called_once_with("reports /TYPE:PROJECT")
    assert result["success"] is True
    assert result["action"] == "reports /TYPE:PROJECT"


@pytest.mark.parametrize("plumbing", ["RegisterScript", "executescript", "UnregisterScript"])
def test_execute_action_script_plumbing_runs_directly_even_in_quiet_mode(manager, plumbing):
    action = f'{plumbing} /ScriptFile:"C:\\x.cs"'
    assert manager.execute_action(action, quiet_mode=True)["success"] is True
    manager.client.ExecuteAction.assert_called_once_with(action)


def test_execute_action_direct_exception_is_reported(manager):
    manager.client.ExecuteAction.side_effect = RuntimeError("boom")
    result = manager.execute_action("act")
    assert result["success"] is False
    assert "boom" in result["message"]


def test_execute_action_quiet_generates_escaped_script(manager, monkeypatch):
    captured = {}

    def fake_run(action, script_path, result_path, started):
        with open(script_path, encoding="utf-8") as f:
            captured["script"] = f.read()
        return {"success": True, "from": "script"}

    monkeypatch.setattr(manager, "_run_generated_script", fake_run)

    result = manager.execute_action('XPrjActionProjectOpen /Project:"C:\\a b\\p.elk" /Mode:1', quiet_mode=True)

    assert result == {"success": True, "from": "script"}
    script = captured["script"]
    assert 'acc.AddParameter("Project", "C:\\\\a b\\\\p.elk");' in script
    assert 'acc.AddParameter("Mode", "1");' in script
    assert 'FindAction("XPrjActionProjectOpen")' in script
    assert "QuietModes.ShowNoDialogs" in script
    manager.client.ExecuteAction.assert_not_called()


def test_execute_action_quiet_legacy_template(manager, monkeypatch):
    monkeypatch.setenv("EPLAN_MCP_LEGACY_CLI", "1")
    captured = {}

    def fake_run(action, script_path, result_path, started):
        with open(script_path, encoding="utf-8") as f:
            captured["script"] = f.read()
        return {"success": True}

    monkeypatch.setattr(manager, "_run_generated_script", fake_run)
    manager.execute_action("act /K:v", quiet_mode=True)

    assert '"cli-legacy"' in captured["script"]
    assert "FindAction" not in captured["script"]


# --- _run_generated_script ---------------------------------------------------

def _paths(tmp_path):
    script = tmp_path / "s.cs"
    script.write_text("// script")
    return str(script), str(tmp_path / "r.json")


def test_run_generated_script_register_failure_cleans_up(manager, tmp_path, monkeypatch):
    script, result = _paths(tmp_path)
    calls = []

    def fake_exec(action, quiet_mode=False):
        calls.append(action)
        return {"success": not action.startswith("RegisterScript"), "message": "nope"}

    monkeypatch.setattr(manager, "execute_action", fake_exec)
    res = manager._run_generated_script("act", script, result, 0.0)

    assert res == {"success": False, "message": "Failed to register execution script: nope"}
    assert any(c.startswith("UnregisterScript") for c in calls)
    assert not os.path.exists(script)


def test_run_generated_script_timeout(manager, tmp_path, monkeypatch, fake_clock):
    script, result = _paths(tmp_path)
    monkeypatch.setattr(manager, "execute_action", lambda a, quiet_mode=False: {"success": True})

    res = manager._run_generated_script("act", script, result, 0.0)

    assert res == {"success": False, "message": "Timeout waiting for scripted action execution result"}
    assert 29.99 < sum(fake_clock.sleeps) < 31.0


def test_run_generated_script_returns_parsed_result_and_removes_files(manager, tmp_path, monkeypatch):
    script, result = _paths(tmp_path)

    def fake_exec(action, quiet_mode=False):
        if action.startswith("ExecuteScript"):
            with open(result, "w", encoding="utf-8") as f:
                f.write('{"success": true, "parameters": {"Value": "42"}}')
        return {"success": True}

    monkeypatch.setattr(manager, "execute_action", fake_exec)
    res = manager._run_generated_script("act", script, result, 0.0)

    assert res == {"success": True, "parameters": {"Value": "42"}}
    assert not os.path.exists(script) and not os.path.exists(result)


def test_run_generated_script_unparsable_result(manager, tmp_path, monkeypatch):
    script, result = _paths(tmp_path)

    def fake_exec(action, quiet_mode=False):
        if action.startswith("ExecuteScript"):
            with open(result, "w", encoding="utf-8") as f:
                f.write("{not json")
        return {"success": True}

    monkeypatch.setattr(manager, "execute_action", fake_exec)
    assert manager._run_generated_script("act", script, result, 0.0) == {
        "success": False, "message": "Could not parse action result file"}


# --- get_manager singleton ---------------------------------------------------

def test_get_manager_is_singleton_and_switches_version_until_loaded(monkeypatch):
    monkeypatch.setattr(ec, "_manager", None)
    first = ec.get_manager("2026")
    assert ec.get_manager() is first
    second = ec.get_manager("2027")
    assert second is not first and second.target_version == "2027"
    second._clr_initialized = True
    assert ec.get_manager("2026") is second
