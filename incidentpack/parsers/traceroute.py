"""Parse cross-platform traceroute/tracert output into structured path evidence."""

from __future__ import annotations

import ipaddress
import re
from typing import List, Mapping, Optional, TypedDict


class TracerouteHop(TypedDict):
    """One normalized traceroute hop."""

    hop: int
    address: Optional[str]
    latencies_ms: List[float]
    timed_out: bool


class TracerouteResult(TypedDict):
    """Normalized traceroute result independent of operating-system output format."""

    status: str
    target_reached: Optional[bool]
    target_address: Optional[str]
    hop_count: int
    responding_hops: int
    timeout_hops: int
    hops: List[TracerouteHop]
    parse_error: str
    execution_error_type: str


_UNIX_HEADER_RE = re.compile(
    r"traceroute\s+to\s+.+?\s+\((?P<address>[^)]+)\)",
    re.IGNORECASE,
)
_WINDOWS_HEADER_BRACKET_RE = re.compile(
    r"Tracing route to\s+.+?\s+\[(?P<address>[^\]]+)\]",
    re.IGNORECASE,
)
_WINDOWS_HEADER_IP_RE = re.compile(
    r"Tracing route to\s+(?P<address>[^\s]+)\s+over a maximum",
    re.IGNORECASE,
)
_HOP_LINE_RE = re.compile(r"^\s*(?P<hop>\d+)\s+(?P<body>.+?)\s*$")
_LATENCY_RE = re.compile(r"<?\s*(?P<latency>\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_IPV6_TOKEN_RE = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:%]+")


def _valid_ip(candidate: str) -> bool:
    """Return True when candidate is a valid IPv4 or IPv6 address."""
    candidate = candidate.split("%", 1)[0]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return True


def _extract_ip(text: str) -> Optional[str]:
    """Extract the first valid IP address from a traceroute line."""
    for candidate in _IPV4_RE.findall(text):
        if _valid_ip(candidate):
            return candidate
    for match in _IPV6_TOKEN_RE.finditer(text):
        candidate = match.group(0).rstrip(":")
        if _valid_ip(candidate):
            return candidate
    return None


def _extract_target_address(text: str, target: str = "") -> Optional[str]:
    """Resolve the destination address from traceroute headers or an IP target."""
    for pattern in (_UNIX_HEADER_RE, _WINDOWS_HEADER_BRACKET_RE, _WINDOWS_HEADER_IP_RE):
        match = pattern.search(text)
        if match:
            candidate = match.group("address").strip()
            if _valid_ip(candidate):
                return candidate

    clean_target = target.strip()
    if clean_target and _valid_ip(clean_target):
        return clean_target
    return None


def _status(hops: List[TracerouteHop], target_reached: Optional[bool]) -> str:
    """Return deterministic path status without treating intermediate timeouts as failure."""
    if not hops:
        return "unknown"
    if target_reached:
        return "complete"
    if any(not hop["timed_out"] for hop in hops):
        return "partial"
    return "failed"


def parse_traceroute_output(
    stdout: str,
    stderr: str = "",
    target: str = "",
    execution_error_type: str = "",
) -> TracerouteResult:
    """Parse Linux/macOS traceroute and Windows tracert output."""
    text = "\n".join(part for part in (stdout, stderr) if part).strip()
    target_address = _extract_target_address(text, target=target)
    hops: List[TracerouteHop] = []

    for line in text.splitlines():
        match = _HOP_LINE_RE.match(line)
        if not match:
            continue

        hop_number = int(match.group("hop"))
        body = match.group("body")
        address = _extract_ip(body)
        latencies = [float(value) for value in _LATENCY_RE.findall(body)]
        timed_out = address is None and "*" in body

        # Ignore numbered prose that is not a traceroute hop.
        if address is None and not timed_out and "Request timed out" not in body:
            continue
        if "Request timed out" in body:
            timed_out = True

        hops.append(
            {
                "hop": hop_number,
                "address": address,
                "latencies_ms": latencies,
                "timed_out": timed_out,
            }
        )

    target_reached: Optional[bool]
    if not hops:
        target_reached = None
    elif target_address:
        target_reached = any(hop["address"] == target_address for hop in hops)
    elif re.search(r"\bTrace complete\.\s*$", text, re.IGNORECASE | re.MULTILINE):
        # Windows explicitly signals completion even if the destination header could not be parsed.
        target_reached = True
    else:
        target_reached = False

    result: TracerouteResult = {
        "status": _status(hops, target_reached),
        "target_reached": target_reached,
        "target_address": target_address,
        "hop_count": max((hop["hop"] for hop in hops), default=0),
        "responding_hops": sum(1 for hop in hops if not hop["timed_out"] and hop["address"]),
        "timeout_hops": sum(1 for hop in hops if hop["timed_out"]),
        "hops": hops,
        "parse_error": "",
        "execution_error_type": execution_error_type,
    }

    if not hops:
        result["parse_error"] = "hop data not found"

    return result


def parse_traceroute_command_result(
    command_result: Mapping[str, object],
    target: str = "",
) -> TracerouteResult:
    """Parse a structured command-runner result without coupling to its concrete type."""
    return parse_traceroute_output(
        stdout=str(command_result.get("stdout") or ""),
        stderr=str(command_result.get("stderr") or ""),
        target=target,
        execution_error_type=str(command_result.get("error_type") or ""),
    )
