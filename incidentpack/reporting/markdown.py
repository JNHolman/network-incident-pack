"""Markdown renderer for ServiceNow-ready incident handoffs."""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_MD_MAX_LINES = 40

def build_markdown(evidence: Dict[str, Any], md_max_lines: int = DEFAULT_MD_MAX_LINES) -> str:
    """Convert evidence dict to Markdown format (ServiceNow-ready)."""
    meta = evidence["meta"]
    ctx = evidence["context"]
    dns = evidence.get("dns", {})
    tcp = evidence.get("tcp", [])
    ping = evidence.get("ping", {})
    traceroute = evidence.get("traceroute", {})
    interfaces = evidence.get("interfaces", {})
    routes = evidence.get("routes", {})
    neighbors = evidence.get("neighbors", {})
    health = evidence.get("health", {})
    inventory = evidence.get("inventory", {})
    integrations = evidence.get("integrations", {})
    cloud = evidence.get("cloud", {})
    cmds = evidence.get("commands", [])

    lines: List[str] = []
    lines.append("# Incident Evidence Pack")
    lines.append("")
    lines.append("## Metadata")
    if evidence.get("schema_version") is not None:
        lines.append(f"- Report Schema: `{evidence.get('schema_version')}`")
    lines.append(f"- Timestamp (UTC): `{meta.get('timestamp_utc')}`")
    lines.append(f"- Host: `{meta.get('host')}`")
    lines.append(f"- OS: `{meta.get('os')}`")
    lines.append(f"- Target: `{meta.get('target')}`")
    if meta.get("dns_name"):
        lines.append(f"- DNS Name: `{meta.get('dns_name')}`")
    if meta.get("ports"):
        lines.append(f"- Ports: `{', '.join(map(str, meta.get('ports', [])))}`")
    if meta.get("mode"):
        lines.append(f"- Mode: `{meta.get('mode')}`")
    if meta.get("scenario"):
        lines.append(f"- Mock Scenario: `{meta.get('scenario')}`")
    if inventory:
        if inventory.get("device"):
            lines.append(f"- Inventory Device: `{inventory.get('device')}`")
        if inventory.get("site"):
            lines.append(f"- Site: `{inventory.get('site')}`")
        if inventory.get("role"):
            lines.append(f"- Role: `{inventory.get('role')}`")
        if inventory.get("source"):
            lines.append(f"- Inventory Source: `{inventory.get('source')}`")
    lines.append("")

    if cloud:
        lines.append("## Cloud Context")
        lines.append(f"- Provider: `{cloud.get('provider', '')}`")
        lines.append(f"- Resource: `{cloud.get('name', '')}`")
        if cloud.get("resource_group"):
            lines.append(f"- Resource Group: `{cloud.get('resource_group')}`")
        if cloud.get("location"):
            lines.append(f"- Region: `{cloud.get('location')}`")
        if cloud.get("vm_size"):
            lines.append(f"- VM Size: `{cloud.get('vm_size')}`")
        if cloud.get("power_state"):
            lines.append(f"- Power State: `{cloud.get('power_state')}`")
        for nic in (cloud.get("network", {}) or {}).get("nics", []):
            if not isinstance(nic, dict):
                continue
            details = []
            if nic.get("private_ips"):
                details.append("private=" + ",".join(nic.get("private_ips", [])))
            if nic.get("public_ips"):
                details.append("public=" + ",".join(nic.get("public_ips", [])))
            if nic.get("virtual_networks"):
                details.append("vnet=" + ",".join(nic.get("virtual_networks", [])))
            if nic.get("subnets"):
                details.append("subnet=" + ",".join(nic.get("subnets", [])))
            if nic.get("network_security_group"):
                details.append("nsg=" + str(nic.get("network_security_group")))
            lines.append(
                f"- NIC `{nic.get('name', '')}`"
                + (f": {', '.join(details)}" if details else "")
            )
        lines.append("")

    if health:
        lines.append("## Health Summary")
        lines.append(f"- Overall: **{str(health.get('status', 'unknown')).upper()}**")
        lines.append(f"- Reachability: **{str(health.get('reachability', 'unknown')).upper()}**")
        for finding in health.get("findings", []):
            lines.append(f"- Finding: {finding}")
        lines.append("")

    collection_summary = evidence.get("collection_summary", {})
    if collection_summary:
        lines.append("## Collection Summary")
        command_total = int(collection_summary.get("commands_total", 0))
        command_ok = int(collection_summary.get("commands_succeeded", 0))
        command_timeouts = int(collection_summary.get("commands_timed_out", 0))
        tcp_total = int(collection_summary.get("tcp_total", 0))
        tcp_ok = int(collection_summary.get("tcp_succeeded", 0))
        parser_errors = int(collection_summary.get("parser_errors", 0))
        lines.append(
            f"- Host commands: **{command_ok}/{command_total} succeeded** "
            f"({command_timeouts} timed out)"
        )
        lines.append(f"- TCP checks: **{tcp_ok}/{tcp_total} connected**")
        lines.append(f"- Parser errors: **{parser_errors}**")
        lines.append("")

    lines.append("## Context")
    for key in ["impact", "symptoms", "scope", "recent_changes", "actions_taken"]:
        value = (ctx.get(key) or "").strip()
        lines.append(f"- **{key.replace('_', ' ').title()}**: {value}")
    lines.append("")

    lines.append("## Key Results")
    if dns:
        if dns.get("error"):
            lines.append(f"- DNS: ❌ `{dns.get('name')}` -> `{dns.get('error')}`")
        else:
            answers = ", ".join(dns.get("answers", [])) or "none"
            lines.append(f"- DNS: ✅ `{dns.get('name')}` -> {answers}")
    if ping:
        status = ping.get("status", "unknown")
        received = ping.get("packets_received")
        sent = ping.get("packets_sent")
        loss = ping.get("packet_loss_percent")
        avg_ms = ping.get("avg_latency_ms")
        details = []
        if sent is not None and received is not None:
            details.append(f"received {received}/{sent}")
        if loss is not None:
            details.append(f"loss {loss:g}%")
        if avg_ms is not None:
            details.append(f"avg {avg_ms:g} ms")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"- Ping: **{status.upper()}**{suffix}")
        if ping.get("parse_error"):
            lines.append(f"  - Parse note: `{ping.get('parse_error')}`")
    if traceroute:
        status = traceroute.get("status", "unknown")
        hop_count = traceroute.get("hop_count", 0)
        timeout_hops = traceroute.get("timeout_hops", 0)
        target_reached = traceroute.get("target_reached")
        details = []
        if hop_count:
            details.append(f"{hop_count} hops observed")
        if timeout_hops:
            details.append(f"{timeout_hops} timeout hop{'s' if timeout_hops != 1 else ''}")
        if target_reached is True:
            details.append("target reached")
        elif target_reached is False:
            details.append("target not reached")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"- Traceroute: **{status.upper()}**{suffix}")
        if traceroute.get("parse_error"):
            lines.append(f"  - Parse note: `{traceroute.get('parse_error')}`")
    if interfaces:
        lines.append(
            f"- Interfaces: **{str(interfaces.get('status', 'unknown')).upper()}** "
            f"({interfaces.get('usable_up_count', interfaces.get('up_count', 0))} usable up, {interfaces.get('interface_count', 0)} total)"
        )
    if routes:
        route_note = "default route present" if routes.get("default_route") else "no default route"
        lines.append(
            f"- Routes: **{str(routes.get('status', 'unknown')).upper()}** "
            f"({routes.get('route_count', 0)} routes, {route_note})"
        )
    if neighbors:
        lines.append(
            f"- Neighbors: **{str(neighbors.get('status', 'unknown')).upper()}** "
            f"({neighbors.get('neighbor_count', 0)} entries, "
            f"{neighbors.get('unresolved_count', 0)} unresolved)"
        )
    if tcp:
        for test in tcp:
            attempts = test.get("attempts")
            attempt_note = (
                f" after {attempts} attempt{'s' if attempts != 1 else ''}"
                if attempts
                else ""
            )
            if test.get("ok"):
                lines.append(f"- TCP {test['host']}:{test['port']}: ✅ connect ok{attempt_note}")
            else:
                lines.append(
                    f"- TCP {test['host']}:{test['port']}: ❌ {test.get('error')}{attempt_note}"
                )
    lines.append("")

    if integrations:
        lines.append("## Integrations")
        azure = integrations.get("azure", {})
        if azure:
            status = str(azure.get("status", "unknown")).upper()
            resource = azure.get("resource", "")
            lines.append(f"- Azure `{resource}`: **{status}**")
            if azure.get("error"):
                lines.append(f"  - Error: `{azure.get('error')}`")
        servicenow = integrations.get("servicenow", {})
        if servicenow:
            status = str(servicenow.get("status", "unknown")).upper()
            incident = servicenow.get("incident", "")
            lines.append(f"- ServiceNow `{incident}`: **{status}**")
            if servicenow.get("error"):
                lines.append(f"  - Error: `{servicenow.get('error')}`")
        lines.append("")

    lines.append("## Raw Command Outputs")
    for command_result in cmds:
        lines.append(f"### `{command_result.get('cmd')}`")
        lines.append("")
        lines.append("```text")

        stdout = (command_result.get("stdout") or "").strip()
        stderr = (command_result.get("stderr") or "").strip()

        combined = ""
        if stdout:
            combined += stdout
        if stderr:
            combined += ("\n\n" if combined else "") + "[stderr]\n" + stderr
        combined = combined.strip()

        if combined:
            out_lines = combined.splitlines()
            if len(out_lines) > md_max_lines:
                lines.extend(out_lines[:md_max_lines])
                lines.append(
                    f"... (truncated; full output preserved in JSON) [{len(out_lines)} lines total]"
                )
            else:
                lines.append(combined)
        else:
            lines.append("(no output)")

        lines.append("```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
