#!/usr/bin/env python3
"""Compatibility entrypoint for the modular Incident Pack package.

The implementation now lives under ``incidentpack``. Existing users can keep
running ``python incident_pack.py`` and importing the historical helper names.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

from incidentpack.application import (
    DEFAULT_MD_MAX_LINES,
    IncidentPackRequest,
    IncidentPackResult,
    run_incident_pack,
)
from incidentpack.cli import build_arg_parser, main
from incidentpack.collectors.host import run_host_commands
from incidentpack.collectors.tcp import run_tcp_checks, tcp_check
from incidentpack.evidence import (
    DEFAULT_CMD_TIMEOUT,
    DEFAULT_MAX_WORKERS,
    DEFAULT_TCP_ATTEMPTS,
    DEFAULT_TCP_TIMEOUT,
    MOCK_OS,
    MOCK_TIMESTAMP_UTC,
    REPORT_SCHEMA_VERSION,
    collect_live_evidence,
    mock_evidence,
)
from incidentpack.host_context import detect_os, now_utc_iso, os_commands, prompt_context, resolve
from incidentpack.integrations.netbox import NetBoxClient, NetBoxError, NetBoxSettings
from incidentpack.integrations.servicenow import (
    ServiceNowClient,
    ServiceNowError,
    ServiceNowSettings,
)
from incidentpack.reporting import (
    CURRENT_SCHEMA_VERSION,
    ReportValidationError,
    build_collection_summary,
    build_markdown,
    choose_output_base,
    sanitize_filename_component,
    validate_report,
    write_outputs,
)
from incidentpack.runner import run_command
from incidentpack.validation import (
    normalize_ports,
    validate_md_max_lines,
    validate_ports,
    validate_tcp_attempts,
    validate_tcp_timeout,
    validate_timeout,
    validate_workers,
)


def run(cmd: Sequence[str], timeout: int = DEFAULT_CMD_TIMEOUT) -> Dict[str, Any]:
    """Historical wrapper retained for callers that imported ``incident_pack.run``."""
    return run_command(cmd, timeout=timeout)


if __name__ == "__main__":
    raise SystemExit(main())
