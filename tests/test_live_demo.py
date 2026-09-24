import unittest

from lab.live_demo import build_demo_cases
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


if __name__ == "__main__":
    unittest.main()
