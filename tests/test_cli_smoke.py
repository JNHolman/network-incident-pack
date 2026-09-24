import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from incidentpack import __version__


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "incident_pack.py"


class IncidentPackCliSmokeTests(unittest.TestCase):
    def run_mock(self, out_dir: str) -> subprocess.CompletedProcess[str]:
        """Run the public-safe CLI path exactly as a user would."""
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--target",
            "10.20.30.40",
            "--dns-name",
            "app.example.com",
            "--ports",
            "443",
            "80",
            "22",
            "--mock",
            "--out-dir",
            out_dir,
            "--non-interactive",
        ]
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def find_output(out_dir: str, suffix: str) -> Path:
        matches = list(Path(out_dir).glob(f"*{suffix}"))
        if len(matches) != 1:
            raise AssertionError(f"Expected one {suffix} output, found {len(matches)}")
        return matches[0]


    def test_cli_reports_release_version(self):
        command = [sys.executable, str(SCRIPT_PATH), "--version"]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn(__version__, result.stdout)

    def test_mock_cli_generates_current_json_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_mock(tmpdir)
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            json_path = self.find_output(tmpdir, ".json")
            data = json.loads(json_path.read_text(encoding="utf-8"))

            required_sections = {
                "schema_version",
                "meta",
                "context",
                "dns",
                "tcp",
                "ping",
                "traceroute",
                "interfaces",
                "routes",
                "neighbors",
                "health",
                "collection_summary",
                "commands",
            }
            self.assertTrue(required_sections.issubset(data))
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["meta"]["target"], "10.20.30.40")
            self.assertEqual(data["meta"]["mode"], "mock")
            self.assertEqual(data["meta"]["ports"], [443, 80, 22])
            self.assertEqual(data["traceroute"]["status"], "complete")
            self.assertTrue(data["traceroute"]["target_reached"])

    def test_mock_cli_generates_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.run_mock(tmpdir)
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            markdown_path = self.find_output(tmpdir, ".md")
            content = markdown_path.read_text(encoding="utf-8")

            self.assertIn("# Incident Evidence Pack", content)
            self.assertIn("10.20.30.40", content)
            self.assertIn("Mode: `mock`", content)
            self.assertIn("Traceroute: **COMPLETE**", content)
            self.assertIn("## Health Summary", content)
            self.assertIn("## Collection Summary", content)
            self.assertIn("Reachability: **HEALTHY**", content)
            self.assertIn("Interfaces: **HEALTHY**", content)

    def test_mock_cli_is_deterministic(self):
        with (
            tempfile.TemporaryDirectory() as first_dir,
            tempfile.TemporaryDirectory() as second_dir,
        ):
            first = self.run_mock(first_dir)
            second = self.run_mock(second_dir)
            self.assertEqual(first.returncode, 0, msg=first.stderr)
            self.assertEqual(second.returncode, 0, msg=second.stderr)

            first_data = json.loads(
                self.find_output(first_dir, ".json").read_text(encoding="utf-8")
            )
            second_data = json.loads(
                self.find_output(second_dir, ".json").read_text(encoding="utf-8")
            )
            self.assertEqual(first_data, second_data)

    def test_inventory_cli_resolves_named_device_and_site_defaults(self):
        config_path = REPO_ROOT / "config" / "inventory.example.yaml"
        with tempfile.TemporaryDirectory() as tmpdir:
            command = [
                sys.executable,
                str(SCRIPT_PATH),
                "--device",
                "app-demo-01",
                "--config",
                str(config_path),
                "--mock",
                "--out-dir",
                tmpdir,
                "--non-interactive",
            ]
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            data = json.loads(
                self.find_output(tmpdir, ".json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["schema_version"], 2)
            self.assertEqual(data["meta"]["target"], "10.20.30.40")
            self.assertEqual(data["meta"]["dns_name"], "app.example.com")
            self.assertEqual(data["meta"]["ports"], [443, 22])
            self.assertEqual(data["inventory"]["device"], "app-demo-01")
            self.assertEqual(data["inventory"]["site"], "louisville-lab")
            self.assertEqual(data["inventory"]["role"], "application-server")
            self.assertEqual(data["inventory"]["source"], "inventory.example.yaml")

            markdown = self.find_output(tmpdir, ".md").read_text(encoding="utf-8")
            self.assertIn("Inventory Device: `app-demo-01`", markdown)
            self.assertIn("Site: `louisville-lab`", markdown)

    def test_inventory_cli_allows_explicit_port_override(self):
        config_path = REPO_ROOT / "config" / "inventory.example.json"
        with tempfile.TemporaryDirectory() as tmpdir:
            command = [
                sys.executable,
                str(SCRIPT_PATH),
                "--device",
                "app-demo-01",
                "--config",
                str(config_path),
                "--ports",
                "8443",
                "22",
                "--mock",
                "--out-dir",
                tmpdir,
                "--non-interactive",
            ]
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            data = json.loads(
                self.find_output(tmpdir, ".json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["meta"]["ports"], [8443, 22])


    def test_package_module_entrypoint_matches_legacy_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            command = [
                sys.executable,
                "-m",
                "incidentpack",
                "--target",
                "10.20.30.40",
                "--ports",
                "443",
                "--mock",
                "--out-dir",
                tmpdir,
                "--non-interactive",
            ]
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            data = json.loads(
                self.find_output(tmpdir, ".json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["meta"]["target"], "10.20.30.40")
            self.assertEqual(data["meta"]["mode"], "mock")

    def test_mock_unreachable_scenario_prints_operator_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            command = [
                sys.executable,
                str(SCRIPT_PATH),
                "--target",
                "10.20.30.40",
                "--ports",
                "443",
                "--mock",
                "--mock-scenario",
                "unreachable",
                "--out-dir",
                tmpdir,
                "--non-interactive",
            ]
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Status: FAILED | Reachability: FAILED", result.stdout)
            data = json.loads(
                self.find_output(tmpdir, ".json").read_text(encoding="utf-8")
            )
            self.assertEqual(data["meta"]["scenario"], "unreachable")
            self.assertEqual(data["health"]["status"], "failed")

    def test_cli_rejects_option_like_target_before_collection(self):
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--target=-i",
            "--ports",
            "443",
            "--mock",
            "--non-interactive",
        ]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot begin with '-'", result.stderr)

    def test_cli_rejects_mock_scenario_without_mock(self):
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--target",
            "10.20.30.40",
            "--ports",
            "443",
            "--mock-scenario",
            "unreachable",
            "--non-interactive",
        ]
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --mock", result.stderr)


if __name__ == "__main__":
    unittest.main()
