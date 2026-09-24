import json
import tempfile
import unittest
from pathlib import Path

from incidentpack.config import (
    ConfigurationError,
    command_timeout_from_config,
    load_config,
    positive_float_from_config,
    positive_int_from_config,
)


class ConfigTests(unittest.TestCase):
    def test_load_json_config(self):
        payload = {
            "version": 1,
            "defaults": {"command_timeout": 12, "ports": [443]},
            "sites": {},
            "devices": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inventory.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = load_config(str(path))
        self.assertEqual(config["defaults"]["command_timeout"], 12)

    def test_load_yaml_config(self):
        text = """\
version: 1
defaults:
  command_timeout: 9
sites: {}
devices: {}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inventory.yaml"
            path.write_text(text, encoding="utf-8")
            config = load_config(str(path))
        self.assertEqual(config["defaults"]["command_timeout"], 9)

    def test_missing_config_is_clear_error(self):
        with self.assertRaisesRegex(ConfigurationError, "not found"):
            load_config("/definitely/not/here/inventory.yaml")

    def test_unsupported_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inventory.toml"
            path.write_text("version = 1", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "Unsupported configuration format"):
                load_config(str(path))

    def test_non_mapping_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inventory.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "root must be"):
                load_config(str(path))

    def test_unsupported_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "inventory.json"
            path.write_text('{"version": 2}', encoding="utf-8")
            with self.assertRaisesRegex(ConfigurationError, "Unsupported configuration version"):
                load_config(str(path))

    def test_command_timeout_uses_config_and_validates_type(self):
        self.assertEqual(command_timeout_from_config({"defaults": {"command_timeout": 7}}, 15), 7)
        with self.assertRaisesRegex(ConfigurationError, "must be an integer"):
            command_timeout_from_config({"defaults": {"command_timeout": "7"}}, 15)

    def test_concurrency_and_tcp_defaults_are_validated(self):
        config = {"defaults": {"max_workers": 6, "tcp_attempts": 3, "tcp_timeout": 2.5}}
        self.assertEqual(positive_int_from_config(config, "max_workers", 4), 6)
        self.assertEqual(positive_int_from_config(config, "tcp_attempts", 2), 3)
        self.assertEqual(positive_float_from_config(config, "tcp_timeout", 3.0), 2.5)
        with self.assertRaisesRegex(ConfigurationError, "must be at least"):
            positive_int_from_config({"defaults": {"max_workers": 0}}, "max_workers", 4)
        with self.assertRaisesRegex(ConfigurationError, "greater than 0"):
            positive_float_from_config({"defaults": {"tcp_timeout": 0}}, "tcp_timeout", 3.0)


if __name__ == "__main__":
    unittest.main()
