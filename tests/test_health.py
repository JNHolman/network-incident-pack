import unittest

from incidentpack.health import evaluate_health


def base_evidence():
    return {
        "dns": {"name": "app.example.com", "answers": ["10.0.0.10"], "error": ""},
        "ping": {"status": "healthy"},
        "traceroute": {"status": "complete"},
        "tcp": [{"port": 443, "ok": True}],
        "interfaces": {"status": "healthy"},
        "routes": {"status": "healthy"},
        "neighbors": {"status": "healthy", "unresolved_count": 0},
    }


class HealthTests(unittest.TestCase):
    def test_all_good_is_healthy(self):
        result = evaluate_health(base_evidence())
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["reachability"], "healthy")

    def test_ping_failure_does_not_override_successful_tcp(self):
        evidence = base_evidence()
        evidence["ping"] = {"status": "failed"}
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "healthy")
        self.assertEqual(result["status"], "healthy")

    def test_all_tcp_fail_but_ping_reaches_target_is_degraded(self):
        evidence = base_evidence()
        evidence["tcp"] = [
            {"port": 443, "ok": False},
            {"port": 22, "ok": False},
        ]
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "healthy")
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(any("TCP" in finding for finding in result["findings"]))

    def test_mixed_tcp_is_degraded(self):
        evidence = base_evidence()
        evidence["tcp"] = [{"port": 443, "ok": True}, {"port": 22, "ok": False}]
        result = evaluate_health(evidence)
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["components"]["tcp"]["status"], "degraded")

    def test_reachability_is_failed_when_multiple_independent_checks_fail(self):
        evidence = base_evidence()
        evidence["ping"] = {"status": "failed"}
        evidence["traceroute"] = {"status": "partial"}
        evidence["tcp"] = [{"port": 443, "ok": False}]
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "failed")
        self.assertEqual(result["status"], "failed")

    def test_dns_failure_degrades_reachable_target(self):
        evidence = base_evidence()
        evidence["dns"] = {"name": "app.example.com", "answers": [], "error": "gaierror"}
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "healthy")
        self.assertEqual(result["status"], "degraded")

    def test_no_default_route_is_flagged_but_does_not_override_proven_target_reachability(self):
        evidence = base_evidence()
        evidence["routes"] = {"status": "degraded"}
        result = evaluate_health(evidence)
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(any("No default route" in finding for finding in result["findings"]))

    def test_route_problem_contributes_when_target_reachability_is_not_proven(self):
        evidence = base_evidence()
        evidence["routes"] = {"status": "degraded"}
        evidence["ping"] = {"status": "failed"}
        evidence["traceroute"] = {"status": "unknown"}
        evidence["tcp"] = []
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "degraded")
        self.assertEqual(result["status"], "degraded")

    def test_neighbor_unresolved_is_informational_to_overall_status(self):
        evidence = base_evidence()
        evidence["neighbors"] = {"status": "degraded", "unresolved_count": 2}
        result = evaluate_health(evidence)
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(any("Neighbor cache" in finding for finding in result["findings"]))


    def test_connection_refused_proves_reachability_but_service_is_failed(self):
        evidence = base_evidence()
        evidence["ping"] = {"status": "failed"}
        evidence["traceroute"] = {"status": "unknown"}
        evidence["tcp"] = [
            {"port": 22, "ok": False, "error_type": "connection_refused"}
        ]
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "healthy")
        self.assertEqual(result["components"]["tcp"]["status"], "failed")
        self.assertEqual(result["status"], "degraded")

    def test_tcp_timeout_does_not_prove_reachability(self):
        evidence = base_evidence()
        evidence["ping"] = {"status": "failed"}
        evidence["traceroute"] = {"status": "unknown"}
        evidence["tcp"] = [{"port": 443, "ok": False, "error_type": "timeout"}]
        result = evaluate_health(evidence)
        self.assertEqual(result["reachability"], "failed")
        self.assertEqual(result["status"], "failed")

    def test_no_target_evidence_is_unknown(self):
        result = evaluate_health({})
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reachability"], "unknown")


if __name__ == "__main__":
    unittest.main()
