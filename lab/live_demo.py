"""Run a small live demo matrix against the local sandbox."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from incidentpack.application import IncidentPackRequest, run_incident_pack
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


def run_demo(out_dir: str) -> int:
    sandbox = start_sandbox(http_port=0, tcp_port=0, refused_port=0)
    failures = 0
    try:
        print("Live Incident Pack demo matrix")
        print(f"Target: {sandbox.host}")
        print(
            "Ports: "
            f"HTTP={sandbox.http_port}, TCP={sandbox.tcp_port}, refused={sandbox.refused_port}"
        )

        for case in build_demo_cases(sandbox):
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
                )
            )
            health = result.evidence["health"]
            status = str(health["status"])
            reachability = str(health["reachability"])
            matched = (
                status == case.expected_status
                and reachability == case.expected_reachability
            )
            marker = "PASS" if matched else "FAIL"
            print(
                f"{marker:4} {case.name:16} "
                f"status={status:8} reachability={reachability:8} "
                f"report={result.output_paths['md']}"
            )
            if not matched:
                failures += 1
    finally:
        sandbox.close()

    return 1 if failures else 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run live healthy/failure Incident Pack demos.")
    parser.add_argument("--out-dir", default="./lab-output")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run_demo(args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
