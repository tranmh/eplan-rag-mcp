import json
import os
import types
import uuid as real_uuid
from unittest.mock import MagicMock

import pytest

from api.actions import scripted

NOT_CONNECTED = {"success": False, "message": "Not connected to EPLAN. Call eplan_connect() first."}


@pytest.fixture
def captured(monkeypatch):
    """Capture scripts passed to _execute_script instead of running them."""
    scripts = []

    def fake_execute(script, timeout=30.0):
        scripts.append(script)
        return {"success": True, "results": {}}

    monkeypatch.setattr(scripted, "_execute_script", fake_execute)
    return scripts


# --- _identifier_error -------------------------------------------------------

def test_identifier_error_message():
    err = scripted._identifier_error("1abc", "filter_property")
    assert err["success"] is False
    assert err["error"].startswith("Invalid filter_property: '1abc'.")
    assert "valid identifier" in err["error"]
    assert "not starting with a digit" in err["error"]


def test_identifier_error_uses_repr_for_quotes():
    err = scripted._identifier_error('a"b', "x")
    assert "Invalid x: 'a\"b'." in err["error"]


# --- parts_db_query / parts_db_count ----------------------------------------

@pytest.mark.parametrize("bad", [
    "1PartNr", "Part Nr", "PartNr)", "PartNr;evil()", "Part-Nr", "Pärt", "a.b", " PartNr",
])
@pytest.mark.parametrize("func", [scripted.parts_db_query, scripted.parts_db_count])
def test_invalid_filter_property_rejected_before_execution(captured, func, bad):
    result = func(filter_property=bad, filter_value="x")
    assert result == scripted._identifier_error(bad, "filter_property")
    assert captured == []


@pytest.mark.skip(reason="aqaa: suspected bug - _CS_IDENTIFIER uses '$' which also matches before a trailing "
                         "newline, so 'PartNr\\n' is accepted as an identifier (B12)")
@pytest.mark.parametrize("func", [scripted.parts_db_query, scripted.parts_db_count])
def test_filter_property_with_trailing_newline_rejected(captured, func):
    result = func(filter_property="PartNr\n", filter_value="x")
    assert result["success"] is False
    assert captured == []


@pytest.mark.parametrize("good", ["PartNr", "_x", "ProductSubGroup", "a1_B2"])
def test_valid_filter_property_is_used_as_member(captured, good):
    scripted.parts_db_query(filter_property=good, filter_value="v")
    assert f".Where(p => p.{good}?.ToString()" in captured[0]


@pytest.mark.parametrize("bad", ["ten", "5; evil()", None, [1], "1.5"])
def test_parts_db_query_invalid_limit(captured, bad):
    result = scripted.parts_db_query(limit=bad)
    assert result["success"] is False
    assert result["error"].startswith("Invalid limit")
    assert captured == []


@pytest.mark.parametrize("limit", ["7", 7, 7.9])
def test_parts_db_query_limit_converted_to_int(captured, limit):
    scripted.parts_db_query(limit=limit)
    assert ".Take(7)" in captured[0] or "Take(7)" in captured[0]


def test_parts_db_query_defaults(captured):
    scripted.parts_db_query()
    script = captured[0]
    assert '"PartNr", "Description1", "Manufacturer", "ProductGroup", "ProductSubGroup"' in script
    assert "100" in script
    assert ".Where(" not in script


def test_parts_db_query_escapes_filter_value_and_properties(captured):
    scripted.parts_db_query(filter_property="PartNr", filter_value='a"); evil(); //',
                            return_properties=['Desc"1'])
    script = captured[0]
    assert 'Contains("a\\"); evil(); //")' in script
    assert '"Desc\\"1"' in script


def test_parts_db_query_ignores_property_without_value(captured):
    # no value -> no filter, identifier is not even interpolated
    scripted.parts_db_query(filter_property="bad name", filter_value=None)
    assert "bad name" not in captured[0]


# --- parts_db_create / parts_db_update --------------------------------------

def test_parts_db_create_escapes_part_number_and_properties(captured):
    scripted.parts_db_create('P"1\\x', {'Na"me': 'Va\nl', "ARTICLE_DESCR1": "ok"})
    script = captured[0]
    assert 'db.AddPart("P\\"1\\\\x")' in script
    assert 'string[] propNames = new string[] { "Na\\"me", "ARTICLE_DESCR1" };' in script
    assert 'string[] propValues = new string[] { "Va\\nl", "ok" };' in script
    assert "Part already exists" in script
    assert "{{RESULT_PATH}}" in script


def test_parts_db_create_without_properties(captured):
    scripted.parts_db_create("P1")
    assert "string[] propNames = new string[] {  };" in captured[0]


def test_parts_db_update_escapes_all_inputs(captured):
    scripted.parts_db_update('P"1', 'Prop"x', 'v\\"); evil(); //')
    script = captured[0]
    assert '"P\\"1"' in script
    assert "Prop\\\"x" in script
    assert 'prop.SetValue(part.Properties, "v\\\\\\"); evil(); //");' in script


# --- settings_set_* ---------------------------------------------------------

def test_settings_set_string_escapes_path_and_value(captured):
    scripted.settings_set_string('USER.A"B', 'x"\ny', index=2)
    assert 'SetStringSetting("USER.A\\"B", "x\\"\\ny", 2);' in captured[0]


@pytest.mark.parametrize("value, rendered", [(True, "true"), (False, "false"), (0, "false"), ("yes", "true")])
def test_settings_set_bool_renders_cs_literal(captured, value, rendered):
    scripted.settings_set_bool("USER.Flag", value)
    assert f'SetBoolSetting("USER.Flag", {rendered}, 0);' in captured[0]


def test_settings_set_int_casts_value_and_index(captured):
    scripted.settings_set_int("USER.N\\x", "5", index="1")
    assert 'SetNumericSetting("USER.N\\\\x", 5, 1);' in captured[0]


@pytest.mark.parametrize("func, value", [
    (scripted.settings_set_int, "5); evil(); //"),
    (scripted.settings_set_double, "1.0); evil(); //"),
])
def test_settings_set_numeric_rejects_injection(captured, func, value):
    with pytest.raises(ValueError):
        func("USER.N", value)
    assert captured == []


@pytest.mark.parametrize("func", [scripted.settings_set_string, scripted.settings_set_bool,
                                  scripted.settings_set_int, scripted.settings_set_double])
def test_settings_set_index_must_be_int(captured, func):
    with pytest.raises(ValueError):
        func("USER.N", 1, index="0); evil(); //")


def test_settings_set_double(captured):
    scripted.settings_set_double("USER.D", "2.5", index=3)
    assert 'SetDoubleSetting("USER.D", 2.5, 3);' in captured[0]


# --- _execute_script --------------------------------------------------------

class FakeManager:
    def __init__(self, write_result=None, fail_on=None, raise_on=None):
        self.calls = []
        self.write_result = write_result
        self.fail_on = fail_on
        self.raise_on = raise_on
        self.script_seen = None

    def execute_action(self, action, *args, **kwargs):
        self.calls.append(action)
        verb = action.split(" ")[0]
        path = action.split('"')[1]
        if verb == "RegisterScript":
            with open(path, encoding="utf-8") as f:
                self.script_seen = f.read()
        if verb == self.raise_on:
            raise RuntimeError("kaputt")
        if verb == self.fail_on:
            return {"success": False, "message": "denied"}
        if verb == "ExecuteScript" and self.write_result is not None:
            with open(self.result_path, "w", encoding="utf-8") as f:
                f.write(self.write_result)
        return {"success": True}


@pytest.fixture
def script_env(monkeypatch, tmp_path, fake_clock):
    monkeypatch.setattr(scripted, "SCRIPT_DIR", str(tmp_path / "generated"))
    monkeypatch.setattr(scripted, "RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setattr(scripted, "time", fake_clock)
    fixed = real_uuid.UUID("abcdef01-0000-0000-0000-000000000000")
    monkeypatch.setattr(scripted, "uuid", types.SimpleNamespace(uuid4=lambda: fixed))

    def install(manager):
        manager.result_path = os.path.join(str(tmp_path / "results"), "result_abcdef01.json")
        monkeypatch.setattr(scripted, "_get_connected_manager", lambda: (manager, None))
        return manager

    install.script_path = os.path.join(str(tmp_path / "generated"), "script_abcdef01.cs")
    install.result_path = os.path.join(str(tmp_path / "results"), "result_abcdef01.json")
    return install


def test_execute_script_not_connected(monkeypatch):
    monkeypatch.setattr(scripted, "_get_connected_manager", lambda: (None, dict(NOT_CONNECTED)))
    assert scripted._execute_script("x") == NOT_CONNECTED


def test_execute_script_success(script_env):
    mgr = script_env(FakeManager(write_result=json.dumps({"count": 3, "success": True})))

    result = scripted._execute_script('File.WriteAllText(@"{{RESULT_PATH}}", json);')

    assert result == {"success": True, "results": {"count": 3, "success": True}}
    assert script_env.result_path.replace("\\", "\\\\") in mgr.script_seen
    assert "{{RESULT_PATH}}" not in mgr.script_seen
    assert [c.split(" ")[0] for c in mgr.calls] == ["RegisterScript", "ExecuteScript", "UnregisterScript"]
    assert not os.path.exists(script_env.script_path)
    assert not os.path.exists(script_env.result_path)


@pytest.mark.parametrize("verb, prefix", [
    ("RegisterScript", "Failed to register script: denied"),
    ("ExecuteScript", "Failed to execute script: denied"),
])
def test_execute_script_register_or_execute_failure(script_env, verb, prefix):
    mgr = script_env(FakeManager(fail_on=verb))

    assert scripted._execute_script("x") == {"success": False, "message": prefix}
    assert mgr.calls[-1].startswith("UnregisterScript")
    assert not os.path.exists(script_env.script_path)


def test_execute_script_timeout(script_env, fake_clock):
    mgr = script_env(FakeManager())

    result = scripted._execute_script("x", timeout=2.0)

    assert result == {"success": False, "message": "Timeout waiting for script results"}
    assert 1.99 < sum(fake_clock.sleeps) < 2.5
    assert mgr.calls[-1].startswith("UnregisterScript")
    assert not os.path.exists(script_env.script_path)


def test_execute_script_default_timeout_is_30s(script_env, fake_clock):
    script_env(FakeManager())
    scripted._execute_script("x")
    assert 29.99 < sum(fake_clock.sleeps) < 30.5


def test_execute_script_invalid_json_reports_error_and_cleans_up(script_env):
    script_env(FakeManager(write_result="{broken"))

    result = scripted._execute_script("x")

    assert result["success"] is False
    assert result["message"]
    assert not os.path.exists(script_env.result_path)
    assert not os.path.exists(script_env.script_path)


def test_execute_script_exception_from_manager(script_env):
    script_env(FakeManager(raise_on="ExecuteScript"))
    assert scripted._execute_script("x") == {"success": False, "message": "kaputt"}
    assert not os.path.exists(script_env.script_path)


def test_execute_script_unregister_failure_does_not_mask_result(script_env):
    mgr = FakeManager(write_result="{}")
    original = mgr.execute_action

    def exec_with_unregister_error(action, *a, **k):
        if action.startswith("UnregisterScript"):
            raise OSError("locked")
        return original(action, *a, **k)

    mgr.execute_action = exec_with_unregister_error
    script_env(mgr)
    assert scripted._execute_script("x") == {"success": True, "results": {}}
    assert not os.path.exists(script_env.script_path)
