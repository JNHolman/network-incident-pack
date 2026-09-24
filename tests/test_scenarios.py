import unittest

from incidentpack.evidence import mock_evidence
from incidentpack.scenarios import MOCK_SCENARIOS, apply_mock_scenario, validate_mock_scenario


class MockScenarioTests(unittest.TestCase):
    def test_supported_scenarios_are_stable(self):
        self.assertEqual(
            MOCK_SCENARIOS,
            (
                "baseline",
                "healthy",
                "dns-failure",
                "service-refused",
                "unreachable",
                "collector-timeout",
            ),
        )

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported mock scenario"):
            validate_mock_scenario("mystery-outage")

    def test_healthy_scenario_connects_all_requested_ports(self):
        evidence = mock_evidence(
            "10.20.30.40",
            "app.example.com",
            [443, 22],
            scenario="healthy",
        )
        self.assertEqual(evidence["meta"]["scenario"], "healthy")
        self.assertTrue(all(item["ok"] for item in evidence["tcp"]))
        self.assertEqual(evidence["health"]["status"], "healthy")
        self.assertEqual(evidence["health"]["reachability"], "healthy")

    def test_dns_failure_keeps_ip_reachability_but_degrades_health(self):
        evidence = mock_evidence(
            "10.20.30.40",
            "app.example.com",
            [443],
            scenario="dns-failure",
        )
        self.assertTrue(evidence["dns"]["error"])
        self.assertEqual(evidence["health"]["reachability"], "healthy")
        self.assertEqual(evidence["health"]["status"], "degraded")
        self.assertIn("DNS resolution failed", evidence["health"]["findings"])

    def test_dns_failure_requires_dns_name(self):
        with self.assertRaisesRegex(ValueError, "requires --dns-name"):
            mock_evidence("10.20.30.40", None, [443], scenario="dns-failure")

    def test_service_refused_proves_target_reachability(self):
        evidence = mock_evidence(
            "10.20.30.40",
            None,
            [443, 22],
            scenario="service-refused",
        )
        self.assertTrue(all(item["error_type"] == "connection_refused" for item in evidence["tcp"]))
        self.assertEqual(evidence["health"]["reachability"], "healthy")
        self.assertEqual(evidence["health"]["status"], "degraded")

    def test_unreachable_aligns_raw_and_structured_evidence(self):
        evidence = mock_evidence(
            "10.20.30.40",
            None,
            [443, 22],
            scenario="unreachable",
        )
        self.assertEqual(evidence["ping"]["status"], "failed")
        self.assertEqual(evidence["traceroute"]["status"], "partial")
        self.assertFalse(evidence["traceroute"]["target_reached"])
        self.assertTrue(all(item["error_type"] == "timeout" for item in evidence["tcp"]))
        self.assertEqual(evidence["health"]["reachability"], "failed")
        self.assertEqual(evidence["health"]["status"], "failed")

    def test_collector_timeout_changes_collection_quality_not_network_evidence(self):
        evidence = mock_evidence(
            "10.20.30.40",
            None,
            [443],
            scenario="collector-timeout",
        )
        self.assertEqual(evidence["health"]["status"], "healthy")
        self.assertEqual(evidence["collection_summary"]["commands_failed"], 1)
        self.assertEqual(evidence["collection_summary"]["commands_timed_out"], 1)

    def test_apply_scenario_does_not_mutate_source_evidence(self):
        source = mock_evidence("10.20.30.40", None, [443])
        changed = apply_mock_scenario(source, "service-refused")
        self.assertTrue(source["tcp"][0]["ok"])
        self.assertFalse(changed["tcp"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
