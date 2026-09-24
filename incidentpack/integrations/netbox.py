"""Read-only NetBox-style device inventory lookup."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from incidentpack.integrations.http import ApiError, JsonApiClient
from incidentpack.inventory import ResolvedTarget
from incidentpack.validation import validate_https_endpoint


class NetBoxError(ApiError):
    """Raised when NetBox configuration or lookup data is invalid."""


@dataclass(frozen=True)
class NetBoxSettings:
    url: str
    token: str = field(repr=False)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "NetBoxSettings":
        values = env if env is not None else os.environ
        url = (values.get("NETBOX_URL") or "").strip().rstrip("/")
        token = (values.get("NETBOX_TOKEN") or "").strip()
        missing = [
            name
            for name, value in (("NETBOX_URL", url), ("NETBOX_TOKEN", token))
            if not value
        ]
        if missing:
            raise NetBoxError(f"Missing NetBox environment variable(s): {', '.join(missing)}")
        try:
            url = validate_https_endpoint(url, "NETBOX_URL")
        except ValueError as error:
            raise NetBoxError(str(error)) from error
        return cls(url=url, token=token)


@dataclass(frozen=True)
class NetBoxDevice:
    name: str
    address: str
    dns_name: str = ""
    site: str = ""
    role: str = ""

    def resolved_target(self, ports: Sequence[int]) -> ResolvedTarget:
        return ResolvedTarget(
            address=self.address,
            dns_name=self.dns_name or None,
            ports=list(ports),
            device=self.name,
            site=self.site,
            role=self.role,
        )


class NetBoxClient:
    """Minimal read-only client for the NetBox DCIM devices endpoint."""

    def __init__(self, settings: NetBoxSettings, http: Optional[JsonApiClient] = None) -> None:
        self.settings = settings
        self.http = http or JsonApiClient()

    def get_device(self, name: str) -> NetBoxDevice:
        device_name = name.strip()
        if not device_name:
            raise NetBoxError("NetBox device name cannot be empty")

        try:
            payload = self.http.request_json(
                "GET",
                f"{self.settings.url}/api/dcim/devices/",
                headers={
                    "Authorization": f"Token {self.settings.token}",
                    "Accept": "application/json",
                },
                params={"name": device_name, "limit": 2},
            )
        except ApiError as error:
            raise NetBoxError(f"NetBox lookup failed: {error}") from error
        if not isinstance(payload, dict):
            raise NetBoxError("NetBox device response must be a JSON object")
        results = payload.get("results")
        if not isinstance(results, list):
            raise NetBoxError("NetBox device response is missing a results list")
        if not results:
            raise NetBoxError(f"Device '{device_name}' was not found in NetBox")
        if len(results) > 1:
            raise NetBoxError(f"Device lookup for '{device_name}' returned multiple matches")

        device = results[0]
        if not isinstance(device, dict):
            raise NetBoxError("NetBox device result must be a JSON object")

        address, dns_name = self._primary_ip(device)
        site = self._named_object(device.get("site"))
        role = self._named_object(device.get("role") or device.get("device_role"))
        actual_name = str(device.get("name") or device_name).strip()
        return NetBoxDevice(
            name=actual_name,
            address=address,
            dns_name=dns_name,
            site=site,
            role=role,
        )

    @staticmethod
    def _named_object(value: object) -> str:
        if isinstance(value, dict):
            return str(value.get("name") or value.get("display") or "").strip()
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def _primary_ip(device: Mapping[str, Any]) -> tuple[str, str]:
        primary = device.get("primary_ip4") or device.get("primary_ip")
        if not isinstance(primary, dict):
            raise NetBoxError("NetBox device has no primary IP address")
        address_value = str(primary.get("address") or "").strip()
        if not address_value:
            raise NetBoxError("NetBox primary IP object has no address")
        try:
            address = str(ipaddress.ip_interface(address_value).ip)
        except ValueError as error:
            raise NetBoxError(f"Invalid NetBox primary IP address: {address_value}") from error
        dns_name = str(primary.get("dns_name") or "").strip()
        return address, dns_name
