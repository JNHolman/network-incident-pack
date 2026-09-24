"""Reusable Incident Pack application service, independent from argparse."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from incidentpack.config import (
    command_timeout_from_config,
    load_config,
    positive_float_from_config,
    positive_int_from_config,
)
from incidentpack.evidence import (
    DEFAULT_CMD_TIMEOUT,
    DEFAULT_MAX_WORKERS,
    DEFAULT_TCP_ATTEMPTS,
    DEFAULT_TCP_TIMEOUT,
    collect_live_evidence,
    mock_evidence,
)
from incidentpack.integrations.azure import AzureClient, AzureError, AzureSettings
from incidentpack.integrations.netbox import NetBoxClient, NetBoxSettings
from incidentpack.integrations.servicenow import (
    ServiceNowClient,
    ServiceNowError,
    ServiceNowSettings,
)
from incidentpack.inventory import (
    InventoryError,
    ResolvedTarget,
    resolve_device,
    resolve_direct_target,
)
from incidentpack.reporting import (
    build_markdown,
    sanitize_report,
    validate_report,
    write_outputs,
)
from incidentpack.scenarios import BASELINE_SCENARIO, validate_mock_scenario
from incidentpack.security import redact_secret_text
from incidentpack.validation import (
    normalize_ports,
    validate_md_max_lines,
    validate_ports,
    validate_tcp_attempts,
    validate_tcp_timeout,
    validate_timeout,
    validate_workers,
)

logger = logging.getLogger(__name__)
DEFAULT_MD_MAX_LINES = 40


@dataclass(frozen=True)
class IncidentPackRequest:
    """All runtime inputs required to execute one incident-pack collection."""

    target: Optional[str] = None
    device: Optional[str] = None
    netbox_device: Optional[str] = None
    config_path: Optional[str] = None
    dns_name: Optional[str] = None
    ports: Optional[Sequence[int]] = None
    timeout: Optional[int] = None
    non_interactive: bool = False
    mock: bool = False
    mock_scenario: str = BASELINE_SCENARIO
    out_dir: str = "."
    md_max_lines: int = DEFAULT_MD_MAX_LINES
    workers: Optional[int] = None
    tcp_timeout: Optional[float] = None
    tcp_attempts: Optional[int] = None
    servicenow_update: Optional[str] = None
    azure_vm_resource_id: Optional[str] = None


@dataclass(frozen=True)
class IncidentPackResult:
    """Result returned to CLI callers or other Python automation."""

    evidence: Dict[str, Any]
    output_paths: Dict[str, str]
    exit_code: int


@dataclass(frozen=True)
class RuntimePlan:
    """Resolved target plus effective collection policy after precedence rules."""

    target: ResolvedTarget
    ports: List[int]
    timeout: int
    workers: int
    tcp_timeout: float
    tcp_attempts: int
    inventory: Dict[str, str]


def _resolve_runtime_plan(
    request: IncidentPackRequest,
    *,
    netbox_client_factory: Callable[[NetBoxSettings], NetBoxClient],
) -> RuntimePlan:
    config = load_config(request.config_path) if request.config_path else {}
    if request.device and not request.config_path:
        raise InventoryError("--device requires --config.")

    inventory_source = ""
    if request.netbox_device:
        netbox_client = netbox_client_factory(NetBoxSettings.from_env())
        netbox_device = netbox_client.get_device(request.netbox_device)
        direct = resolve_direct_target(
            netbox_device.address,
            config=config if request.config_path else None,
            cli_dns_name=(
                request.dns_name if request.dns_name is not None else netbox_device.dns_name
            ),
            cli_ports=request.ports,
        )
        resolved = ResolvedTarget(
            address=direct.address,
            dns_name=direct.dns_name,
            ports=direct.ports,
            device=netbox_device.name,
            site=netbox_device.site,
            role=netbox_device.role,
        )
        inventory_source = "netbox"
    elif request.device:
        resolved = resolve_device(
            config,
            request.device,
            cli_dns_name=request.dns_name,
            cli_ports=request.ports,
        )
        inventory_source = Path(request.config_path).name if request.config_path else ""
    else:
        resolved = resolve_direct_target(
            request.target or "",
            config=config if request.config_path else None,
            cli_dns_name=request.dns_name,
            cli_ports=request.ports,
        )

    ports = normalize_ports(resolved.ports)
    validate_ports(ports)
    timeout = (
        request.timeout
        if request.timeout is not None
        else command_timeout_from_config(config, DEFAULT_CMD_TIMEOUT)
    )
    workers = (
        request.workers
        if request.workers is not None
        else positive_int_from_config(config, "max_workers", DEFAULT_MAX_WORKERS)
    )
    tcp_attempts = (
        request.tcp_attempts
        if request.tcp_attempts is not None
        else positive_int_from_config(config, "tcp_attempts", DEFAULT_TCP_ATTEMPTS)
    )
    tcp_timeout = (
        request.tcp_timeout
        if request.tcp_timeout is not None
        else positive_float_from_config(config, "tcp_timeout", DEFAULT_TCP_TIMEOUT)
    )

    validate_timeout(timeout)
    validate_workers(workers)
    validate_tcp_attempts(tcp_attempts)
    validate_tcp_timeout(tcp_timeout)
    validate_md_max_lines(request.md_max_lines)

    inventory = resolved.metadata(inventory_source) if resolved.device or inventory_source else {}
    return RuntimePlan(
        target=resolved,
        ports=ports,
        timeout=timeout,
        workers=workers,
        tcp_timeout=tcp_timeout,
        tcp_attempts=tcp_attempts,
        inventory=inventory,
    )


def run_incident_pack(
    request: IncidentPackRequest,
    *,
    netbox_client_factory: Optional[Callable[[NetBoxSettings], NetBoxClient]] = None,
    servicenow_client_factory: Optional[Callable[[ServiceNowSettings], ServiceNowClient]] = None,
    azure_client_factory: Optional[Callable[[AzureSettings], AzureClient]] = None,
    mock_builder: Callable[..., Dict[str, Any]] = mock_evidence,
    live_collector: Callable[..., Dict[str, Any]] = collect_live_evidence,
) -> IncidentPackResult:
    """Execute one complete incident-pack workflow and return a reusable result object."""
    resolved_netbox_factory = netbox_client_factory or NetBoxClient
    resolved_servicenow_factory = servicenow_client_factory or ServiceNowClient
    resolved_azure_factory = azure_client_factory or AzureClient
    scenario = validate_mock_scenario(request.mock_scenario)
    if not request.mock and scenario != BASELINE_SCENARIO:
        raise ValueError("--mock-scenario requires --mock.")
    plan = _resolve_runtime_plan(request, netbox_client_factory=resolved_netbox_factory)
    resolved = plan.target
    logger.info(
        "Starting incident pack target=%s device=%s site=%s mode=%s ports=%s workers=%s",
        resolved.address,
        resolved.device or "direct",
        resolved.site or "",
        "mock" if request.mock else "live",
        plan.ports,
        plan.workers,
    )

    common = {
        "target": resolved.address,
        "dns_name": resolved.dns_name,
        "ports": plan.ports,
        "inventory": plan.inventory,
        "timeout": plan.timeout,
        "tcp_timeout": plan.tcp_timeout,
        "tcp_attempts": plan.tcp_attempts,
        "max_workers": plan.workers,
    }
    if request.mock:
        if scenario == BASELINE_SCENARIO:
            # Preserve compatibility with injected mock builders that predate named scenarios.
            evidence = mock_builder(**common)
        else:
            evidence = mock_builder(**common, scenario=scenario)
    else:
        evidence = live_collector(non_interactive=request.non_interactive, **common)

    # Redact recognizable credential content before validation or any external handoff.
    evidence = sanitize_report(evidence)
    validate_report(evidence)

    exit_code = 0
    if request.azure_vm_resource_id:
        try:
            azure = resolved_azure_factory(AzureSettings.from_env())
            context = azure.get_vm_context(request.azure_vm_resource_id)
            evidence["cloud"] = context.to_report()
            evidence.setdefault("integrations", {})["azure"] = {
                "status": "enriched",
                "resource": context.name,
            }
            logger.info("Enriched report from Azure VM=%s", context.name)
        except AzureError as error:
            evidence.setdefault("integrations", {})["azure"] = {
                "status": "failed",
                "error": str(error),
            }
            logger.error("Azure enrichment failed: %s", redact_secret_text(str(error)))
            exit_code = 1

    if request.servicenow_update:
        try:
            notes = build_markdown(evidence, md_max_lines=request.md_max_lines)
            client = resolved_servicenow_factory(ServiceNowSettings.from_env())
            incident = client.add_work_notes(request.servicenow_update, notes)
            evidence.setdefault("integrations", {})["servicenow"] = {
                "status": "updated",
                "incident": incident.number,
            }
            logger.info("Updated ServiceNow incident=%s", incident.number)
        except ServiceNowError as error:
            evidence.setdefault("integrations", {})["servicenow"] = {
                "status": "failed",
                "incident": request.servicenow_update.strip().upper(),
                "error": str(error),
            }
            logger.error("ServiceNow update failed: %s", redact_secret_text(str(error)))
            exit_code = 1

    # Integrations mutate the report, so sanitize and enforce the contract again.
    evidence = sanitize_report(evidence)
    validate_report(evidence)
    output_paths = write_outputs(
        evidence,
        out_dir=request.out_dir,
        md_max_lines=request.md_max_lines,
    )
    logger.info(
        "Incident pack complete json=%s markdown=%s",
        output_paths["json"],
        output_paths["md"],
    )
    return IncidentPackResult(
        evidence=evidence,
        output_paths=output_paths,
        exit_code=exit_code,
    )
