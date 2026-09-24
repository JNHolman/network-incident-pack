"""Normalize local interface output from Linux, macOS, and Windows."""

from __future__ import annotations

import re
from typing import List, Mapping, Optional, TypedDict


class InterfaceRecord(TypedDict):
    """Normalized interface details used by incident summaries."""

    name: str
    state: str
    is_up: Optional[bool]
    is_loopback: bool
    mac: str
    ipv4: List[str]
    ipv6: List[str]


class InterfaceResult(TypedDict):
    """Structured interface inventory independent of operating-system output."""

    status: str
    interface_count: int
    up_count: int
    usable_up_count: int
    interfaces: List[InterfaceRecord]
    parse_error: str
    execution_error_type: str


_LINUX_HEADER_RE = re.compile(
    r"^\d+:\s+(?P<name>[^:@]+)(?:@[^:]+)?:\s+<(?P<flags>[^>]*)>.*?(?:state\s+(?P<state>\S+))?",
    re.IGNORECASE,
)
_MAC_HEADER_RE = re.compile(r"^(?P<name>[^:\s]+):\s+flags=.*?<(?P<flags>[^>]*)>")
_WIN_ADAPTER_RE = re.compile(r"^(?P<name>.+? adapter .+):$", re.IGNORECASE)


def _is_loopback_name(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"lo", "lo0"} or "loopback" in lowered


def _new_interface(name: str, *, state: str = "unknown", is_up: Optional[bool] = None) -> InterfaceRecord:
    return {
        "name": name,
        "state": state.lower(),
        "is_up": is_up,
        "is_loopback": _is_loopback_name(name),
        "mac": "",
        "ipv4": [],
        "ipv6": [],
    }


def _append_unique(values: List[str], value: str) -> None:
    value = value.strip().split("%", 1)[0]
    if value and value not in values:
        values.append(value)


def _parse_linux(text: str) -> List[InterfaceRecord]:
    interfaces: List[InterfaceRecord] = []
    current: Optional[InterfaceRecord] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        header = _LINUX_HEADER_RE.match(line)
        if header:
            flags = {flag.strip().upper() for flag in header.group("flags").split(",")}
            state = (header.group("state") or ("UP" if "UP" in flags else "DOWN")).lower()
            current = _new_interface(
                header.group("name"),
                state=state,
                is_up=("UP" in flags and state != "down"),
            )
            interfaces.append(current)
            continue
        if current is None:
            continue

        stripped = line.strip()
        if stripped.startswith("link/"):
            parts = stripped.split()
            if len(parts) >= 2 and re.fullmatch(r"[0-9a-fA-F:]{17}", parts[1]):
                current["mac"] = parts[1].lower()
        elif stripped.startswith("inet "):
            value = stripped.split()[1].split("/", 1)[0]
            _append_unique(current["ipv4"], value)
        elif stripped.startswith("inet6 "):
            value = stripped.split()[1].split("/", 1)[0]
            _append_unique(current["ipv6"], value)

    return interfaces


def _parse_macos(text: str) -> List[InterfaceRecord]:
    interfaces: List[InterfaceRecord] = []
    current: Optional[InterfaceRecord] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        header = _MAC_HEADER_RE.match(line)
        if header:
            flags = {flag.strip().upper() for flag in header.group("flags").split(",")}
            current = _new_interface(
                header.group("name"),
                state="up" if "UP" in flags else "down",
                is_up="UP" in flags,
            )
            interfaces.append(current)
            continue
        if current is None:
            continue

        stripped = line.strip()
        if stripped.startswith("ether "):
            parts = stripped.split()
            if len(parts) >= 2:
                current["mac"] = parts[1].lower()
        elif stripped.startswith("inet "):
            parts = stripped.split()
            if len(parts) >= 2:
                _append_unique(current["ipv4"], parts[1])
        elif stripped.startswith("inet6 "):
            parts = stripped.split()
            if len(parts) >= 2:
                _append_unique(current["ipv6"], parts[1])
        elif stripped.startswith("status:"):
            state = stripped.split(":", 1)[1].strip().lower()
            current["state"] = state
            current["is_up"] = state == "active"

    return interfaces


def _parse_windows(text: str) -> List[InterfaceRecord]:
    interfaces: List[InterfaceRecord] = []
    current: Optional[InterfaceRecord] = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        header = _WIN_ADAPTER_RE.match(line.strip())
        if header:
            current = _new_interface(header.group("name"), state="unknown", is_up=None)
            interfaces.append(current)
            continue
        if current is None or ":" not in line:
            continue

        key, value = [part.strip() for part in line.split(":", 1)]
        key_lower = key.lower().replace(". ", "").replace(".", "")
        value = value.strip()

        if key_lower.startswith("physical address"):
            current["mac"] = value.replace("-", ":").lower()
        elif key_lower.startswith("media state"):
            disconnected = "disconnected" in value.lower()
            current["state"] = "down" if disconnected else "up"
            current["is_up"] = not disconnected
        elif key_lower.startswith("ipv4 address"):
            _append_unique(current["ipv4"], value.split("(", 1)[0].strip())
            if current["is_up"] is None:
                current["is_up"] = True
                current["state"] = "up"
        elif key_lower.startswith("ipv6 address") or key_lower.startswith("link-local ipv6 address"):
            _append_unique(current["ipv6"], value.split("(", 1)[0].strip())
            if current["is_up"] is None:
                current["is_up"] = True
                current["state"] = "up"

    return interfaces


def parse_interface_output(
    stdout: str,
    stderr: str = "",
    *,
    os_name: str,
    execution_error_type: str = "",
) -> InterfaceResult:
    """Parse local interface output into a compact cross-platform schema."""
    text = "\n".join(part for part in (stdout, stderr) if part).strip()
    parser = {
        "linux": _parse_linux,
        "macos": _parse_macos,
        "windows": _parse_windows,
    }.get(os_name)
    interfaces = parser(text) if parser else []
    up_count = sum(1 for interface in interfaces if interface["is_up"] is True)
    usable_up_count = sum(
        1
        for interface in interfaces
        if interface["is_up"] is True and not interface["is_loopback"]
    )

    if not interfaces:
        status = "unknown"
    elif usable_up_count == 0:
        status = "failed"
    else:
        status = "healthy"

    return {
        "status": status,
        "interface_count": len(interfaces),
        "up_count": up_count,
        "usable_up_count": usable_up_count,
        "interfaces": interfaces,
        "parse_error": "" if interfaces else "interface data not found",
        "execution_error_type": execution_error_type,
    }


def parse_interface_command_result(
    command_result: Mapping[str, object], *, os_name: str
) -> InterfaceResult:
    """Parse a structured command-runner result."""
    return parse_interface_output(
        stdout=str(command_result.get("stdout") or ""),
        stderr=str(command_result.get("stderr") or ""),
        os_name=os_name,
        execution_error_type=str(command_result.get("error_type") or ""),
    )
