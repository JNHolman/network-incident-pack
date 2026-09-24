"""Normalize local routing-table output from Linux, macOS, and Windows."""

from __future__ import annotations

import ipaddress
import re
from typing import List, Mapping, Optional, TypedDict


class RouteRecord(TypedDict):
    destination: str
    gateway: str
    interface: str
    metric: Optional[int]
    is_default: bool


class RouteResult(TypedDict):
    status: str
    route_count: int
    default_route: bool
    default_gateway: str
    default_interface: str
    routes: List[RouteRecord]
    parse_error: str
    execution_error_type: str


def _metric(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_linux(text: str) -> List[RouteRecord]:
    routes: List[RouteRecord] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        destination = parts[0]
        if destination in {"broadcast", "local", "unreachable", "prohibit", "throw", "blackhole"}:
            continue
        is_default = destination == "default"
        if not is_default:
            try:
                ipaddress.ip_network(destination, strict=False)
            except ValueError:
                continue
        gateway = ""
        interface = ""
        metric: Optional[int] = None
        if "via" in parts:
            idx = parts.index("via")
            if idx + 1 < len(parts):
                gateway = parts[idx + 1]
        if "dev" in parts:
            idx = parts.index("dev")
            if idx + 1 < len(parts):
                interface = parts[idx + 1]
        if "metric" in parts:
            idx = parts.index("metric")
            if idx + 1 < len(parts):
                metric = _metric(parts[idx + 1])
        routes.append(
            {
                "destination": destination,
                "gateway": gateway,
                "interface": interface,
                "metric": metric,
                "is_default": is_default,
            }
        )
    return routes


def _parse_macos(text: str) -> List[RouteRecord]:
    routes: List[RouteRecord] = []
    in_internet = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "Internet:":
            in_internet = True
            continue
        if line.endswith(":") and line != "Internet:":
            if in_internet:
                break
            continue
        if not in_internet or not line or line.startswith("Destination"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        destination, gateway = parts[0], parts[1]
        interface = parts[-1]
        routes.append(
            {
                "destination": destination,
                "gateway": gateway,
                "interface": interface,
                "metric": None,
                "is_default": destination == "default",
            }
        )
    return routes


def _parse_windows(text: str) -> List[RouteRecord]:
    routes: List[RouteRecord] = []
    in_active_routes = False
    route_re = re.compile(
        r"^\s*(?P<network>\d+\.\d+\.\d+\.\d+)\s+"
        r"(?P<mask>\d+\.\d+\.\d+\.\d+)\s+"
        r"(?P<gateway>\S+)\s+(?P<interface>\S+)\s+(?P<metric>\d+)\s*$"
    )
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "Active Routes:":
            in_active_routes = True
            continue
        if in_active_routes and stripped.startswith("Persistent Routes:"):
            break
        if not in_active_routes:
            continue
        match = route_re.match(line)
        if not match:
            continue
        network = match.group("network")
        mask = match.group("mask")
        is_default = network == "0.0.0.0" and mask == "0.0.0.0"
        destination = "default" if is_default else f"{network}/{mask}"
        routes.append(
            {
                "destination": destination,
                "gateway": match.group("gateway"),
                "interface": match.group("interface"),
                "metric": _metric(match.group("metric")),
                "is_default": is_default,
            }
        )
    return routes


def parse_route_output(
    stdout: str,
    stderr: str = "",
    *,
    os_name: str,
    execution_error_type: str = "",
) -> RouteResult:
    """Parse a platform route table and identify the effective default route."""
    text = "\n".join(part for part in (stdout, stderr) if part).strip()
    parser = {
        "linux": _parse_linux,
        "macos": _parse_macos,
        "windows": _parse_windows,
    }.get(os_name)
    routes = parser(text) if parser else []
    defaults = [route for route in routes if route["is_default"]]
    default = min(
        defaults,
        key=lambda route: route["metric"] if route["metric"] is not None else 2**31,
        default=None,
    )

    if not routes:
        status = "unknown"
    elif default is None:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "route_count": len(routes),
        "default_route": default is not None,
        "default_gateway": default["gateway"] if default else "",
        "default_interface": default["interface"] if default else "",
        "routes": routes,
        "parse_error": "" if routes else "route data not found",
        "execution_error_type": execution_error_type,
    }


def parse_route_command_result(
    command_result: Mapping[str, object], *, os_name: str
) -> RouteResult:
    return parse_route_output(
        stdout=str(command_result.get("stdout") or ""),
        stderr=str(command_result.get("stderr") or ""),
        os_name=os_name,
        execution_error_type=str(command_result.get("error_type") or ""),
    )
