"""Run a visible live demo against the local Incident Pack sandbox."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List

from incidentpack.application import IncidentPackRequest, IncidentPackResult, run_incident_pack
from lab.local_sandbox import SandboxEnvironment, start_sandbox


@dataclass(frozen=True)
class DemoCase:
    name: str
    dns_name: str
    ports: List[int]
    expected_status: str
    expected_reachability: str


def build_demo_cases(sandbox: SandboxEnvironment) -> List[DemoCase]:
    return [
        DemoCase(
            name="healthy",
            dns_name="localhost",
            ports=[sandbox.http_port, sandbox.tcp_port],
            expected_status="healthy",
            expected_reachability="healthy",
        ),
        DemoCase(
            name="service-refused",
            dns_name="localhost",
            ports=[sandbox.http_port, sandbox.refused_port],
            expected_status="degraded",
            expected_reachability="healthy",
        ),
        DemoCase(
            name="dns-failure",
            dns_name="incident-pack-demo.invalid",
            ports=[sandbox.http_port],
            expected_status="degraded",
            expected_reachability="healthy",
        ),
    ]


class DemoRenderer:
    """Present real Incident Pack results as an engineer-readable terminal walkthrough."""

    def __init__(self) -> None:
        self.interactive = sys.stdout.isatty()
        self.pause = 0.28 if self.interactive else 0.0

    def _replace(self, text: str) -> None:
        if not self.interactive:
            return
        sys.stdout.write("\r\033[2K" + text)
        sys.stdout.flush()

    def transition(self, label: str, working: str, final: str, detail: str = "") -> None:
        prefix = f"{label:<20}"
        if self.interactive:
            self._replace(f"{prefix}{working}")
            time.sleep(self.pause)
            self._replace(f"{prefix}{final}")
            sys.stdout.write("\n")
        else:
            print(f"{prefix}{final}")
        if detail:
            print(f"{'':20}{detail}")

    def collect(self, action: Callable[[], IncidentPackResult]) -> IncidentPackResult:
        if not self.interactive:
            print("Collecting live evidence...")
            return action()

        result: list[IncidentPackResult] = []
        error: list[BaseException] = []

        def worker() -> None:
            try:
                result.append(action())
            except BaseException as exc:  # Re-raise on the main thread.
                error.append(exc)

        thread = threading.Thread(target=worker, name="incident-demo-runner", daemon=True)
        thread.start()
        frames = ["|", "/", "-", "\\"]
        index = 0
        while thread.is_alive():
            self._replace(
                f"Collecting live evidence {frames[index % len(frames)]} "
                "(host state, path, DNS, TCP)"
            )
            index += 1
            time.sleep(0.12)
        thread.join()
        self._replace("Collecting live evidence ✓")
        sys.stdout.write("\n")
        if error:
            raise error[0]
        return result[0]

    def show_result(self, result: IncidentPackResult) -> None:
        evidence = result.evidence

        dns = evidence.get("dns") or {}
        if dns:
            answers = list(dns.get("answers") or [])
            if dns.get("error"):
                self.transition(
                    "DNS",
                    "reviewing...",
                    "FAILED",
                    "Name resolution failed. IP/TCP evidence is evaluated separately.",
                )
            else:
                answer_text = ", ".join(str(value) for value in answers[:3]) or "no answers"
                self.transition(
                    "DNS",
                    "reviewing...",
                    "HEALTHY",
                    f"Resolved to {answer_text}.",
                )

        interfaces = evidence.get("interfaces") or {}
        interface_status = str(interfaces.get("status") or "unknown").upper()
        self.transition(
            "Interfaces",
            "reviewing...",
            interface_status,
            (
                f"{interfaces.get('usable_up_count', 0)} usable interface(s) up. "
                "This checks the local host's network state."
            ),
        )

        routes = evidence.get("routes") or {}
        route_status = str(routes.get("status") or "unknown").upper()
        gateway = str(routes.get("default_gateway") or "")
        route_detail = (
            f"Default route present via {gateway}."
            if routes.get("default_route")
            else "No usable default route was parsed."
        )
        self.transition(
            "Routes",
            "reviewing...",
            route_status,
            route_detail + " Routing evidence is kept separate from target reachability.",
        )

        neighbors = evidence.get("neighbors") or {}
        neighbor_status = str(neighbors.get("status") or "unknown").upper()
        self.transition(
            "Neighbors",
            "reviewing...",
            neighbor_status,
            (
                f"{neighbors.get('neighbor_count', 0)} cache entr"
                f"{'y' if neighbors.get('neighbor_count') == 1 else 'ies'}, "
                f"{neighbors.get('unresolved_count', 0)} unresolved."
            ),
        )

        ping = evidence.get("ping") or {}
        ping_status = str(ping.get("status") or "unknown").upper()
        loss = ping.get("packet_loss_percent")
        ping_detail = (
            f"{loss:g}% packet loss. ICMP is useful evidence, but it is not the only "
            "reachability signal."
            if isinstance(loss, (int, float))
            else "No packet-loss statistic was parsed."
        )
        self.transition("Ping", "reviewing...", ping_status, ping_detail)

        trace = evidence.get("traceroute") or {}
        trace_status = str(trace.get("status") or "unknown").upper()
        trace_detail = (
            f"Destination reached in {trace.get('hop_count', 0)} hop(s). "
            f"Intermediate timeout hops: {trace.get('timeout_hops', 0)}."
            if trace.get("target_reached") is True
            else (
                f"Destination not confirmed; responding hops: "
                f"{trace.get('responding_hops', 0)}."
            )
        )
        self.transition("Traceroute", "reviewing...", trace_status, trace_detail)

        for tcp in evidence.get("tcp") or []:
            port = tcp.get("port")
            if tcp.get("ok") is True:
                state = "CONNECTED"
                detail = "The requested service accepted a TCP connection."
            else:
                error_type = str(tcp.get("error_type") or "failed")
                state = error_type.replace("_", " ").upper()
                if error_type == "connection_refused":
                    detail = (
                        "The service is unavailable on this port, but the returned RST "
                        "proves a Layer 4 responder is reachable."
                    )
                elif error_type == "timeout":
                    detail = (
                        "No TCP response was received before timeout. This alone does not "
                        "prove the host is down."
                    )
                else:
                    detail = str(tcp.get("error") or "TCP check failed.")
            self.transition(f"TCP {port}", "connecting...", state, detail)

        summary = evidence.get("collection_summary") or {}
        incomplete = int(summary.get("commands_failed") or 0) + int(
            summary.get("parser_errors") or 0
        )
        collection_state = "COMPLETE" if incomplete == 0 else "INCOMPLETE"
        self.transition(
            "Collection quality",
            "evaluating...",
            collection_state,
            (
                f"{summary.get('commands_succeeded', 0)}/{summary.get('commands_total', 0)} "
                f"host commands succeeded; {summary.get('parser_errors', 0)} parser error(s)."
            ),
        )

        health = evidence.get("health") or {}
        components = health.get("components") or {}
        self.transition(
            "Health decision",
            "evaluating...",
            str(health.get("status") or "unknown").upper(),
        )
        print(f"{'Reachability':<20}{str(health.get('reachability') or 'unknown').upper()}")
        print(
            f"{'TCP service health':<20}"
            f"{str((components.get('tcp') or {}).get('status') or 'unknown').upper()}"
        )

        findings = list(health.get("findings") or [])
        if findings:
            print("\nInterpretation:")
            for finding in findings:
                print(f"  - {finding}")
        elif str(health.get("status") or "") == "healthy":
            print("\nInterpretation:")
            print("  - The requested checks support a healthy target and service path.")

        print("\nReport output:")
        print(f"  JSON     {result.output_paths['json']}")
        print(f"  Markdown {result.output_paths['md']}")


def run_demo(out_dir: str) -> int:
    sandbox = start_sandbox(http_port=0, tcp_port=0, refused_port=0)
    renderer = DemoRenderer()
    failures = 0
    total = 0
    try:
        print("Network Incident Pack — Live Validation")
        print(f"Sandbox target: {sandbox.host}")
        print(
            "Real endpoints: "
            f"HTTP={sandbox.http_port}, TCP={sandbox.tcp_port}, refused={sandbox.refused_port}"
        )

        for case in build_demo_cases(sandbox):
            total += 1
            print("\n" + "=" * 72)
            print(f"Scenario: {case.name}")
            print(f"DNS name: {case.dns_name}")
            print(f"Requested ports: {', '.join(str(port) for port in case.ports)}")
            print("=" * 72)

            case_dir = Path(out_dir) / case.name
            result = renderer.collect(
                lambda case=case, case_dir=case_dir: run_incident_pack(
                    IncidentPackRequest(
                        target=sandbox.host,
                        dns_name=case.dns_name,
                        ports=case.ports,
                        non_interactive=True,
                        out_dir=str(case_dir),
                        tcp_attempts=1,
                        tcp_timeout=1.0,
                    )
                )
            )

            renderer.show_result(result)

            health = result.evidence["health"]
            status = str(health["status"])
            reachability = str(health["reachability"])
            matched = (
                status == case.expected_status
                and reachability == case.expected_reachability
            )
            marker = "PASS" if matched else "FAIL"
            print(
                f"\nScenario result: {marker} — "
                f"status={status}, reachability={reachability}"
            )
            if not matched:
                failures += 1
    finally:
        sandbox.close()

    print("\n" + "=" * 72)
    if failures:
        print(f"Live validation complete: {total - failures}/{total} scenarios matched.")
    else:
        print(f"Live validation complete: {total}/{total} scenarios matched expected outcomes.")
    return 1 if failures else 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run visible healthy/failure Incident Pack live validation."
    )
    parser.add_argument("--out-dir", default="./lab-output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run_demo(args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
