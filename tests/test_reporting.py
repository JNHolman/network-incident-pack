import json
import tempfile
import unittest
from pathlib import Path

import incident_pack
from incidentpack.reporting import (
    ReportValidationError,
    build_collection_summary,
    redact_secret_text,
    sanitize_report,
    validate_report,
    write_outputs,
)


class ReportingTests(unittest.TestCase):
    def test_collection_summary_counts_collection_quality_not_health(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443, 22])
        evidence["commands"][0]["ok"] = False
        evidence["commands"][0]["timed_out"] = True
        evidence["ping"]["parse_error"] = "unrecognized output"

        summary = build_collection_summary(evidence)

        self.assertEqual(summary["commands_total"], 6)
        self.assertEqual(summary["commands_succeeded"], 5)
        self.assertEqual(summary["commands_failed"], 1)
        self.assertEqual(summary["commands_timed_out"], 1)
        self.assertEqual(summary["tcp_total"], 2)
        self.assertEqual(summary["tcp_succeeded"], 1)
        self.assertEqual(summary["tcp_failed"], 1)
        self.assertEqual(summary["parser_errors"], 1)

    def test_mock_report_satisfies_schema_contract(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", "app.example.com", [443])
        validate_report(evidence)

    def test_wrong_schema_version_is_rejected(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["schema_version"] = 1
        with self.assertRaisesRegex(ReportValidationError, "schema_version"):
            validate_report(evidence)

    def test_inconsistent_collection_summary_is_rejected(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["collection_summary"]["commands_succeeded"] = 999
        with self.assertRaisesRegex(ReportValidationError, "inconsistent"):
            validate_report(evidence)

    def test_missing_command_contract_field_is_rejected(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        del evidence["commands"][0]["duration_ms"]
        evidence["collection_summary"] = build_collection_summary(evidence)
        with self.assertRaisesRegex(ReportValidationError, "duration_ms"):
            validate_report(evidence)

    def test_secret_bearing_keys_are_rejected(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["integrations"] = {"netbox": {"token": "do-not-write-me"}}
        with self.assertRaisesRegex(ReportValidationError, "forbidden secret-bearing"):
            validate_report(evidence)

    def test_secret_values_are_redacted_inside_raw_text(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["commands"][0]["stdout"] = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
            "password=hunter2\n"
            "normal evidence remains"
        )
        safe = sanitize_report(evidence)
        output = safe["commands"][0]["stdout"]
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", output)
        self.assertNotIn("hunter2", output)
        self.assertIn("[REDACTED]", output)
        self.assertIn("normal evidence remains", output)

    def test_writer_redacts_secret_values_before_disk(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["commands"][0]["stderr"] = "Authorization: Basic dXNlcjpwYXNz"
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_outputs(evidence, tmpdir, md_max_lines=10)
            raw_json = Path(paths["json"]).read_text(encoding="utf-8")
            raw_md = Path(paths["md"]).read_text(encoding="utf-8")
        self.assertNotIn("dXNlcjpwYXNz", raw_json)
        self.assertNotIn("dXNlcjpwYXNz", raw_md)
        self.assertIn("[REDACTED]", raw_json)

    def test_redact_secret_text_preserves_normal_network_output(self):
        raw = "tcp 10.0.0.1:443 connected; token bucket rate=100"
        self.assertEqual(redact_secret_text(raw), raw)

    def test_non_json_serializable_value_is_rejected(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["context"]["impact"] = {1, 2, 3}
        with self.assertRaisesRegex(ReportValidationError, "not JSON serializable"):
            validate_report(evidence)

    def test_markdown_surfaces_collection_summary(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443, 22])
        markdown = incident_pack.build_markdown(evidence)
        self.assertIn("## Collection Summary", markdown)
        self.assertIn("Host commands: **6/6 succeeded**", markdown)
        self.assertIn("TCP checks: **1/2 connected**", markdown)
        self.assertIn("Parser errors: **0**", markdown)

    def test_writer_validates_before_creating_outputs(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        evidence["schema_version"] = 999
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ReportValidationError):
                write_outputs(evidence, tmpdir, md_max_lines=10)
            self.assertEqual(list(Path(tmpdir).iterdir()), [])

    def test_writer_outputs_parseable_json_with_trailing_newline(self):
        evidence = incident_pack.mock_evidence("10.20.30.40", None, [443])
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_outputs(evidence, tmpdir, md_max_lines=10)
            raw = Path(paths["json"]).read_text(encoding="utf-8")
            parsed = json.loads(raw)
            self.assertTrue(raw.endswith("\n"))
            self.assertEqual(parsed["schema_version"], 2)
            self.assertEqual(parsed["collection_summary"]["commands_total"], 6)


if __name__ == "__main__":
    unittest.main()
