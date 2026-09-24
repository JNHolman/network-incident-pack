"""Parse cross-platform ping output into deterministic structured evidence."""

from __future__ import annotations

import re
from typing import Mapping, Optional, TypedDict


class PingResult(TypedDict):
    """Normalized ping result independent of operating-system output format."""

    reachable: Optional[bool]
    status: str
    packets_sent: Optional[int]
    packets_received: Optional[int]
    packet_loss_percent: Optional[float]
    min_latency_ms: Optional[float]
    avg_latency_ms: Optional[float]
    max_latency_ms: Optional[float]
    jitter_ms: Optional[float]
    parse_error: str
    execution_error_type: str


_UNIX_PACKET_RE = re.compile(
    r"(?P<sent>\d+)\s+packets transmitted,\s*"
    r"(?P<received>\d+)\s+(?:packets )?received,\s*"
    r"(?P<loss>[\d.]+)%\s+packet loss",
    re.IGNORECASE,
)

_WINDOWS_PACKET_RE = re.compile(
    r"Sent\s*=\s*(?P<sent>\d+),\s*"
    r"Received\s*=\s*(?P<received>\d+),\s*"
    r"Lost\s*=\s*\d+\s*\((?P<loss>[\d.]+)%\s*loss\)",
    re.IGNORECASE,
)

_UNIX_RTT_RE = re.compile(
    r"(?:rtt|round-trip)\s+min/avg/max/(?:mdev|stddev)\s*=\s*"
    r"(?P<min>[\d.]+)/(?P<avg>[\d.]+)/(?P<max>[\d.]+)/(?P<jitter>[\d.]+)\s*ms",
    re.IGNORECASE,
)

_WINDOWS_RTT_RE = re.compile(
    r"Minimum\s*=\s*(?P<min>\d+)ms,\s*"
    r"Maximum\s*=\s*(?P<max>\d+)ms,\s*"
    r"Average\s*=\s*(?P<avg>\d+)ms",
    re.IGNORECASE,
)


def _status(sent: int, received: int, loss: float) -> str:
    """Return a deterministic status from parsed packet statistics."""
    if sent <= 0:
        return "unknown"
    if received == 0:
        return "failed"
    if loss > 0:
        return "degraded"
    return "healthy"


def parse_ping_output(
    stdout: str,
    stderr: str = "",
    execution_error_type: str = "",
) -> PingResult:
    """Parse Linux/macOS/Windows ping output while preserving execution context."""
    text = "\n".join(part for part in (stdout, stderr) if part).strip()

    result: PingResult = {
        "reachable": None,
        "status": "unknown",
        "packets_sent": None,
        "packets_received": None,
        "packet_loss_percent": None,
        "min_latency_ms": None,
        "avg_latency_ms": None,
        "max_latency_ms": None,
        "jitter_ms": None,
        "parse_error": "",
        "execution_error_type": execution_error_type,
    }

    packet_match = _UNIX_PACKET_RE.search(text) or _WINDOWS_PACKET_RE.search(text)
    if not packet_match:
        result["parse_error"] = "packet statistics not found"
        return result

    sent = int(packet_match.group("sent"))
    received = int(packet_match.group("received"))
    loss = float(packet_match.group("loss"))

    result["packets_sent"] = sent
    result["packets_received"] = received
    result["packet_loss_percent"] = loss
    result["reachable"] = received > 0
    result["status"] = _status(sent, received, loss)

    rtt_match = _UNIX_RTT_RE.search(text)
    if rtt_match:
        result["min_latency_ms"] = float(rtt_match.group("min"))
        result["avg_latency_ms"] = float(rtt_match.group("avg"))
        result["max_latency_ms"] = float(rtt_match.group("max"))
        result["jitter_ms"] = float(rtt_match.group("jitter"))
        return result

    windows_rtt_match = _WINDOWS_RTT_RE.search(text)
    if windows_rtt_match:
        result["min_latency_ms"] = float(windows_rtt_match.group("min"))
        result["avg_latency_ms"] = float(windows_rtt_match.group("avg"))
        result["max_latency_ms"] = float(windows_rtt_match.group("max"))

    return result


def parse_ping_command_result(command_result: Mapping[str, object]) -> PingResult:
    """Parse a structured command-runner result without coupling to its concrete type."""
    return parse_ping_output(
        stdout=str(command_result.get("stdout") or ""),
        stderr=str(command_result.get("stderr") or ""),
        execution_error_type=str(command_result.get("error_type") or ""),
    )
