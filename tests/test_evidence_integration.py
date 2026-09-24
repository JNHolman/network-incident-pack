import unittest
from unittest import mock

import incident_pack


class EvidenceIntegrationTests(unittest.TestCase):
    def test_live_collection_builds_structured_local_state_and_health(self):
        commands = [
            ["ip", "addr"],
            ["ip", "route"],
            ["ip", "neigh"],
            ["ping", "-c", "4", "10.20.30.40"],
            ["traceroute", "-n", "10.20.30.40"],
            ["ss", "-tulpn"],
        ]
        command_results = [
            {
                "cmd": "ip addr",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN\n"
                    "    inet 127.0.0.1/8 scope host lo\n"
                    "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 00:11:22:33:44:55 brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 192.168.1.25/24 scope global eth0"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 1.0,
            },
            {
                "cmd": "ip route",
                "rc": 0,
                "ok": True,
                "stdout": "default via 192.168.1.1 dev eth0 metric 100",
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 1.0,
            },
            {
                "cmd": "ip neigh",
                "rc": 0,
                "ok": True,
                "stdout": "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE",
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 1.0,
            },
            {
                "cmd": "ping -c 4 10.20.30.40",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "4 packets transmitted, 4 received, 0% packet loss, time 3000ms\n"
                    "rtt min/avg/max/mdev = 10.000/12.000/14.000/1.000 ms"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 1.0,
            },
            {
                "cmd": "traceroute -n 10.20.30.40",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "traceroute to 10.20.30.40 (10.20.30.40), 30 hops max\n"
                    " 1  192.168.1.1  1.0 ms  1.1 ms  1.2 ms\n"
                    " 2  10.20.30.40  12.0 ms  12.1 ms  12.2 ms"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 1.0,
            },
            {
                "cmd": "ss -tulpn",
                "rc": 0,
                "ok": True,
                "stdout": "",
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 1.0,
            },
        ]

        with (
            mock.patch("incidentpack.evidence.platform.node", return_value="lab-host"),
            mock.patch("incidentpack.evidence.detect_os", return_value="linux"),
            mock.patch("incidentpack.evidence.os_commands", return_value=commands),
            mock.patch("incidentpack.evidence.run_host_commands", return_value=command_results),
            mock.patch(
                "incidentpack.evidence.run_tcp_checks",
                return_value=[
                    {
                        "host": "10.20.30.40",
                        "port": 443,
                        "ok": True,
                        "error": "",
                        "error_type": "",
                        "attempts": 1,
                        "duration_ms": 1.0,
                    }
                ],
            ),
            mock.patch(
                "incidentpack.evidence.prompt_context",
                return_value={
                    "impact": "",
                    "symptoms": "",
                    "scope": "",
                    "recent_changes": "",
                    "actions_taken": "",
                },
            ),
        ):
            evidence = incident_pack.collect_live_evidence(
                target="10.20.30.40",
                dns_name=None,
                ports=[443],
                timeout=5,
                non_interactive=True,
            )

        self.assertEqual(evidence["schema_version"], 2)
        self.assertEqual(evidence["interfaces"]["status"], "healthy")
        self.assertEqual(evidence["interfaces"]["usable_up_count"], 1)
        self.assertTrue(evidence["routes"]["default_route"])
        self.assertEqual(evidence["routes"]["default_gateway"], "192.168.1.1")
        self.assertEqual(evidence["neighbors"]["neighbor_count"], 1)
        self.assertEqual(evidence["health"]["reachability"], "healthy")
        self.assertEqual(evidence["health"]["status"], "healthy")

    def test_markdown_surfaces_health_and_local_state(self):
        evidence = incident_pack.mock_evidence(
            "10.20.30.40", "app.example.com", [443, 80, 22]
        )
        markdown = incident_pack.build_markdown(evidence)
        self.assertIn("Report Schema: `2`", markdown)
        self.assertIn("## Health Summary", markdown)
        self.assertIn("Overall: **DEGRADED**", markdown)
        self.assertIn("Reachability: **HEALTHY**", markdown)
        self.assertIn("Interfaces: **HEALTHY**", markdown)
        self.assertIn("Routes: **HEALTHY**", markdown)
        self.assertIn("Neighbors: **HEALTHY**", markdown)


if __name__ == "__main__":
    unittest.main()
