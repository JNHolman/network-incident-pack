"""Deterministic mock incident scenarios for demos, tests, and interview walkthroughs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, Mapping, MutableMapping

from incidentpack.health import evaluate_health
from incidentpack.parsers.ping import parse_ping_command_result
from incidentpack.parsers.traceroute import parse_traceroute_command_result
from incidentpack.reporting import build_collection_summary

BASELINE_SCENARIO = "baseline"
MOCK_SCENARIOS = (
    BASELINE_SCENARIO,
    "healthy",
    "dns-failure",
    "service-refused",
    "unreachable",
    "collector-timeout",
)

SCENARIO_DESCRIPTIONS: Mapping[str, str] = {
    "baseline": "Default mixed-service demo: common web ports connect, other requested ports refuse.",
    "healthy": "Target is reachable and every requested TCP service connects.",
    "dns-failure": "IP reachability works but the requested DNS name does not resolve.",
    "service-refused": "Target is reachable but every requested TCP service actively refuses connections.",
    "unreachable": "Ping, traceroute, and TCP evidence indicate the target cannot be reached.",
    "collector-timeout": "Network evidence is usable, but one local host collector times out.",
}


def validate_mock_scenario(name: str) -> str:
    """Return a normalized supported scenario name or raise a clear configuration error."""
    normalized = name.strip().lower()
    if normalized not in MOCK_SCENARIOS:
        choices = ", ".join(MOCK_SCENARIOS)
        raise ValueError(f"Unsupported mock scenario '{name}'. Choose one of: {choices}.")
    return normalized


def _command_by_prefix(commands: Iterable[MutableMapping[str, Any]], prefix: str) -> MutableMapping[str, Any]:
    for command in commands:
        if str(command.get("cmd") or "").startswith(prefix):
            return command
    raise ValueError(f"Mock evidence is missing expected command prefix '{prefix}'.")


def _set_tcp_success(results: Iterable[MutableMapping[str, Any]]) -> None:
    for result in results:
        result.update(
            {
                "ok": True,
                "error": "",
                "error_type": "",
                "attempts": 1,
                "duration_ms": 1.0,
            }
        )


def _set_tcp_refused(results: Iterable[MutableMapping[str, Any]]) -> None:
    for result in results:
        result.update(
            {
                "ok": False,
                "error": "ConnectionRefusedError: Connection refused",
                "error_type": "connection_refused",
                "attempts": 1,
                "duration_ms": 1.0,
            }
        )


def _set_tcp_timeouts(results: Iterable[MutableMapping[str, Any]], attempts: int) -> None:
    for result in results:
        result.update(
            {
                "ok": False,
                "error": "TimeoutError: timed out",
                "error_type": "timeout",
                "attempts": attempts,
                "duration_ms": 3000.0,
            }
        )


def apply_mock_scenario(evidence: Dict[str, Any], scenario: str) -> Dict[str, Any]:
    """Return a scenario-specific copy while keeping raw and structured evidence aligned."""
    name = validate_mock_scenario(scenario)
    result = deepcopy(evidence)
    result.setdefault("meta", {})["scenario"] = name

    commands = result.get("commands") or []
    tcp = result.get("tcp") or []
    target = str(result.get("meta", {}).get("target") or "")

    if name == "healthy":
        _set_tcp_success(tcp)

    elif name == "dns-failure":
        dns = result.get("dns") or {}
        if not dns.get("name"):
            raise ValueError("The dns-failure mock scenario requires --dns-name.")
        dns["answers"] = []
        dns["error"] = "gaierror: Name or service not known"
        result["dns"] = dns

    elif name == "service-refused":
        _set_tcp_refused(tcp)

    elif name == "unreachable":
        _set_tcp_timeouts(tcp, int(result.get("collection", {}).get("tcp_max_attempts") or 1))

        ping = _command_by_prefix(commands, "ping ")
        ping.update(
            {
                "rc": 1,
                "ok": False,
                "stdout": (
                    f"PING {target} ({target}) 56(84) bytes of data.\n\n"
                    f"--- {target} ping statistics ---\n"
                    "4 packets transmitted, 0 received, 100% packet loss, time 3067ms"
                ),
                "stderr": "",
                "error_type": "nonzero_exit",
                "timed_out": False,
                "duration_ms": 3067.0,
            }
        )
        result["ping"] = parse_ping_command_result(ping)

        trace = _command_by_prefix(commands, "traceroute ")
        trace.update(
            {
                "rc": 1,
                "ok": False,
                "stdout": (
                    f"traceroute to {target} ({target}), 30 hops max, 60 byte packets\n"
                    " 1  192.168.1.1  1.100 ms  1.000 ms  0.900 ms\n"
                    " 2  * * *\n"
                    " 3  * * *\n"
                    " 4  * * *"
                ),
                "stderr": "",
                "error_type": "nonzero_exit",
                "timed_out": False,
                "duration_ms": 15000.0,
            }
        )
        result["traceroute"] = parse_traceroute_command_result(trace, target=target)

    elif name == "collector-timeout":
        collector = _command_by_prefix(commands, "ss ")
        collector.update(
            {
                "rc": None,
                "ok": False,
                "stdout": "",
                "stderr": "Command timed out after 15 seconds",
                "error_type": "timeout",
                "timed_out": True,
                "duration_ms": 15000.0,
            }
        )

    # baseline intentionally preserves the original mock evidence.
    result["health"] = evaluate_health(result)
    result["collection_summary"] = build_collection_summary(result)
    return result
