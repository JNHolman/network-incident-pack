import subprocess
import unittest
from unittest import mock

from incidentpack.runner import run_command


class CommandRunnerTests(unittest.TestCase):
    def test_success_returns_structured_result(self):
        completed = subprocess.CompletedProcess(
            args=["ping", "example.com"],
            returncode=0,
            stdout="reply\n",
            stderr="",
        )
        with mock.patch("incidentpack.runner.subprocess.run", return_value=completed):
            result = run_command(["ping", "example.com"], timeout=5)

        self.assertTrue(result["ok"])
        self.assertEqual(result["rc"], 0)
        self.assertEqual(result["stdout"], "reply")
        self.assertEqual(result["error_type"], "")
        self.assertFalse(result["timed_out"])
        self.assertGreaterEqual(result["duration_ms"], 0)

    def test_nonzero_exit_is_evidence_not_exception(self):
        completed = subprocess.CompletedProcess(
            args=["ping", "example.com"],
            returncode=1,
            stdout="",
            stderr="unreachable",
        )
        with mock.patch("incidentpack.runner.subprocess.run", return_value=completed):
            result = run_command(["ping", "example.com"], timeout=5)

        self.assertFalse(result["ok"])
        self.assertEqual(result["rc"], 1)
        self.assertEqual(result["error_type"], "nonzero_exit")
        self.assertFalse(result["timed_out"])

    def test_timeout_is_classified_and_preserves_partial_output(self):
        error = subprocess.TimeoutExpired(
            cmd=["traceroute", "example.com"],
            timeout=5,
            output="hop 1\n",
            stderr="",
        )
        with mock.patch("incidentpack.runner.subprocess.run", side_effect=error):
            result = run_command(["traceroute", "example.com"], timeout=5)

        self.assertFalse(result["ok"])
        self.assertIsNone(result["rc"])
        self.assertEqual(result["error_type"], "timeout")
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["stdout"], "hop 1")
        self.assertIn("timed out after 5s", result["stderr"])

    def test_missing_executable_is_classified(self):
        with mock.patch(
            "incidentpack.runner.subprocess.run",
            side_effect=FileNotFoundError("traceroute not found"),
        ):
            result = run_command(["traceroute", "example.com"], timeout=5)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "command_not_found")
        self.assertIn("traceroute not found", result["stderr"])

    def test_os_error_is_classified(self):
        with mock.patch(
            "incidentpack.runner.subprocess.run",
            side_effect=PermissionError("permission denied"),
        ):
            result = run_command(["netstat"], timeout=5)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "os_error")
        self.assertIn("PermissionError", result["stderr"])
