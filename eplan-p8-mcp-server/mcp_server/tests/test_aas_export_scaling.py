"""Scaling test for the AAS project export: EPLAN script round trips per export.

No EPLAN needed - the script executor is replaced by a counting fake.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.aas.export_ import export_project  # noqa: E402
from api.actions import scripted  # noqa: E402


def _count_script_executions(monkeypatch, tmp_path, n):
    calls = []

    def fake_execute_script(script_content, timeout=30.0):
        calls.append(script_content)
        return {"success": True, "results": {}}

    monkeypatch.setattr(scripted, "_execute_script", fake_execute_script)
    part_numbers = [f"VENDOR.PART-{i:05d}" for i in range(n)]
    result = export_project(
        "ScaleProject",
        str(tmp_path / f"project_{n}.aasx"),
        part_numbers=part_numbers,
        properties={"Customer": "ACME"},
    )
    assert result["success"], result
    return len(calls)


def test_export_project_script_executions_do_not_grow_with_parts(monkeypatch, tmp_path):
    # Every EPLAN script execution is a register/execute/poll/unregister round
    # trip; resolving the parts of a project must not cost one per part.
    n = 20
    calls_n = _count_script_executions(monkeypatch, tmp_path, n)
    calls_2n = _count_script_executions(monkeypatch, tmp_path, 2 * n)
    assert calls_2n <= calls_n, (
        f"EPLAN script executions grow with the part count: "
        f"{calls_n} for {n} parts, {calls_2n} for {2 * n} parts"
    )
