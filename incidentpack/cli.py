"""Command-line interface for the Incident Pack application service."""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from incidentpack import __version__
from incidentpack.application import (
    DEFAULT_MD_MAX_LINES,
    IncidentPackRequest,
    run_incident_pack,
)
from incidentpack.config import ConfigurationError
from incidentpack.evidence import (
    DEFAULT_CMD_TIMEOUT,
    DEFAULT_MAX_WORKERS,
    DEFAULT_TCP_ATTEMPTS,
    DEFAULT_TCP_TIMEOUT,
)
from incidentpack.integrations.azure import AzureError
from incidentpack.integrations.netbox import NetBoxError
from incidentpack.inventory import InventoryError
from incidentpack.logging_config import configure_logging
from incidentpack.reporting import ReportValidationError
from incidentpack.scenarios import BASELINE_SCENARIO, MOCK_SCENARIOS
from incidentpack.validation import (
    MAX_COMMAND_TIMEOUT_SECONDS,
    MAX_PORTS_PER_RUN,
    MAX_TCP_ATTEMPTS,
    MAX_TCP_TIMEOUT_SECONDS,
    MAX_WORKERS,
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the public CLI without embedding application workflow logic."""
    parser = argparse.ArgumentParser(
        description="Generate a standardized incident evidence pack (JSON + Markdown)."
    )
    parser.add_argument(
        "--version", action="version", version=f"network-incident-pack {__version__}"
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--target", help="IP or hostname to test directly (e.g., 10.0.0.10)"
    )
    target_group.add_argument("--device", help="Named device to resolve from --config inventory")
    target_group.add_argument(
        "--netbox-device",
        help="Named device to resolve read-only from NetBox using environment credentials",
    )
    parser.add_argument(
        "--config", help="Optional .json/.yaml/.yml site and device inventory configuration"
    )
    parser.add_argument(
        "--dns-name", default=None, help="Optional DNS name override (e.g., app.example.com)"
    )
    parser.add_argument(
        "--ports",
        nargs="*",
        type=int,
        default=None,
        help=f"TCP port override (e.g., 443 80 22; max {MAX_PORTS_PER_RUN} unique ports)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help=f"Command timeout override in seconds (default: {DEFAULT_CMD_TIMEOUT}; max: {MAX_COMMAND_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--non-interactive", action="store_true", help="Skip prompts (empty context fields)"
    )
    parser.add_argument(
        "--mock", action="store_true", help="Generate deterministic sample outputs (for GitHub demos)"
    )
    parser.add_argument(
        "--mock-scenario",
        choices=MOCK_SCENARIOS,
        default=BASELINE_SCENARIO,
        help="Deterministic mock incident scenario (default: baseline; requires --mock for non-baseline scenarios)",
    )
    parser.add_argument("--out-dir", default=".", help="Output directory (default: current)")
    parser.add_argument(
        "--md-max-lines",
        type=int,
        default=DEFAULT_MD_MAX_LINES,
        help=f"Max lines per command in Markdown (default: {DEFAULT_MD_MAX_LINES})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Maximum concurrent collection workers (default: {DEFAULT_MAX_WORKERS}; max: {MAX_WORKERS})",
    )
    parser.add_argument(
        "--tcp-timeout",
        type=float,
        default=None,
        help=f"TCP connect timeout in seconds (default: {DEFAULT_TCP_TIMEOUT}; max: {MAX_TCP_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--tcp-attempts",
        type=int,
        default=None,
        help=f"Maximum TCP attempts for transient failures (default: {DEFAULT_TCP_ATTEMPTS}; max: {MAX_TCP_ATTEMPTS})",
    )
    parser.add_argument(
        "--servicenow-update",
        metavar="INCIDENT",
        help="Append the generated Markdown to an existing ServiceNow incident as work notes",
    )
    parser.add_argument(
        "--azure-vm-resource-id",
        help=(
            "Optional Azure VM resource ID for read-only ARM network/context enrichment; "
            "requires AZURE_ACCESS_TOKEN"
        ),
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Operational log verbosity (default: WARNING)",
    )
    return parser


def _request_from_args(args: argparse.Namespace) -> IncidentPackRequest:
    return IncidentPackRequest(
        target=args.target,
        device=args.device,
        netbox_device=args.netbox_device,
        config_path=args.config,
        dns_name=args.dns_name,
        ports=args.ports,
        timeout=args.timeout,
        non_interactive=args.non_interactive,
        mock=args.mock,
        mock_scenario=args.mock_scenario,
        out_dir=args.out_dir,
        md_max_lines=args.md_max_lines,
        workers=args.workers,
        tcp_timeout=args.tcp_timeout,
        tcp_attempts=args.tcp_attempts,
        servicenow_update=args.servicenow_update,
        azure_vm_resource_id=args.azure_vm_resource_id,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse CLI input, delegate the workflow, and render only terminal-facing output."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)

    try:
        result = run_incident_pack(_request_from_args(args))
    except (
        AzureError,
        ConfigurationError,
        InventoryError,
        NetBoxError,
        ReportValidationError,
        ValueError,
    ) as error:
        parser.error(str(error))

    health = result.evidence.get("health", {})
    status = str(health.get("status") or "unknown").upper()
    reachability = str(health.get("reachability") or "unknown").upper()
    print(f"Status: {status} | Reachability: {reachability}")
    for finding in health.get("findings", []):
        print(f"- {finding}")
    print(f"Wrote:\n- {result.output_paths['json']}\n- {result.output_paths['md']}")
    return result.exit_code
