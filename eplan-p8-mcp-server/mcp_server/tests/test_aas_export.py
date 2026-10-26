import pytest

from api.actions import scripted
from api.aas import export_


@pytest.fixture
def script_calls(monkeypatch):
    """Count EPLAN script round trips instead of running them."""
    calls = []

    def fake_execute(script, timeout=30.0):
        calls.append(script)
        return {
            "success": True,
            "results": {
                "success": True,
                "found": True,
                "part": {"PartNr": "X", "Manufacturer": "ACME", "Description1": "Part"},
            },
        }

    monkeypatch.setattr(scripted, "_execute_script", fake_execute)
    return calls


def _export(tmp_path, script_calls, n):
    script_calls.clear()
    export_.export_project(
        "Proj",
        str(tmp_path / f"proj_{n}.aasx"),
        part_numbers=[f"PN-{i:04d}" for i in range(n)],
    )
    return len(script_calls)


@pytest.mark.skip(reason="aqaa: open bug, see report")
def test_export_project_part_lookups_do_not_scale_with_part_count(tmp_path, script_calls):
    # Each script execution is a full EPLAN round trip (register, execute,
    # poll for the result file, unregister), so looking parts up one by one
    # makes a project handover with hundreds of parts take minutes.
    n = 20
    calls_n = _export(tmp_path, script_calls, n)
    calls_2n = _export(tmp_path, script_calls, 2 * n)
    assert calls_n >= 1
    assert calls_2n <= 1.5 * calls_n, (
        f"export_project ran {calls_n} scripts for {n} parts and {calls_2n} for {2 * n}: "
        "one EPLAN round trip per part"
    )
