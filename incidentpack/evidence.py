"""Build mock or live incident evidence independently from CLI orchestration."""

from __future__ import annotations

import platform
from typing import Any, Dict, List, Optional, Sequence

from incidentpack.collectors.host import run_host_commands
from incidentpack.collectors.tcp import run_tcp_checks
from incidentpack.health import evaluate_health
from incidentpack.host_context import detect_os, now_utc_iso, os_commands, prompt_context, resolve
from incidentpack.parsers.interfaces import parse_interface_command_result
from incidentpack.parsers.neighbors import parse_neighbor_command_result
from incidentpack.parsers.ping import parse_ping_command_result
from incidentpack.parsers.routes import parse_route_command_result
from incidentpack.parsers.traceroute import parse_traceroute_command_result
from incidentpack.reporting import CURRENT_SCHEMA_VERSION, build_collection_summary
from incidentpack.scenarios import BASELINE_SCENARIO, apply_mock_scenario

DEFAULT_CMD_TIMEOUT = 15
DEFAULT_TCP_TIMEOUT = 3.0
DEFAULT_TCP_ATTEMPTS = 2
DEFAULT_MAX_WORKERS = 4
REPORT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION
MOCK_TIMESTAMP_UTC = "2026-01-29T06:07:27+00:00"
MOCK_OS = "linux"


def mock_evidence(
    target: str,
    dns_name: Optional[str],
    ports: List[int],
    inventory: Optional[Dict[str, str]] = None,
    *,
    timeout: int = DEFAULT_CMD_TIMEOUT,
    tcp_timeout: float = DEFAULT_TCP_TIMEOUT,
    tcp_attempts: int = DEFAULT_TCP_ATTEMPTS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    scenario: str = BASELINE_SCENARIO,
) -> Dict[str, Any]:
    """Generate deterministic, public-safe evidence for demos and contract tests."""
    evidence: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "meta": {
            "timestamp_utc": MOCK_TIMESTAMP_UTC,
            "host": "demo-host",
            "os": MOCK_OS,
            "target": target,
            "dns_name": dns_name or "",
            "ports": ports,
            "mode": "mock",
        },
        "inventory": inventory or {},
        "collection": {
            "max_workers": max_workers,
            "command_timeout_seconds": timeout,
            "tcp_timeout_seconds": tcp_timeout,
            "tcp_max_attempts": tcp_attempts,
        },
        "context": {
            "impact": "",
            "symptoms": "",
            "scope": "",
            "recent_changes": "",
            "actions_taken": "",
        },
        "dns": {
            "name": dns_name or "",
            "answers": ["93.184.216.34"],
            "error": "",
        }
        if dns_name
        else {},
        "tcp": [
            {
                "host": target,
                "port": port,
                "ok": port in (80, 443),
                "error": "" if port in (80, 443) else "ConnectionRefusedError: Connection refused",
                "error_type": "" if port in (80, 443) else "connection_refused",
                "attempts": 1,
                "duration_ms": 1.0,
            }
            for port in ports
        ],
        "commands": [
            {
                "cmd": "ip addr",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN\n"
                    "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
                    "    inet 127.0.0.1/8 scope host lo\n"
                    "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
                    "    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff\n"
                    "    inet 192.168.1.25/24 brd 192.168.1.255 scope global eth0"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 8.0,
            },
            {
                "cmd": "ip route",
                "rc": 0,
                "ok": True,
                "stdout": (
                    "default via 192.168.1.1 dev eth0 proto dhcp metric 100\n"
                    "192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.25 metric 100"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 4.0,
            },
            {
                "cmd": "ip neigh",
                "rc": 0,
                "ok": True,
                "stdout": "192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE",
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 3.0,
            },
            {
                "cmd": f"ping -c 4 {target}",
                "rc": 0,
                "ok": True,
                "stdout": (
                    f"PING {target} ({target}) 56(84) bytes of data.\n"
                    f"64 bytes from {target}: icmp_seq=1 ttl=57 time=22.1 ms\n\n"
                    f"--- {target} ping statistics ---\n"
                    "4 packets transmitted, 4 received, 0% packet loss, time 3004ms\n"
                    "rtt min/avg/max/mdev = 22.100/23.250/24.400/0.900 ms"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 12.0,
            },
            {
                "cmd": f"traceroute -n {target}",
                "rc": 0,
                "ok": True,
                "stdout": (
                    f"traceroute to {target} ({target}), 30 hops max, 60 byte packets\n"
                    " 1  192.168.1.1  1.100 ms  1.000 ms  0.900 ms\n"
                    " 2  * * *\n"
                    " 3  10.20.0.1  8.100 ms  8.000 ms  7.900 ms\n"
                    f" 4  {target}  22.400 ms  22.200 ms  22.300 ms"
                ),
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 18.0,
            },
            {
                "cmd": "ss -tulpn",
                "rc": 0,
                "ok": True,
                "stdout": "Netid State  Local Address:Port  Peer Address:Port",
                "stderr": "",
                "error_type": "",
                "timed_out": False,
                "duration_ms": 5.0,
            },
        ],
    }
    evidence["interfaces"] = parse_interface_command_result(evidence["commands"][0], os_name=MOCK_OS)
    evidence["routes"] = parse_route_command_result(evidence["commands"][1], os_name=MOCK_OS)
    evidence["neighbors"] = parse_neighbor_command_result(evidence["commands"][2], os_name=MOCK_OS)
    evidence["ping"] = parse_ping_command_result(evidence["commands"][3])
    evidence["traceroute"] = parse_traceroute_command_result(evidence["commands"][4], target=target)
    evidence["health"] = evaluate_health(evidence)
    evidence["collection_summary"] = build_collection_summary(evidence)
    return apply_mock_scenario(evidence, scenario)


def _attach_structured_command_evidence(
    evidence: Dict[str, Any],
    commands: Sequence[Sequence[str]],
    command_results: Sequence[Dict[str, Any]],
    *,
    os_name: str,
    target: str,
) -> None:
    """Parse known command results into normalized sections without losing raw evidence."""
    for command, command_result in zip(commands, command_results):
        if not command:
            continue
        command_name = command[0].lower()
        if command_name in {"ipconfig", "ifconfig"} or (
            command_name == "ip" and len(command) > 1 and command[1] == "addr"
        ):
            evidence["interfaces"] = parse_interface_command_result(command_result, os_name=os_name)
        elif command_name == "route" or (
            command_name == "netstat" and "-rn" in command
        ) or (command_name == "ip" and len(command) > 1 and command[1] == "route"):
            evidence["routes"] = parse_route_command_result(command_result, os_name=os_name)
        elif command_name == "arp" or (
            command_name == "ip" and len(command) > 1 and command[1] == "neigh"
        ):
            evidence["neighbors"] = parse_neighbor_command_result(command_result, os_name=os_name)
        elif command_name == "ping":
            evidence["ping"] = parse_ping_command_result(command_result)
        elif command_name in {"traceroute", "tracert"}:
            evidence["traceroute"] = parse_traceroute_command_result(command_result, target=target)


def collect_live_evidence(
    target: str,
    dns_name: Optional[str],
    ports: List[int],
    timeout: int,
    non_interactive: bool,
    inventory: Optional[Dict[str, str]] = None,
    *,
    tcp_timeout: float = DEFAULT_TCP_TIMEOUT,
    tcp_attempts: int = DEFAULT_TCP_ATTEMPTS,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> Dict[str, Any]:
    """Collect live host-side evidence with bounded concurrency for independent checks."""
    host = platform.node() or "unknown-host"
    os_name = detect_os()
    commands = os_commands(target, os_name=os_name)

    tcp_results = run_tcp_checks(
        target,
        ports,
        timeout=tcp_timeout,
        max_attempts=tcp_attempts,
        max_workers=max_workers,
    )
    command_results = run_host_commands(commands, timeout=timeout, max_workers=max_workers)

    evidence: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "meta": {
            "timestamp_utc": now_utc_iso(),
            "host": host,
            "os": os_name,
            "target": target,
            "dns_name": dns_name or "",
            "ports": ports,
            "mode": "live",
        },
        "inventory": inventory or {},
        "collection": {
            "max_workers": max_workers,
            "command_timeout_seconds": timeout,
            "tcp_timeout_seconds": tcp_timeout,
            "tcp_max_attempts": tcp_attempts,
        },
        "context": prompt_context(non_interactive),
        "dns": resolve(dns_name) if dns_name else {},
        "tcp": tcp_results,
        "commands": command_results,
    }

    _attach_structured_command_evidence(
        evidence,
        commands,
        command_results,
        os_name=os_name,
        target=target,
    )
    evidence["health"] = evaluate_health(evidence)
    evidence["collection_summary"] = build_collection_summary(evidence)
    return evidence
