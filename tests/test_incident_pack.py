import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import incident_pack
from incidentpack.integrations.netbox import NetBoxDevice


class IncidentPackTests(unittest.TestCase):
    def test_sanitize_filename_component(self):
        self.assertEqual(incident_pack.sanitize_filename_component("Js MBP/2.lan"), "Js-MBP-2.lan")
        self.assertEqual(incident_pack.sanitize_filename_component("***", default="demo"), "demo")

    def test_normalize_ports_deduplicates_preserves_order(self):
        self.assertEqual(incident_pack.normalize_ports([443, 80, 443, 22, 80]), [443, 80, 22])

    def test_validate_ports_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            incident_pack.validate_ports([0, 443, 70000])

    def test_validate_md_max_lines_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            incident_pack.validate_md_max_lines(0)

    def test_validate_timeout_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            incident_pack.validate_timeout(0)

    def test_build_markdown_includes_mode(self):
        evidence = incident_pack.mock_evidence("1.1.1.1", "example.com", [443, 53])
        markdown = incident_pack.build_markdown(evidence, md_max_lines=10)
        self.assertIn("- Mode: `mock`", markdown)
        self.assertIn("TCP 1.1.1.1:443: ✅ connect ok", markdown)
        self.assertIn("Traceroute: **COMPLETE**", markdown)

    def test_mock_evidence_can_reflect_collection_policy(self):
        evidence = incident_pack.mock_evidence(
            "1.1.1.1",
            "example.com",
            [443],
            timeout=9,
            tcp_timeout=1.5,
            tcp_attempts=3,
            max_workers=2,
        )
        self.assertEqual(
            evidence["collection"],
            {
                "max_workers": 2,
                "command_timeout_seconds": 9,
                "tcp_timeout_seconds": 1.5,
                "tcp_max_attempts": 3,
            },
        )

    def test_build_markdown_includes_servicenow_integration_result(self):
        evidence = incident_pack.mock_evidence("1.1.1.1", "example.com", [443])
        evidence["integrations"] = {
            "servicenow": {"status": "updated", "incident": "INC0012345"}
        }
        markdown = incident_pack.build_markdown(evidence)
        self.assertIn("## Integrations", markdown)
        self.assertIn("ServiceNow `INC0012345`: **UPDATED**", markdown)

    def test_build_markdown_truncates_long_output(self):
        evidence = incident_pack.mock_evidence("1.1.1.1", "example.com", [443])
        evidence["commands"] = [
            {
                "cmd": "demo",
                "rc": 0,
                "stdout": "\n".join(f"line-{i}" for i in range(6)),
                "stderr": "",
            }
        ]
        markdown = incident_pack.build_markdown(evidence, md_max_lines=3)
        self.assertIn("line-0", markdown)
        self.assertIn("line-2", markdown)
        self.assertIn("truncated; full output preserved in JSON", markdown)
        self.assertNotIn("line-5", markdown)

    def test_mock_evidence_is_deterministic_and_demo_safe(self):
        evidence = incident_pack.mock_evidence("1.1.1.1", "example.com", [443, 53])
        self.assertEqual(evidence["meta"]["host"], "demo-host")
        self.assertEqual(evidence["meta"]["timestamp_utc"], incident_pack.MOCK_TIMESTAMP_UTC)
        self.assertEqual(evidence["meta"]["os"], incident_pack.MOCK_OS)
        self.assertEqual(evidence["ping"]["status"], "healthy")
        self.assertEqual(evidence["ping"]["packets_received"], 4)
        self.assertEqual(evidence["traceroute"]["status"], "complete")
        self.assertTrue(evidence["traceroute"]["target_reached"])
        self.assertEqual(evidence["traceroute"]["timeout_hops"], 1)

    def test_resolve_captures_dns_failure(self):
        with mock.patch("incidentpack.host_context.socket.getaddrinfo", side_effect=OSError("dns failed")):
            result = incident_pack.resolve("bad.example")
        self.assertEqual(result["answers"], [])
        self.assertIn("dns failed", result["error"])

    def test_run_compatibility_wrapper_uses_structured_runner(self):
        expected = {
            "cmd": "ping example.com",
            "rc": 0,
            "ok": True,
            "stdout": "ok",
            "stderr": "",
            "error_type": "",
            "timed_out": False,
            "duration_ms": 1.0,
        }
        with mock.patch("incident_pack.run_command", return_value=expected) as runner:
            result = incident_pack.run(["ping", "example.com"], timeout=9)
        runner.assert_called_once_with(["ping", "example.com"], timeout=9)
        self.assertEqual(result, expected)

    def test_os_commands_linux(self):
        with mock.patch("incidentpack.host_context.detect_os", return_value="linux"):
            commands = incident_pack.os_commands("example.com")
        self.assertEqual(commands[0], ["ip", "addr"])
        self.assertIn(["ss", "-tulpn"], commands)

    def test_os_commands_macos(self):
        with mock.patch("incidentpack.host_context.detect_os", return_value="macos"):
            commands = incident_pack.os_commands("example.com")
        self.assertEqual(commands[0], ["ifconfig"])
        self.assertIn(["traceroute", "-n", "example.com"], commands)

    def test_os_commands_windows(self):
        with mock.patch("incidentpack.host_context.detect_os", return_value="windows"):
            commands = incident_pack.os_commands("example.com")
        self.assertEqual(commands[0], ["ipconfig", "/all"])
        self.assertIn(["tracert", "-d", "example.com"], commands)

    def test_prompt_context_handles_non_interactive(self):
        result = incident_pack.prompt_context(non_interactive=True)
        self.assertTrue(all(value == "" for value in result.values()))
        self.assertEqual(
            set(result),
            {"impact", "symptoms", "scope", "recent_changes", "actions_taken"},
        )

    def test_prompt_context_handles_eof(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch("builtins.input", side_effect=EOFError):
                result = incident_pack.prompt_context(non_interactive=False)
        self.assertTrue(all(value == "" for value in result.values()))

    def test_main_rejects_invalid_ports(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                incident_pack.main(["--target", "1.1.1.1", "--ports", "0"])
        self.assertEqual(ctx.exception.code, 2)

    def test_main_rejects_invalid_md_max_lines(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                incident_pack.main(["--target", "1.1.1.1", "--md-max-lines", "0"])
        self.assertEqual(ctx.exception.code, 2)

    def test_main_rejects_invalid_timeout(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                incident_pack.main(["--target", "1.1.1.1", "--timeout", "0"])
        self.assertEqual(ctx.exception.code, 2)

    def test_main_rejects_blank_target(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                incident_pack.main(["--target", "   "])
        self.assertEqual(ctx.exception.code, 2)

    def test_main_rejects_device_without_config(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                incident_pack.main(["--device", "app01", "--mock"])
        self.assertEqual(ctx.exception.code, 2)

    def test_collect_live_evidence_uses_injected_helpers(self):
        command_results = [
            {
                "cmd": "ping 1.1.1.1",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "4 packets transmitted, 4 received, 0% packet loss, time 3000ms\n"
                    "rtt min/avg/max/mdev = 10.000/12.000/14.000/1.000 ms"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 5.0,
            },
            {
                "cmd": "traceroute -n 1.1.1.1",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "traceroute to 1.1.1.1 (1.1.1.1), 30 hops max, 60 byte packets\n"
                    " 1  192.168.1.1  1.000 ms  1.100 ms  1.200 ms\n"
                    " 2  1.1.1.1  12.000 ms  12.100 ms  12.200 ms"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 7.0,
            },
        ]
        with (
            mock.patch("incidentpack.evidence.platform.node", return_value="lab-host"),
            mock.patch("incidentpack.host_context.detect_os", return_value="linux"),
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
            mock.patch(
                "incidentpack.evidence.resolve",
                return_value={"name": "app.example.com", "answers": ["1.1.1.1"], "error": ""},
            ),
            mock.patch(
                "incidentpack.evidence.run_tcp_checks",
                return_value=[
                    {
                        "host": "1.1.1.1",
                        "port": 443,
                        "ok": True,
                        "error": "",
                        "error_type": "",
                        "attempts": 1,
                        "duration_ms": 1.0,
                    }
                ],
            ) as tcp_batch,
            mock.patch(
                "incidentpack.evidence.os_commands",
                return_value=[["ping", "1.1.1.1"], ["traceroute", "-n", "1.1.1.1"]],
            ),
            mock.patch(
                "incidentpack.evidence.run_host_commands", return_value=command_results
            ) as host_batch,
        ):
            evidence = incident_pack.collect_live_evidence(
                target="1.1.1.1",
                dns_name="app.example.com",
                ports=[443],
                timeout=5,
                non_interactive=True,
                tcp_timeout=2.5,
                tcp_attempts=3,
                max_workers=2,
            )
        self.assertEqual(evidence["meta"]["host"], "lab-host")
        self.assertEqual(evidence["meta"]["mode"], "live")
        self.assertEqual(evidence["dns"]["answers"], ["1.1.1.1"])
        self.assertEqual(evidence["commands"][0]["rc"], 0)
        self.assertEqual(evidence["ping"]["status"], "healthy")
        self.assertEqual(evidence["ping"]["avg_latency_ms"], 12.0)
        self.assertEqual(evidence["traceroute"]["status"], "complete")
        self.assertTrue(evidence["traceroute"]["target_reached"])
        self.assertEqual(evidence["traceroute"]["hop_count"], 2)
        self.assertEqual(evidence["collection"]["max_workers"], 2)
        tcp_batch.assert_called_once_with(
            "1.1.1.1", [443], timeout=2.5, max_attempts=3, max_workers=2
        )
        host_batch.assert_called_once_with(
            [["ping", "1.1.1.1"], ["traceroute", "-n", "1.1.1.1"]],
            timeout=5,
            max_workers=2,
        )

    def test_main_can_update_servicenow_work_notes_explicitly(self):
        client = mock.Mock()
        client.add_work_notes.return_value = mock.Mock(number="INC0012345")
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch("incidentpack.application.ServiceNowSettings.from_env", return_value=mock.Mock()),
            mock.patch("incidentpack.application.ServiceNowClient", return_value=client),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            rc = incident_pack.main(
                [
                    "--target",
                    "1.1.1.1",
                    "--ports",
                    "443",
                    "--mock",
                    "--non-interactive",
                    "--out-dir",
                    tmpdir,
                    "--servicenow-update",
                    "INC0012345",
                ]
            )
            json_path = next(Path(tmpdir).glob("incident_pack_*.json"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(payload["integrations"]["servicenow"]["status"], "updated")
        self.assertEqual(payload["integrations"]["servicenow"]["incident"], "INC0012345")
        client.add_work_notes.assert_called_once()
        self.assertIn("# Incident Evidence Pack", client.add_work_notes.call_args.args[1])

    def test_servicenow_failure_preserves_local_outputs_and_returns_nonzero(self):
        client = mock.Mock()
        client.add_work_notes.side_effect = incident_pack.ServiceNowError("API unavailable")
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch("incidentpack.application.ServiceNowSettings.from_env", return_value=mock.Mock()),
            mock.patch("incidentpack.application.ServiceNowClient", return_value=client),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            rc = incident_pack.main(
                [
                    "--target",
                    "1.1.1.1",
                    "--ports",
                    "443",
                    "--mock",
                    "--non-interactive",
                    "--out-dir",
                    tmpdir,
                    "--servicenow-update",
                    "INC0012345",
                ]
            )
            json_path = next(Path(tmpdir).glob("incident_pack_*.json"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 1)
        self.assertEqual(payload["integrations"]["servicenow"]["status"], "failed")
        self.assertIn("API unavailable", payload["integrations"]["servicenow"]["error"])

    def test_main_can_resolve_target_from_netbox(self):
        netbox_client = mock.Mock()
        netbox_client.get_device.return_value = NetBoxDevice(
            name="edge-01",
            address="10.20.0.1",
            dns_name="edge-01.example.com",
            site="Louisville",
            role="edge-router",
        )
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            mock.patch("incidentpack.application.NetBoxSettings.from_env", return_value=mock.Mock()),
            mock.patch("incidentpack.application.NetBoxClient", return_value=netbox_client),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            rc = incident_pack.main(
                [
                    "--netbox-device",
                    "edge-01",
                    "--ports",
                    "443",
                    "--mock",
                    "--non-interactive",
                    "--out-dir",
                    tmpdir,
                ]
            )
            json_path = next(Path(tmpdir).glob("incident_pack_*.json"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertEqual(payload["meta"]["target"], "10.20.0.1")
        self.assertEqual(payload["inventory"]["source"], "netbox")
        self.assertEqual(payload["inventory"]["site"], "Louisville")

    def test_choose_output_base_adds_suffix_on_collision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            first_base = incident_pack.choose_output_base(
                tmpdir, "demo-host", timestamp="20260303_120000"
            )
            Path(f"{first_base}.json").write_text("{}", encoding="utf-8")
            second_base = incident_pack.choose_output_base(
                tmpdir, "demo-host", timestamp="20260303_120000"
            )
        self.assertTrue(second_base.endswith("_01"))

    def test_write_outputs_creates_json_and_markdown(self):
        evidence = incident_pack.mock_evidence("1.1.1.1", "example.com", [443])
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = incident_pack.write_outputs(evidence, tmpdir, md_max_lines=10)
            json_path = Path(paths["json"])
            md_path = Path(paths["md"])
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["meta"]["host"], "demo-host")


if __name__ == "__main__":
    unittest.main()
