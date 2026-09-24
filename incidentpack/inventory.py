"""Resolve named devices and site defaults from Incident Pack inventory configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from incidentpack.validation import validate_host


class InventoryError(ValueError):
    """Raised when inventory data is invalid or a requested device cannot be resolved."""


@dataclass(frozen=True)
class ResolvedTarget:
    """Runtime target produced from CLI overrides plus inventory configuration."""

    address: str
    dns_name: Optional[str]
    ports: List[int]
    device: str = ""
    site: str = ""
    role: str = ""

    def metadata(self, source: str = "") -> Dict[str, str]:
        """Return report-safe inventory metadata for the evidence document."""
        return {
            "source": source,
            "device": self.device,
            "site": self.site,
            "role": self.role,
        }


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    """Require a mapping for one inventory object."""
    if not isinstance(value, dict):
        raise InventoryError(f"{label} must be a mapping/object.")
    return value


def _optional_text(value: object, label: str) -> str:
    """Normalize an optional text inventory field."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InventoryError(f"{label} must be a string.")
    return value.strip()


def _ports(value: object, label: str) -> List[int]:
    """Validate and normalize one configured port list."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise InventoryError(f"{label} must be a list of TCP ports.")

    out: List[int] = []
    seen = set()
    for port in value:
        if isinstance(port, bool) or not isinstance(port, int):
            raise InventoryError(f"{label} must contain integers only.")
        if port < 1 or port > 65535:
            raise InventoryError(
                f"{label} contains invalid TCP port {port}; valid range is 1-65535."
            )
        if port not in seen:
            out.append(port)
            seen.add(port)
    return out


def _cli_ports(ports: Optional[Sequence[int]]) -> Optional[List[int]]:
    """Normalize optional CLI ports while preserving whether an override was supplied."""
    if ports is None:
        return None
    return _ports(list(ports), "CLI --ports")


def resolve_device(
    config: Mapping[str, Any],
    device_name: str,
    *,
    cli_dns_name: Optional[str] = None,
    cli_ports: Optional[Sequence[int]] = None,
) -> ResolvedTarget:
    """Resolve a named device using CLI > device > site > global precedence."""
    name = device_name.strip()
    if not name:
        raise InventoryError("--device cannot be empty.")

    devices = _mapping(config.get("devices", {}), "Configuration section 'devices'")
    if name not in devices:
        raise InventoryError(f"Device '{name}' was not found in inventory.")
    device = _mapping(devices[name], f"Device '{name}'")

    address = _optional_text(device.get("address"), f"devices.{name}.address")
    if not address:
        raise InventoryError(f"devices.{name}.address is required.")
    try:
        address = validate_host(address, f"devices.{name}.address")
    except ValueError as error:
        raise InventoryError(str(error)) from error

    site_name = _optional_text(device.get("site"), f"devices.{name}.site")
    site: Mapping[str, Any] = {}
    if site_name:
        sites = _mapping(config.get("sites", {}), "Configuration section 'sites'")
        if site_name not in sites:
            raise InventoryError(
                f"Device '{name}' references unknown site '{site_name}'."
            )
        site = _mapping(sites[site_name], f"Site '{site_name}'")

    role = _optional_text(device.get("role"), f"devices.{name}.role")

    cli_port_values = _cli_ports(cli_ports)
    if cli_port_values is not None:
        resolved_ports = cli_port_values
    elif "ports" in device:
        resolved_ports = _ports(device.get("ports"), f"devices.{name}.ports")
    elif site_name and "default_ports" in site:
        resolved_ports = _ports(site.get("default_ports"), f"sites.{site_name}.default_ports")
    else:
        defaults = _mapping(config.get("defaults", {}), "Configuration section 'defaults'")
        resolved_ports = _ports(defaults.get("ports"), "defaults.ports")

    if cli_dns_name is not None:
        dns_name = cli_dns_name.strip() or None
        if dns_name:
            try:
                dns_name = validate_host(dns_name, "--dns-name")
            except ValueError as error:
                raise InventoryError(str(error)) from error
    else:
        configured_dns = _optional_text(device.get("dns_name"), f"devices.{name}.dns_name")
        if configured_dns:
            try:
                configured_dns = validate_host(configured_dns, f"devices.{name}.dns_name")
            except ValueError as error:
                raise InventoryError(str(error)) from error
        dns_name = configured_dns or None

    return ResolvedTarget(
        address=address,
        dns_name=dns_name,
        ports=resolved_ports,
        device=name,
        site=site_name,
        role=role,
    )


def resolve_direct_target(
    target: str,
    *,
    config: Optional[Mapping[str, Any]] = None,
    cli_dns_name: Optional[str] = None,
    cli_ports: Optional[Sequence[int]] = None,
) -> ResolvedTarget:
    """Resolve a direct target, optionally inheriting global configured port defaults."""
    address = target.strip()
    if not address:
        raise InventoryError("--target cannot be empty.")
    try:
        address = validate_host(address, "--target")
    except ValueError as error:
        raise InventoryError(str(error)) from error

    cli_port_values = _cli_ports(cli_ports)
    if cli_port_values is not None:
        resolved_ports = cli_port_values
    elif config is not None:
        defaults = _mapping(config.get("defaults", {}), "Configuration section 'defaults'")
        resolved_ports = _ports(defaults.get("ports"), "defaults.ports")
    else:
        resolved_ports = []

    dns_name = cli_dns_name.strip() if cli_dns_name is not None else ""
    if dns_name:
        try:
            dns_name = validate_host(dns_name, "--dns-name")
        except ValueError as error:
            raise InventoryError(str(error)) from error
    return ResolvedTarget(
        address=address,
        dns_name=dns_name or None,
        ports=resolved_ports,
    )
