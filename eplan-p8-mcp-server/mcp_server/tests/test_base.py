from unittest.mock import MagicMock

import pytest

from api.actions import _base
from api.actions._base import QuietManagerWrapper, _build_action, _get_connected_manager

# --- _build_action -----------------------------------------------------------

def test_build_action_without_params_returns_name():
    assert _build_action("XEsSetProjectPropertyAction") == "XEsSetProjectPropertyAction"


def test_build_action_joins_params_with_single_spaces():
    assert _build_action("export", TYPE="PDF", PAGES=3) == "export /TYPE:PDF /PAGES:3"


@pytest.mark.parametrize("value, rendered", [(True, "1"), (False, "0")])
def test_build_action_renders_booleans_as_digits(value, rendered):
    assert _build_action("act", FLAG=value) == f"act /FLAG:{rendered}"


@pytest.mark.parametrize("empty", [None, ""])
def test_build_action_omits_none_and_empty_values(empty):
    assert _build_action("act", A=empty, B="x", C=empty) == "act /B:x"


def test_build_action_keeps_falsy_non_empty_values():
    # 0 and False are real values, only None and "" are skipped
    assert _build_action("act", N=0, F=False) == "act /N:0 /F:0"


def test_build_action_quotes_strings_with_spaces():
    assert _build_action("open", PROJECT=r"C:\My Projects\a.elk") == r'open /PROJECT:"C:\My Projects\a.elk"'


def test_build_action_does_not_double_quote_already_quoted_value():
    assert _build_action("open", PROJECT='"C:\\a b.elk"') == 'open /PROJECT:"C:\\a b.elk"'


def test_build_action_does_not_quote_strings_without_spaces():
    assert _build_action("open", PROJECT=r"C:\x.elk") == r"open /PROJECT:C:\x.elk"


# --- _get_connected_manager / QuietManagerWrapper ----------------------------

def test_get_connected_manager_not_connected_returns_error(monkeypatch):
    fake = MagicMock(connected=False)
    monkeypatch.setattr(_base, "get_manager", lambda: fake)

    manager, error = _get_connected_manager()

    assert manager is None
    assert error == {"success": False, "message": "Not connected to EPLAN. Call eplan_connect() first."}
    fake.execute_action.assert_not_called()


def test_get_connected_manager_connected_returns_wrapper(monkeypatch):
    fake = MagicMock(connected=True)
    monkeypatch.setattr(_base, "get_manager", lambda: fake)

    manager, error = _get_connected_manager()

    assert error is None
    assert isinstance(manager, QuietManagerWrapper)
    assert manager.manager is fake


@pytest.mark.parametrize("kwargs", [{}, {"quiet_mode": False}, {"quiet_mode": True}])
def test_wrapper_forces_quiet_mode(kwargs):
    inner = MagicMock()
    inner.execute_action.return_value = {"success": True}
    wrapper = QuietManagerWrapper(inner)

    result = wrapper.execute_action("someAction /X:1", **kwargs)

    assert result == {"success": True}
    inner.execute_action.assert_called_once_with("someAction /X:1", quiet_mode=True)


def test_wrapper_passes_other_attributes_through():
    inner = MagicMock()
    inner.port = "49152"
    inner.get_status.return_value = {"connected": True}
    wrapper = QuietManagerWrapper(inner)

    assert wrapper.port == "49152"
    assert wrapper.get_status() == {"connected": True}


def test_execute_with_quiet_mode_returns_error_when_not_connected(monkeypatch):
    monkeypatch.setattr(_base, "get_manager", lambda: MagicMock(connected=False))
    assert _base._execute_with_quiet_mode("act")["success"] is False


def test_execute_with_quiet_mode_delegates_quietly(monkeypatch):
    inner = MagicMock(connected=True)
    inner.execute_action.return_value = {"success": True}
    monkeypatch.setattr(_base, "get_manager", lambda: inner)

    assert _base._execute_with_quiet_mode("act /A:b") == {"success": True}
    inner.execute_action.assert_called_once_with("act /A:b", quiet_mode=True)
