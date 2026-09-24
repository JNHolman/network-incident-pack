"""Versioned report contract and deterministic collection-completeness summary."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from typing import Any, List, TypedDict

from incidentpack.security import redact_secret_text

CURRENT_SCHEMA_VERSION = 2
_ALLOWED_HEALTH = {"healthy", "degraded", "failed", "unknown"}
_FORBIDDEN_SECRET_KEYS = {
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "api_key",
    "apikey",
}
_PARSE_SECTIONS = ("interfaces", "routes", "neighbors", "ping", "traceroute")



def sanitize_report(value: Any) -> Any:
    """Return a deep report copy with credential-like string content redacted."""
    if isinstance(value, Mapping):
        return {key: sanitize_report(child) for key, child in value.items()}
    if isinstance(value, list):
        return [sanitize_report(child) for child in value]
    if isinstance(value, tuple):
        return [sanitize_report(child) for child in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return copy.deepcopy(value)


class ReportValidationError(ValueError):
    """Raised when an evidence object violates the report contract."""


class CollectionSummary(TypedDict):
    commands_total: int
    commands_succeeded: int
    commands_failed: int
    commands_timed_out: int
    tcp_total: int
    tcp_succeeded: int
    tcp_failed: int
    parser_errors: int


def build_collection_summary(evidence: Mapping[str, Any]) -> CollectionSummary:
    """Return deterministic counts describing collection completeness, not health."""
    commands = list(evidence.get("commands") or [])
    tcp = list(evidence.get("tcp") or [])

    parser_errors = 0
    for section_name in _PARSE_SECTIONS:
        section = evidence.get(section_name) or {}
        if isinstance(section, Mapping) and section.get("parse_error"):
            parser_errors += 1

    succeeded_commands = sum(
        1 for command in commands if isinstance(command, Mapping) and command.get("ok") is True
    )
    timed_out_commands = sum(
        1
        for command in commands
        if isinstance(command, Mapping) and command.get("timed_out") is True
    )
    tcp_succeeded = sum(
        1 for result in tcp if isinstance(result, Mapping) and result.get("ok") is True
    )

    return {
        "commands_total": len(commands),
        "commands_succeeded": succeeded_commands,
        "commands_failed": len(commands) - succeeded_commands,
        "commands_timed_out": timed_out_commands,
        "tcp_total": len(tcp),
        "tcp_succeeded": tcp_succeeded,
        "tcp_failed": len(tcp) - tcp_succeeded,
        "parser_errors": parser_errors,
    }


def _require_mapping(container: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ReportValidationError(f"Report field '{key}' must be an object.")
    return value


def _require_list(container: Mapping[str, Any], key: str) -> List[Any]:
    value = container.get(key)
    if not isinstance(value, list):
        raise ReportValidationError(f"Report field '{key}' must be a list.")
    return value


def _find_forbidden_key(value: Any, path: str = "report") -> str:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in _FORBIDDEN_SECRET_KEYS:
                return f"{path}.{key_text}"
            found = _find_forbidden_key(child, f"{path}.{key_text}")
            if found:
                return found
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            found = _find_forbidden_key(child, f"{path}[{index}]")
            if found:
                return found
    return ""


def validate_report(evidence: Mapping[str, Any]) -> None:
    """Validate the JSON/Markdown handoff contract before it leaves the process."""
    if not isinstance(evidence, Mapping):
        raise ReportValidationError("Report must be an object.")

    version = evidence.get("schema_version")
    if version != CURRENT_SCHEMA_VERSION:
        raise ReportValidationError(
            f"Unsupported report schema_version {version!r}; expected {CURRENT_SCHEMA_VERSION}."
        )

    meta = _require_mapping(evidence, "meta")
    for key in ("timestamp_utc", "host", "os", "target", "ports", "mode"):
        if key not in meta:
            raise ReportValidationError(f"Report metadata is missing required field '{key}'.")
    if not isinstance(meta.get("ports"), list):
        raise ReportValidationError("Report metadata field 'ports' must be a list.")
    if not str(meta.get("target") or "").strip():
        raise ReportValidationError("Report metadata field 'target' cannot be empty.")

    _require_mapping(evidence, "collection")
    _require_mapping(evidence, "context")
    commands = _require_list(evidence, "commands")
    tcp = _require_list(evidence, "tcp")
    health = _require_mapping(evidence, "health")
    summary = _require_mapping(evidence, "collection_summary")

    health_status = str(health.get("status") or "")
    reachability = str(health.get("reachability") or "")
    if health_status not in _ALLOWED_HEALTH:
        raise ReportValidationError(f"Invalid overall health status '{health_status}'.")
    if reachability not in _ALLOWED_HEALTH:
        raise ReportValidationError(f"Invalid reachability status '{reachability}'.")

    expected_summary = build_collection_summary(evidence)
    for key, expected in expected_summary.items():
        actual = summary.get(key)
        if actual != expected:
            raise ReportValidationError(
                f"Collection summary field '{key}' is inconsistent: {actual!r} != {expected!r}."
            )

    for index, command in enumerate(commands):
        if not isinstance(command, Mapping):
            raise ReportValidationError(f"Command result {index} must be an object.")
        for key in (
            "cmd",
            "rc",
            "ok",
            "stdout",
            "stderr",
            "error_type",
            "timed_out",
            "duration_ms",
        ):
            if key not in command:
                raise ReportValidationError(
                    f"Command result {index} is missing required field '{key}'."
                )

    for index, result in enumerate(tcp):
        if not isinstance(result, Mapping):
            raise ReportValidationError(f"TCP result {index} must be an object.")
        for key in ("host", "port", "ok", "error", "error_type", "attempts", "duration_ms"):
            if key not in result:
                raise ReportValidationError(
                    f"TCP result {index} is missing required field '{key}'."
                )

    forbidden_path = _find_forbidden_key(evidence)
    if forbidden_path:
        raise ReportValidationError(
            f"Report contains forbidden secret-bearing field '{forbidden_path}'."
        )

    try:
        json.dumps(evidence)
    except (TypeError, ValueError) as error:
        raise ReportValidationError(f"Report is not JSON serializable: {error}") from error
