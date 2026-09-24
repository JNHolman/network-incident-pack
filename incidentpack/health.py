"""Deterministic incident-level health/status evaluation."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, TypedDict


class ComponentHealth(TypedDict):
    status: str
    detail: str


class HealthSummary(TypedDict):
    status: str
    reachability: str
    components: Dict[str, ComponentHealth]
    findings: List[str]


def _dns_health(dns: Mapping[str, Any]) -> ComponentHealth:
    if not dns:
        return {"status": "unknown", "detail": "DNS check not requested"}
    if dns.get("error"):
        return {"status": "failed", "detail": "DNS resolution failed"}
    if dns.get("answers"):
        return {"status": "healthy", "detail": "DNS returned one or more answers"}
    return {"status": "unknown", "detail": "DNS returned no answers and no explicit error"}


def _tcp_health(tcp: List[Mapping[str, Any]]) -> ComponentHealth:
    if not tcp:
        return {"status": "unknown", "detail": "No TCP ports requested"}
    passed = sum(1 for test in tcp if test.get("ok") is True)
    if passed == len(tcp):
        return {"status": "healthy", "detail": f"All {passed} requested TCP checks connected"}
    if passed:
        return {
            "status": "degraded",
            "detail": f"{passed}/{len(tcp)} requested TCP checks connected",
        }
    return {"status": "failed", "detail": f"0/{len(tcp)} requested TCP checks connected"}


def _simple_component(data: Mapping[str, Any], label: str) -> ComponentHealth:
    if not data:
        return {"status": "unknown", "detail": f"{label} evidence unavailable"}
    status = str(data.get("status") or "unknown")
    return {"status": status, "detail": f"{label} status is {status}"}


def _reachability(
    ping: Mapping[str, Any],
    traceroute: Mapping[str, Any],
    tcp: List[Mapping[str, Any]],
) -> str:
    """Evaluate target reachability without assuming ICMP must be allowed."""
    if any(test.get("ok") is True for test in tcp):
        return "healthy"
    if any(
        str(test.get("error_type") or "") in {"connection_refused", "connection_reset"}
        for test in tcp
    ):
        # An RST/refusal is a service failure, but it proves a return path to an L4 responder.
        return "healthy"

    ping_status = str(ping.get("status") or "unknown")
    trace_status = str(traceroute.get("status") or "unknown")
    if ping_status == "healthy" or trace_status == "complete":
        return "healthy"
    if ping_status == "degraded":
        return "degraded"

    explicit_failures = [
        ping_status == "failed",
        trace_status in {"failed", "partial"},
        bool(tcp) and all(test.get("ok") is False for test in tcp),
    ]
    if sum(explicit_failures) >= 2:
        return "failed"
    if any(explicit_failures):
        return "degraded"
    return "unknown"


def evaluate_health(evidence: Mapping[str, Any]) -> HealthSummary:
    """Build a stable health summary from normalized evidence only."""
    ping = evidence.get("ping") or {}
    traceroute = evidence.get("traceroute") or {}
    tcp = list(evidence.get("tcp") or [])
    interfaces = evidence.get("interfaces") or {}
    routes = evidence.get("routes") or {}
    neighbors = evidence.get("neighbors") or {}
    dns = evidence.get("dns") or {}

    components: Dict[str, ComponentHealth] = {
        "dns": _dns_health(dns),
        "ping": _simple_component(ping, "Ping"),
        "traceroute": _simple_component(traceroute, "Traceroute"),
        "tcp": _tcp_health(tcp),
        "interfaces": _simple_component(interfaces, "Interface"),
        "routes": _simple_component(routes, "Route"),
        "neighbors": _simple_component(neighbors, "Neighbor"),
    }
    reachability = _reachability(ping, traceroute, tcp)

    findings: List[str] = []
    if components["dns"]["status"] == "failed":
        findings.append("DNS resolution failed")
    if str(ping.get("status") or "") == "degraded":
        findings.append("Ping shows packet loss")
    if str(traceroute.get("status") or "") == "partial":
        findings.append("Traceroute did not reach the target")
    if components["tcp"]["status"] == "degraded":
        findings.append(components["tcp"]["detail"])
    elif components["tcp"]["status"] == "failed" and reachability != "failed":
        findings.append("Target is reachable by other evidence, but requested TCP checks failed")
    if components["routes"]["status"] == "degraded":
        findings.append("No default route was found in the local route table")
    if components["interfaces"]["status"] == "failed":
        findings.append("No active local interfaces were parsed")
    if components["neighbors"]["status"] == "degraded":
        count = int(neighbors.get("unresolved_count") or 0)
        findings.append(f"Neighbor cache contains {count} unresolved entr{'y' if count == 1 else 'ies'}")

    if reachability == "failed":
        status = "failed"
    elif reachability == "unknown":
        status = "unknown"
    else:
        target_impact_statuses = {
            components[name]["status"]
            for name in ("dns", "tcp")
            if components[name]["status"] != "unknown"
        }
        local_blocker = (
            reachability != "healthy"
            and (
                components["interfaces"]["status"] == "failed"
                or components["routes"]["status"] in {"failed", "degraded"}
            )
        )
        if (
            reachability == "degraded"
            or "failed" in target_impact_statuses
            or "degraded" in target_impact_statuses
            or local_blocker
        ):
            status = "degraded"
        else:
            status = "healthy"

    return {
        "status": status,
        "reachability": reachability,
        "components": components,
        "findings": findings,
    }
