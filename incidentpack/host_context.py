"""Host-side platform, DNS, command-plan, and interactive context helpers."""

from __future__ import annotations

import datetime as dt
import platform
import socket
from typing import Any, Dict, List

SUPPORTED_OS = {"windows", "macos", "linux"}


def now_utc_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def resolve(name: str) -> Dict[str, Any]:
    """Resolve a DNS name and preserve failure as structured evidence."""
    out: Dict[str, Any] = {"name": name, "answers": [], "error": ""}
    try:
        infos = socket.getaddrinfo(name, None)
        out["answers"] = sorted({info[4][0] for info in infos})
    except Exception as error:  # DNS library boundary; preserve collection.
        out["error"] = f"{type(error).__name__}: {error}"
    return out


def detect_os() -> str:
    """Return one normalized operating-system name for collector selection."""
    system_name = platform.system().lower()
    if "windows" in system_name:
        os_name = "windows"
    elif "darwin" in system_name:
        os_name = "macos"
    else:
        os_name = "linux"
    return os_name if os_name in SUPPORTED_OS else "linux"


def os_commands(target: str, *, os_name: str | None = None) -> List[List[str]]:
    """Build the baseline, non-privileged host-side collection command plan."""
    selected_os = os_name or detect_os()
    if selected_os == "windows":
        return [
            ["ipconfig", "/all"],
            ["route", "print"],
            ["arp", "-a"],
            ["ping", "-n", "4", target],
            ["tracert", "-d", target],
            ["netstat", "-ano"],
        ]
    if selected_os == "macos":
        return [
            ["ifconfig"],
            ["netstat", "-rn"],
            ["arp", "-an"],
            ["ping", "-c", "4", target],
            ["traceroute", "-n", target],
            ["netstat", "-anv"],
        ]
    return [
        ["ip", "addr"],
        ["ip", "route"],
        ["ip", "neigh"],
        ["ping", "-c", "4", target],
        ["traceroute", "-n", target],
        ["ss", "-tulpn"],
    ]


def prompt_context(non_interactive: bool) -> Dict[str, str]:
    """Collect optional human incident context without coupling it to evidence logic."""
    fields = [
        ("impact", "Impact (who/what is affected?)"),
        ("symptoms", "Symptoms (what is failing?)"),
        ("scope", "Scope (one user/site/many?)"),
        ("recent_changes", "Recent changes (deploy/patch/network change?)"),
        ("actions_taken", "Actions already taken"),
    ]
    out: Dict[str, str] = {}
    if non_interactive:
        return {key: "" for key, _ in fields}

    print("\nEnter incident context (press Enter to skip any field):\n")
    for key, label in fields:
        try:
            out[key] = input(f"{label}: ").strip()
        except EOFError:
            out[key] = ""
    return out
