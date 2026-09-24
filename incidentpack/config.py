"""Load and validate Incident Pack configuration files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping


class ConfigurationError(ValueError):
    """Raised when a configuration file cannot be loaded or validated."""


def _load_yaml(text: str, path: Path) -> object:
    """Load YAML safely, with a clear dependency error when PyYAML is unavailable."""
    try:
        import yaml
    except ImportError as error:  # pragma: no cover - exercised in environments without PyYAML.
        raise ConfigurationError(
            "YAML configuration requires PyYAML. Install dependencies with "
            "'python -m pip install -r requirements.txt'."
        ) from error

    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML in {path}: {error}") from error


def load_config(path_value: str) -> Dict[str, Any]:
    """Load a JSON or YAML configuration document from disk."""
    path = Path(path_value).expanduser()
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")
    if not path.is_file():
        raise ConfigurationError(f"Configuration path is not a file: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(f"Could not read configuration file {path}: {error}") from error

    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            document = json.loads(text)
        except json.JSONDecodeError as error:
            raise ConfigurationError(f"Invalid JSON in {path}: {error}") from error
    elif suffix in {".yaml", ".yml"}:
        document = _load_yaml(text, path)
    else:
        raise ConfigurationError(
            f"Unsupported configuration format '{suffix or '<none>'}'. Use .json, .yaml, or .yml."
        )

    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ConfigurationError("Configuration root must be a mapping/object.")

    version = document.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ConfigurationError(f"Unsupported configuration version: {version!r}. Expected 1.")

    for section in ("defaults", "sites", "devices"):
        value = document.get(section, {})
        if value is None:
            document[section] = {}
            continue
        if not isinstance(value, dict):
            raise ConfigurationError(f"Configuration section '{section}' must be a mapping/object.")

    return document


def config_defaults(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return validated global defaults from a loaded configuration document."""
    defaults = config.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ConfigurationError("Configuration section 'defaults' must be a mapping/object.")
    return defaults


def command_timeout_from_config(config: Mapping[str, Any], fallback: int) -> int:
    """Return a configured command timeout or the supplied fallback."""
    value = config_defaults(config).get("command_timeout", fallback)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError("defaults.command_timeout must be an integer.")
    if value < 1:
        raise ConfigurationError("defaults.command_timeout must be at least 1 second.")
    return value


def positive_int_from_config(
    config: Mapping[str, Any], key: str, fallback: int, *, minimum: int = 1
) -> int:
    """Return a validated positive integer from global defaults."""
    value = config_defaults(config).get(key, fallback)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"defaults.{key} must be an integer.")
    if value < minimum:
        raise ConfigurationError(f"defaults.{key} must be at least {minimum}.")
    return value


def positive_float_from_config(
    config: Mapping[str, Any], key: str, fallback: float
) -> float:
    """Return a validated positive numeric value from global defaults."""
    value = config_defaults(config).get(key, fallback)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"defaults.{key} must be numeric.")
    number = float(value)
    if number <= 0:
        raise ConfigurationError(f"defaults.{key} must be greater than 0.")
    return number
