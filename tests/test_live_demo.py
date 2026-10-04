import io
import unittest
from contextlib import redirect_stdout

from incidentpack.application import IncidentPackResult
from lab.live_demo import DemoRenderer, build_demo_cases
from lab.local_sandbox import start_sandbox


class LiveDemoTests(unittest.TestCase):
    def test_demo_matrix_covers_success_and_real_failures(self):
        sandbox = start_sandbox(http_port=0, tcp_port=0, refused_port=0)
        try:
            cases = {case.name: case for case in build_demo_cases(sandbox)}
        finally:
            sandbox.close()

        self.assertEqual(set(cases), {"healthy", "service-refused", "dns-failure"})
        self.assertEqual(cases["healthy"].expected_status, "healthy")
        self.assertEqual(cases["service-refused"].expected_status, "degraded")
        self.assertEqual(cases["service-refused"].expected_reachability, "healthy")
        self.assertEqual(cases["dns-failure"].expected_status, "degraded")

    def test_service_refused_interpretation_explains_reachability(self):
        result = IncidentPackResult(
            evidence={
                "dns": {"name": "localhost", "answers": ["127.0.0.1"], "error": ""},
                "tcp": [
                    {"port": 50001, "ok": True, "error_type": ""},
                    {
                        "port": 50002,
                        "ok": False,
                        "error_type": "connection_refused",
                    },
                ],
                "health": {
                    "status": "degraded",
                    "reachability": "healthy",
                    "findings": ["1/2 requested TCP checks connected"],
                },
            },
            output_paths={"json": "report.json", "md": "report.md"},
            exit_code=0,
        )

        output = io.StringIO()
        with redirect_stdout(output):
            DemoRenderer.interpretation(result)

        text = output.getvalue()
        self.assertIn("One requested service is unavailable.", text)
        self.assertIn("TCP RST confirms the host remains reachable.", text)
        self.assertNotIn("1/2 requested TCP checks connected", text)


if __name__ == "__main__":
    unittest.main()
