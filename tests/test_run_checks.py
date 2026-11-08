"""Runner selection and failure contracts; no camera, sockets or firmware inputs."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "run_checks.py"
spec = importlib.util.spec_from_file_location("checks_under_test", SOURCE)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for directory in ("tools", "tests", "camera_client/tests"):
            (self.root / directory).mkdir(parents=True)
        for name in ("test_client.py", "test_workflow.py", "test_transport.py"):
            (self.root / "camera_client/tests" / name).write_text("")

    def invoke(self, args, failure=None):
        output = io.StringIO()
        with patch.object(checks, "ROOT", self.root), \
                patch.object(sys, "argv", ["run_checks.py", *args]), \
                patch.object(sys, "path", sys.path.copy()), \
                patch.object(sys, "dont_write_bytecode", True), \
                patch.object(checks, "run_tests", side_effect=failure) as run, \
                redirect_stdout(output):
            checks.main()
        return run.call_args_list, output.getvalue()

    def test_default_selection_and_message_unchanged(self):
        calls, output = self.invoke([])
        self.assertEqual([c.args for c in calls], [
            (self.root, "test_oly_container.py"),
            (self.root, "test_penf_emulator_performance.py"),
            (self.root / "camera_client", "test_*.py"),
        ])
        self.assertNotIn("Omitted", output)
        self.assertTrue(output.endswith("Checks passed. No camera was contacted or flashed.\n"))

    def test_portable_selection_reports_omissions_including_new_suite(self):
        (self.root / "camera_client/tests/test_future.py").write_text("")
        calls, output = self.invoke(["--portable"])
        self.assertEqual([c.args for c in calls], [
            (self.root, "test_oly_container.py"),
            (self.root, "test_penf_emulator_performance.py"),
            (self.root / "camera_client", "test_transport.py"),
        ])
        for name in ("test_client.py", "test_workflow.py", "test_future.py"):
            self.assertIn("camera_client/tests/" + name, output)
        self.assertNotIn("camera_client/tests/test_transport.py", output)
        self.assertIn("partial coverage", output)
        self.assertNotIn("\nChecks passed.", output)

    def test_portable_rejects_native_and_loopback_before_checks(self):
        for option in ("--native", "--loopback"):
            with self.subTest(option=option), redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    self.invoke(["--portable", option])
                self.assertEqual(error.exception.code, 2)

    def test_unexpected_tool_import_error_is_not_suppressed(self):
        (self.root / "tools/broken.py").write_text("import missing_dependency\n")
        with patch.object(checks.importlib, "import_module", side_effect=ImportError("missing_dependency")):
            with self.assertRaisesRegex(ImportError, "missing_dependency"):
                self.invoke(["--portable"])

    def test_real_selected_test_failure_makes_cli_nonzero(self):
        # Execute the actual CLI/child-test path on a synthetic tree, not mocked run_tests.
        runner = self.root / "tools/run_checks.py"
        runner.write_bytes(SOURCE.read_bytes())
        passing = "import unittest\nclass Example(unittest.TestCase):\n    def test_case(self): self.assertTrue(True)\n"
        for name in ("test_oly_container.py", "test_penf_emulator_performance.py"):
            (self.root / "tests" / name).write_text(passing)
        (self.root / "camera_client/tests/test_transport.py").write_text(passing.replace("assertTrue(True)", "fail('sentinel selected-suite failure')"))
        result = subprocess.run([sys.executable, str(runner), "--portable"],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sentinel selected-suite failure", result.stderr)
        self.assertNotIn("Selected portable checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
