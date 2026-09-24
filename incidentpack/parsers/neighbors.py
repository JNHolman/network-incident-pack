"""Normalize ARP/neighbor-cache output from Linux, macOS, and Windows."""

from __future__ import annotations

import re
from typing import List, Mapping, TypedDict


class NeighborRecord(TypedDict):
    address: str
    mac: str
    interface: str
    state: str


class NeighborResult(TypedDict):
    status: str
    neighbor_count: int
    unresolved_count: int
    neighbors: List[NeighborRecord]
    parse_error: str
    execution_error_type: str


_BAD_STATES = {"failed", "incomplete", "unreachable"}


def _parse_linux(text: str) -> List[NeighborRecord]:
    neighbors: List[NeighborRecord] = []
    for raw_line in text.splitlines():
        parts = raw_line.split()
        if len(parts) < 2:
            continue
        address = parts[0]
        interface = parts[parts.index("dev") + 1] if "dev" in parts and parts.index("dev") + 1 < len(parts) else ""
        mac = parts[parts.index("lladdr") + 1] if "lladdr" in parts and parts.index("lladdr") + 1 < len(parts) else ""
        state = parts[-1].lower() if parts[-1].isalpha() else "unknown"
        neighbors.append(
            {"address": address, "mac": mac.lower(), "interface": interface, "state": state}
        )
    return neighbors


def _parse_macos(text: str) -> List[NeighborRecord]:
    neighbors: List[NeighborRecord] = []
    pattern = re.compile(
        r"^.*?\((?P<address>[^)]+)\)\s+at\s+(?P<mac>\S+)(?:\s+on\s+(?P<interface>\S+))?",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        mac = match.group("mac")
        unresolved = mac.lower() in {"(incomplete)", "incomplete"}
        neighbors.append(
            {
                "address": match.group("address"),
                "mac": "" if unresolved else mac.lower(),
                "interface": match.group("interface") or "",
                "state": "incomplete" if unresolved else "reachable",
            }
        )
    return neighbors


def _parse_windows(text: str) -> List[NeighborRecord]:
    neighbors: List[NeighborRecord] = []
    interface = ""
    header_re = re.compile(r"^Interface:\s+(?P<address>\S+)", re.IGNORECASE)
    row_re = re.compile(
        r"^\s*(?P<address>\d+\.\d+\.\d+\.\d+)\s+"
        r"(?P<mac>[0-9a-fA-F-]{17})\s+(?P<type>\S+)\s*$"
    )
    for line in text.splitlines():
        header = header_re.match(line.strip())
        if header:
            interface = header.group("address")
            continue
        row = row_re.match(line)
        if not row:
            continue
        neighbors.append(
            {
                "address": row.group("address"),
                "mac": row.group("mac").replace("-", ":").lower(),
                "interface": interface,
                "state": row.group("type").lower(),
            }
        )
    return neighbors


def parse_neighbor_output(
    stdout: str,
    stderr: str = "",
    *,
    os_name: str,
    execution_error_type: str = "",
) -> NeighborResult:
    """Parse ARP/neighbor cache output and count unresolved entries."""
    text = "\n".join(part for part in (stdout, stderr) if part).strip()
    parser = {
        "linux": _parse_linux,
        "macos": _parse_macos,
        "windows": _parse_windows,
    }.get(os_name)
    neighbors = parser(text) if parser else []
    unresolved_count = sum(1 for item in neighbors if item["state"] in _BAD_STATES)

    if not neighbors:
        status = "unknown"
    elif unresolved_count:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "neighbor_count": len(neighbors),
        "unresolved_count": unresolved_count,
        "neighbors": neighbors,
        "parse_error": "" if neighbors else "neighbor data not found",
        "execution_error_type": execution_error_type,
    }


def parse_neighbor_command_result(
    command_result: Mapping[str, object], *, os_name: str
) -> NeighborResult:
    return parse_neighbor_output(
        stdout=str(command_result.get("stdout") or ""),
        stderr=str(command_result.get("stderr") or ""),
        os_name=os_name,
        execution_error_type=str(command_result.get("error_type") or ""),
    )
