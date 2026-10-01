from pathlib import Path

import pytest

from cynqra.worker_runtime import WorkerRuntimeError, list_files, read_file, run, safe_path, search_files, write_file


def test_paths_cannot_escape(tmp_path: Path):
    with pytest.raises(WorkerRuntimeError):
        safe_path(tmp_path, "../outside")
    with pytest.raises(WorkerRuntimeError):
        safe_path(tmp_path, "/etc/passwd")


def test_file_lifecycle_and_search(tmp_path: Path):
    write_file(tmp_path, "src/app.py", "print('ok')\n")
    assert read_file(tmp_path, "src/app.py") == "print('ok')\n"
    assert list_files(tmp_path) == ["src/app.py"]
    assert search_files(tmp_path, "print") == ["src/app.py"]


def test_commands_are_allowlisted(tmp_path: Path):
    result = run(tmp_path, ["python", "-c", "print('ok')"])
    assert result["passed"] is True
    with pytest.raises(WorkerRuntimeError):
        run(tmp_path, ["bash", "-lc", "echo nope"])


def test_runtime_does_not_forward_unallowlisted_environment(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CYNQRA_TEST_SECRET", "should-not-pass")
    result = run(tmp_path, ["python", "-c", "import os; raise SystemExit(1 if 'CYNQRA_TEST_SECRET' in os.environ else 0)"])
    assert result["passed"] is True
