"""Small validation helpers shared by the CLI and application service."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from typing import List, Sequence


MAX_PORTS_PER_RUN = 32
MAX_COMMAND_TIMEOUT_SECONDS = 60
MAX_WORKERS = 16
MAX_TCP_ATTEMPTS = 3
MAX_TCP_TIMEOUT_SECONDS = 30.0


def normalize_ports(ports: Sequence[int]) -> List[int]:
    """Deduplicate ports while preserving caller order."""
    seen: set[int] = set()
    out: List[int] = []
    for port in ports:
        if port not in seen:
            out.append(port)
            seen.add(port)
    return out


def validate_ports(ports: Sequence[int]) -> None:
    """Validate TCP ports and cap one run to a bounded troubleshooting scope."""
    invalid = [port for port in ports if port < 1 or port > 65535]
    if invalid:
        joined = ", ".join(str(port) for port in invalid)
        raise ValueError(f"Invalid port(s): {joined}. Valid range is 1-65535.")
    if len(ports) > MAX_PORTS_PER_RUN:
        raise ValueError(
            f"Too many ports requested: {len(ports)}. Maximum is {MAX_PORTS_PER_RUN} per run."
        )


def validate_md_max_lines(value: int) -> None:
    """Validate Markdown output truncation settings."""
    if value < 1:
        raise ValueError("--md-max-lines must be at least 1.")


def validate_timeout(value: int) -> None:
    """Validate command timeout settings."""
    if value < 1:
        raise ValueError("--timeout must be at least 1 second.")
    if value > MAX_COMMAND_TIMEOUT_SECONDS:
        raise ValueError(
            f"--timeout cannot exceed {MAX_COMMAND_TIMEOUT_SECONDS} seconds."
        )


def validate_workers(value: int) -> None:
    """Validate bounded concurrency for one collection run."""
    if value < 1:
        raise ValueError("--workers must be at least 1.")
    if value > MAX_WORKERS:
        raise ValueError(f"--workers cannot exceed {MAX_WORKERS}.")


def validate_tcp_attempts(value: int) -> None:
    """Validate bounded retry count for transient TCP failures."""
    if value < 1:
        raise ValueError("--tcp-attempts must be at least 1.")
    if value > MAX_TCP_ATTEMPTS:
        raise ValueError(f"--tcp-attempts cannot exceed {MAX_TCP_ATTEMPTS}.")


def validate_tcp_timeout(value: float) -> None:
    """Validate bounded TCP connect timeout."""
    if value <= 0:
        raise ValueError("--tcp-timeout must be greater than 0.")
    if value > MAX_TCP_TIMEOUT_SECONDS:
        raise ValueError(
            f"--tcp-timeout cannot exceed {MAX_TCP_TIMEOUT_SECONDS:g} seconds."
        )


def validate_https_endpoint(value: str, label: str) -> str:
    """Validate an integration base URL before credentials are sent to it."""
    candidate = value.strip().rstrip("/")
    if not candidate:
        raise ValueError(f"{label} cannot be empty.")
    parsed = urlsplit(candidate)
    if parsed.scheme.lower() != "https":
        raise ValueError(f"{label} must use https://")
    if not parsed.hostname:
        raise ValueError(f"{label} must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label} cannot contain embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} cannot contain a query string or fragment.")
    return candidate


_HOST_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_SCOPE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def validate_host(value: str, label: str = "target") -> str:
    """Validate a host/IP before it can be passed to OS network commands."""
    candidate = value.strip()
    if not candidate:
        raise ValueError(f"{label} cannot be empty.")
    if candidate.startswith("-"):
        raise ValueError(f"{label} cannot begin with '-'.")
    if any(char.isspace() or ord(char) < 32 for char in candidate):
        raise ValueError(f"{label} cannot contain whitespace or control characters.")

    address_part = candidate
    if "%" in candidate:
        address_part, scope = candidate.rsplit("%", 1)
        if not scope or _SCOPE_RE.fullmatch(scope) is None:
            raise ValueError(f"{label} contains an invalid IPv6 scope identifier.")
    try:
        ipaddress.ip_address(address_part)
        return candidate
    except ValueError:
        if "%" in candidate:
            raise ValueError(f"{label} is not a valid scoped IPv6 address.")

    hostname = candidate[:-1] if candidate.endswith(".") else candidate
    if len(hostname) > 253:
        raise ValueError(f"{label} hostname is too long.")
    labels = hostname.split(".")
    if not labels or any(_HOST_LABEL_RE.fullmatch(part) is None for part in labels):
        raise ValueError(f"{label} must be a valid hostname, IPv4 address, or IPv6 address.")
    return candidate
