"""Run a visible live demo against the local Incident Pack sandbox."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from incidentpack.application import IncidentPackRequest, IncidentPackResult, run_incident_pack
from lab.local_sandbox import SandboxEnvironment, start_sandbox


@dataclass(frozen=True)
class DemoCase:
    name: str
    display_name: str
    dns_name: str
    ports: List[int]
    expected_status: str
    expected_reachability: str


def build_demo_cases(sandbox: SandboxEnvironment) -> List[DemoCase]:
    return [
        DemoCase(
            name="healthy",
            display_name="Healthy baseline",
            dns_name="localhost",
            ports=[sandbox.http_port, sandbox.tcp_port],
            expected_status="healthy",
            expected_reachability="healthy",
        ),
        DemoCase(
            name="service-refused",
            display_name="Service unavailable",
            dns_name="localhost",
            ports=[sandbox.http_port, sandbox.refused_port],
            expected_status="degraded",
            expected_reachability="healthy",
        ),
        DemoCase(
            name="dns-failure",
            display_name="DNS failure",
            dns_name="incident-pack-demo.invalid",
            ports=[sandbox.http_port],
            expected_status="degraded",
            expected_reachability="healthy",
        ),
    ]


class DemoRenderer:
    """Render real collection events as a concise terminal walkthrough."""

    HOST_STAGES: Dict[str, tuple[str, str]] = {
        "interfaces": ("Interfaces", "collecting..."),
        "routes": ("Routes", "checking..."),
        "neighbors": ("Neighbors", "checking..."),
        "ping": ("Ping", "testing..."),
        "traceroute": ("Traceroute", "tracing..."),
        "sockets": ("Local sockets", "collecting..."),
        "command": ("Host command", "running..."),
    }

    def __init__(self) -> None:
        self.interactive = sys.stdout.isatty()
        self.minimum_stage_seconds = 0.35 if self.interactive else 0.0
        self.started_at: Dict[str, float] = {}

    def _replace(self, text: str) -> None:
        sys.stdout.write("\r\033[2K" + text)
        sys.stdout.flush()

    @staticmethod
    def _format(label: str, state: str) -> str:
        return f"{label:<20}{state}"

    def start(self, key: str, label: str, state: str) -> None:
        self.started_at[key] = time.monotonic()
        if self.interactive:
            self._replace(self._format(label, state))

    def finish(self, key: str, label: str, state: str, detail: str = "") -> None:
        if self.interactive:
            elapsed = time.monotonic() - self.started_at.get(key, time.monotonic())
            remaining = self.minimum_stage_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._replace(self._format(label, state))
            sys.stdout.write("\n")
        else:
            print(self._format(label, state))
        if detail:
            print(f"{'':20}{detail}")

    def progress(self, event: str, payload: Dict[str, object]) -> None:
        if event == "dns_started":
            self.start("dns", "DNS", "resolving...")
            return

        if event == "dns_completed":
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                result = {}
            answers = list(result.get("answers") or [])
            if result.get("error"):
                self.finish(
                    "dns",
                    "DNS",
                    "FAILED",
                    "Name resolution failed; IP/TCP evidence is evaluated separately.",
                )
            else:
                answer_text = ", ".join(str(value) for value in answers[:3]) or "no answers"
                self.finish("dns", "DNS", "HEALTHY", f"Resolved to {answer_text}")
            return

        if event == "host_started":
            section = str(payload.get("section") or "command")
            label, verb = self.HOST_STAGES.get(section, self.HOST_STAGES["command"])
            self.start(f"host:{section}", label, verb)
            return

        if event == "host_completed":
            section = str(payload.get("section") or "command")
            label, _ = self.HOST_STAGES.get(section, self.HOST_STAGES["command"])
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                result = {}
            status = str(result.get("status") or "complete").upper()
            detail = self._host_detail(section, result)
            self.finish(f"host:{section}", label, status, detail)
            return

        if event == "tcp_started":
            port = int(payload.get("port") or 0)
            self.start(f"tcp:{port}", f"TCP {port}", "connecting...")
            return

        if event == "tcp_completed":
            port = int(payload.get("port") or 0)
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                result = {}
            if result.get("ok") is True:
                self.finish(
                    f"tcp:{port}",
                    f"TCP {port}",
                    "CONNECTED",
                    "Requested service accepted the connection.",
                )
                return

            error_type = str(result.get("error_type") or "failed")
            state = error_type.replace("_", " ").upper()
            if error_type == "connection_refused":
                detail = "RST received: host reachable; requested service is not listening."
            elif error_type == "timeout":
                detail = "No TCP response before timeout; this alone does not prove host failure."
            else:
                detail = str(result.get("error") or "TCP check failed.")
            self.finish(f"tcp:{port}", f"TCP {port}", state, detail)
            return

        if event == "collection_completed":
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                result = {}
            incomplete = int(result.get("commands_failed") or 0) + int(
                result.get("parser_errors") or 0
            )
            state = "COMPLETE" if incomplete == 0 else "INCOMPLETE"
            detail = (
                f"{result.get('commands_succeeded', 0)}/{result.get('commands_total', 0)} "
                f"host commands; {result.get('parser_errors', 0)} parser errors"
            )
            self.finish("collection", "Collection quality", state, detail)
            return

        if event == "health_started":
            self.start("health", "Health decision", "evaluating...")
            return

        if event == "health_completed":
            result = payload.get("result") or {}
            if not isinstance(result, dict):
                result = {}
            self.finish(
                "health",
                "Health decision",
                str(result.get("status") or "unknown").upper(),
            )
            components = result.get("components") or {}
            if not isinstance(components, dict):
                components = {}
            tcp = components.get("tcp") or {}
            if not isinstance(tcp, dict):
                tcp = {}
            print(
                self._format(
                    "Reachability",
                    str(result.get("reachability") or "unknown").upper(),
                )
            )
            print(
                self._format(
                    "TCP service health",
                    str(tcp.get("status") or "unknown").upper(),
                )
            )
            return

        if event == "report_started":
            self.start("report", "Report", "writing...")
            return

        if event == "report_completed":
            self.finish("report", "Report", "WRITTEN", "JSON + Markdown saved")
            return

    @staticmethod
    def _host_detail(section: str, result: Dict[str, object]) -> str:
        if section == "interfaces":
            return f"{result.get('usable_up_count', 0)} usable interface(s) up"
        if section == "routes":
            gateway = str(result.get("default_gateway") or "")
            return (
                f"Default route via {gateway}"
                if result.get("default_route")
                else "No usable default route parsed"
            )
        if section == "neighbors":
            return (
                f"{result.get('neighbor_count', 0)} entries; "
                f"{result.get('unresolved_count', 0)} unresolved"
            )
        if section == "ping":
            loss = result.get("packet_loss_percent")
            return f"{loss:g}% packet loss" if isinstance(loss, (int, float)) else ""
        if section == "traceroute":
            if result.get("target_reached") is True:
                return f"Destination reached in {result.get('hop_count', 0)} hop(s)"
            return f"Destination not confirmed; {result.get('responding_hops', 0)} responding hop(s)"
        if section == "sockets":
            return "Local socket table captured"
        return ""

    @staticmethod
    def interpretation(result: IncidentPackResult) -> None:
        findings = list((result.evidence.get("health") or {}).get("findings") or [])
        if findings:
            print("\nInterpretation:")
            for finding in findings:
                print(f"  - {finding}")
        else:
            print("\nInterpretation:")
            print("  - Requested checks support a healthy target and service path.")


def run_demo(out_dir: str, scenario: str = "all") -> int:
    sandbox = start_sandbox(http_port=0, tcp_port=0, refused_port=0)
    renderer = DemoRenderer()
    failures = 0
    total = 0
    try:
        cases = build_demo_cases(sandbox)
        if scenario != "all":
            cases = [case for case in cases if case.name == scenario]

        print("Network Incident Pack — Live Incident Demo")
        print(f"Target: {sandbox.host}")

        for index, case in enumerate(cases):
            total += 1
            if index:
                print("\n" + "-" * 56)
            print(f"\nScenario: {case.display_name}")
            print(f"Requested ports: {', '.join(str(port) for port in case.ports)}\n")

            case_dir = Path(out_dir) / case.name
            result = run_incident_pack(
                IncidentPackRequest(
                    target=sandbox.host,
                    dns_name=case.dns_name,
                    ports=case.ports,
                    non_interactive=True,
                    out_dir=str(case_dir),
                    tcp_attempts=1,
                    tcp_timeout=1.0,
                    workers=1,
                ),
                progress_callback=renderer.progress,
            )

            renderer.interpretation(result)

            health = result.evidence["health"]
            status = str(health["status"])
            reachability = str(health["reachability"])
            matched = (
                status == case.expected_status
                and reachability == case.expected_reachability
            )
            if not matched:
                failures += 1

            if scenario == "all":
                marker = "PASS" if matched else "FAIL"
                print(
                    f"\nScenario result: {marker} — "
                    f"status={status}, reachability={reachability}"
                )
            else:
                marker = "matched" if matched else "did not match"
                print(f"\nExpected outcome {marker}.")

    finally:
        sandbox.close()

    if scenario == "all":
        print("\n" + "=" * 56)
        if failures:
            print(f"Live validation complete: {total - failures}/{total} scenarios matched.")
        else:
            print(
                f"Live validation complete: {total}/{total} scenarios matched expected outcomes."
            )

    return 1 if failures else 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run visible healthy/failure Incident Pack live validation."
    )
    parser.add_argument("--out-dir", default="./lab-output")
    parser.add_argument(
        "--scenario",
        choices=["all", "healthy", "service-refused", "dns-failure"],
        default="all",
        help="Run the full validation matrix or one focused portfolio scenario.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run_demo(args.out_dir, scenario=args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())
