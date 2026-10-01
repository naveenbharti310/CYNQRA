import os
import tempfile
import unittest
from pathlib import Path

from cynqra.worker_runtime import WorkerRuntimeError, list_files, read_file, run, safe_path, search_files, write_file


class WorkerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_paths_cannot_escape(self):
        with self.assertRaises(WorkerRuntimeError):
            safe_path(self.root, "../outside")
        with self.assertRaises(WorkerRuntimeError):
            safe_path(self.root, "/etc/passwd")

    def test_file_lifecycle_and_search(self):
        write_file(self.root, "src/app.py", "print('ok')\n")
        self.assertEqual(read_file(self.root, "src/app.py"), "print('ok')\n")
        self.assertEqual(list_files(self.root), ["src/app.py"])
        self.assertEqual(search_files(self.root, "print"), ["src/app.py"])

    def test_commands_are_allowlisted(self):
        result = run(self.root, ["python", "-c", "print('ok')"])
        self.assertTrue(result["passed"])
        with self.assertRaises(WorkerRuntimeError):
            run(self.root, ["bash", "-lc", "echo nope"])

    def test_runtime_does_not_forward_unallowlisted_environment(self):
        old = os.environ.get("CYNQRA_TEST_SECRET")
        os.environ["CYNQRA_TEST_SECRET"] = "should-not-pass"
        try:
            result = run(self.root, ["python", "-c", "import os; print(os.environ.get('HOME','')); raise SystemExit(1 if 'CYNQRA_TEST_SECRET' in os.environ else 0)"])
            self.assertTrue(result["passed"])
            home = result["stdout"] if result.get("stdout") else ""
            self.assertNotIn(str(Path.home()), home)
        finally:
            if old is None:
                os.environ.pop("CYNQRA_TEST_SECRET", None)
            else:
                os.environ["CYNQRA_TEST_SECRET"] = old
