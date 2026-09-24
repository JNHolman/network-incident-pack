"""Read-only Azure Resource Manager enrichment for virtual-machine network context."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from incidentpack.integrations.http import ApiError, JsonApiClient
from incidentpack.validation import validate_https_endpoint

VM_API_VERSION = "2026-03-01"
NETWORK_API_VERSION = "2025-09-01"
_VM_RESOURCE_RE = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/resourceGroups/(?P<resource_group>[^/]+)/"
    r"providers/Microsoft\.Compute/virtualMachines/(?P<name>[^/]+)$",
    re.IGNORECASE,
)


class AzureError(ApiError):
    """Raised when Azure configuration or ARM response data is invalid."""


@dataclass(frozen=True)
class AzureSettings:
    """Azure ARM endpoint plus short-lived bearer token from the caller environment."""

    access_token: str = field(repr=False)
    management_url: str = "https://management.azure.com"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "AzureSettings":
        values = env if env is not None else os.environ
        token = (values.get("AZURE_ACCESS_TOKEN") or "").strip()
        management_url = (
            values.get("AZURE_MANAGEMENT_URL") or "https://management.azure.com"
        ).strip().rstrip("/")
        if not token:
            raise AzureError("Missing Azure environment variable: AZURE_ACCESS_TOKEN")
        try:
            management_url = validate_https_endpoint(
                management_url, "AZURE_MANAGEMENT_URL"
            )
        except ValueError as error:
            raise AzureError(str(error)) from error
        return cls(access_token=token, management_url=management_url)


@dataclass(frozen=True)
class AzureNicContext:
    name: str
    private_ips: List[str]
    public_ips: List[str]
    virtual_networks: List[str]
    subnets: List[str]
    network_security_group: str = ""

    def to_report(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "private_ips": list(self.private_ips),
            "public_ips": list(self.public_ips),
            "virtual_networks": list(self.virtual_networks),
            "subnets": list(self.subnets),
            "network_security_group": self.network_security_group,
        }


@dataclass(frozen=True)
class AzureVmContext:
    name: str
    resource_group: str
    location: str
    vm_size: str
    provisioning_state: str
    power_state: str
    nics: List[AzureNicContext]

    def to_report(self) -> Dict[str, Any]:
        """Return report-safe Azure metadata without subscription IDs or credentials."""
        return {
            "provider": "azure",
            "resource_type": "virtual_machine",
            "name": self.name,
            "resource_group": self.resource_group,
            "location": self.location,
            "vm_size": self.vm_size,
            "provisioning_state": self.provisioning_state,
            "power_state": self.power_state,
            "network": {"nics": [nic.to_report() for nic in self.nics]},
        }


class AzureClient:
    """Minimal ARM client that enriches a target with VM and NIC network context."""

    def __init__(self, settings: AzureSettings, http: Optional[JsonApiClient] = None) -> None:
        self.settings = settings
        self.http = http or JsonApiClient()

    @property
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.access_token}",
            "Accept": "application/json",
        }

    def get_vm_context(self, resource_id: str) -> AzureVmContext:
        vm_id = self._normalize_vm_resource_id(resource_id)
        match = _VM_RESOURCE_RE.fullmatch(vm_id)
        if match is None:  # defensive; normalize already validates
            raise AzureError("Invalid Azure VM resource ID")

        vm = self._get_resource(
            vm_id,
            api_version=VM_API_VERSION,
            extra_params={"$expand": "instanceView"},
        )
        properties = self._mapping(vm.get("properties"), "Azure VM properties")
        hardware = self._mapping(properties.get("hardwareProfile") or {}, "hardwareProfile")
        network_profile = self._mapping(
            properties.get("networkProfile") or {}, "networkProfile"
        )

        nic_contexts: List[AzureNicContext] = []
        nic_refs = network_profile.get("networkInterfaces") or []
        if not isinstance(nic_refs, list):
            raise AzureError("Azure VM networkProfile.networkInterfaces must be a list")
        for ref in nic_refs:
            if not isinstance(ref, Mapping):
                continue
            nic_id = str(ref.get("id") or "").strip()
            if nic_id:
                nic_contexts.append(self._get_nic_context(nic_id))

        return AzureVmContext(
            name=str(vm.get("name") or match.group("name")).strip(),
            resource_group=match.group("resource_group"),
            location=str(vm.get("location") or "").strip(),
            vm_size=str(hardware.get("vmSize") or "").strip(),
            provisioning_state=str(properties.get("provisioningState") or "").strip(),
            power_state=self._power_state(properties.get("instanceView")),
            nics=nic_contexts,
        )

    def _get_nic_context(self, nic_id: str) -> AzureNicContext:
        nic = self._get_resource(nic_id, api_version=NETWORK_API_VERSION)
        properties = self._mapping(nic.get("properties"), "Azure NIC properties")
        ip_configs = properties.get("ipConfigurations") or []
        if not isinstance(ip_configs, list):
            raise AzureError("Azure NIC properties.ipConfigurations must be a list")

        private_ips: List[str] = []
        public_ips: List[str] = []
        vnets: List[str] = []
        subnets: List[str] = []
        for config in ip_configs:
            if not isinstance(config, Mapping):
                continue
            cfg_props = config.get("properties") or {}
            if not isinstance(cfg_props, Mapping):
                continue
            private_ip = str(cfg_props.get("privateIPAddress") or "").strip()
            if private_ip and private_ip not in private_ips:
                private_ips.append(private_ip)

            subnet = cfg_props.get("subnet") or {}
            if isinstance(subnet, Mapping):
                subnet_id = str(subnet.get("id") or "").strip()
                vnet_name, subnet_name = self._vnet_and_subnet(subnet_id)
                if vnet_name and vnet_name not in vnets:
                    vnets.append(vnet_name)
                if subnet_name and subnet_name not in subnets:
                    subnets.append(subnet_name)

            public_ip = cfg_props.get("publicIPAddress") or {}
            if isinstance(public_ip, Mapping):
                public_ip_id = str(public_ip.get("id") or "").strip()
                if public_ip_id:
                    public_payload = self._get_resource(
                        public_ip_id, api_version=NETWORK_API_VERSION
                    )
                    public_props = public_payload.get("properties") or {}
                    if isinstance(public_props, Mapping):
                        address = str(public_props.get("ipAddress") or "").strip()
                        if address and address not in public_ips:
                            public_ips.append(address)

        nsg = properties.get("networkSecurityGroup") or {}
        nsg_name = ""
        if isinstance(nsg, Mapping):
            nsg_name = self._resource_name(str(nsg.get("id") or ""))

        return AzureNicContext(
            name=str(nic.get("name") or self._resource_name(nic_id)).strip(),
            private_ips=private_ips,
            public_ips=public_ips,
            virtual_networks=vnets,
            subnets=subnets,
            network_security_group=nsg_name,
        )

    def _get_resource(
        self,
        resource_id: str,
        *,
        api_version: str,
        extra_params: Optional[Mapping[str, object]] = None,
    ) -> Mapping[str, Any]:
        normalized = self._normalize_arm_resource_id(resource_id)
        params: Dict[str, object] = {"api-version": api_version}
        params.update(dict(extra_params or {}))
        try:
            payload = self.http.request_json(
                "GET",
                f"{self.settings.management_url}{normalized}",
                headers=self._headers,
                params=params,
            )
        except ApiError as error:
            raise AzureError(f"Azure ARM lookup failed: {error}") from error
        if not isinstance(payload, Mapping):
            raise AzureError("Azure ARM response must be a JSON object")
        return payload

    @staticmethod
    def _normalize_arm_resource_id(resource_id: str) -> str:
        value = resource_id.strip()
        if not value.startswith("/subscriptions/"):
            raise AzureError("Azure resource ID must start with /subscriptions/")
        if any(char.isspace() for char in value):
            raise AzureError("Azure resource ID cannot contain whitespace")
        return value.rstrip("/")

    @classmethod
    def _normalize_vm_resource_id(cls, resource_id: str) -> str:
        value = cls._normalize_arm_resource_id(resource_id)
        if _VM_RESOURCE_RE.fullmatch(value) is None:
            raise AzureError(
                "Azure VM resource ID must identify Microsoft.Compute/virtualMachines"
            )
        return value

    @staticmethod
    def _mapping(value: object, label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise AzureError(f"{label} must be a JSON object")
        return value

    @staticmethod
    def _resource_name(resource_id: str) -> str:
        return resource_id.rstrip("/").rsplit("/", 1)[-1] if resource_id else ""

    @staticmethod
    def _vnet_and_subnet(resource_id: str) -> tuple[str, str]:
        parts = [part for part in resource_id.split("/") if part]
        lowered = [part.lower() for part in parts]
        try:
            vnet_index = lowered.index("virtualnetworks")
            subnet_index = lowered.index("subnets")
        except ValueError:
            return "", ""
        vnet = parts[vnet_index + 1] if vnet_index + 1 < len(parts) else ""
        subnet = parts[subnet_index + 1] if subnet_index + 1 < len(parts) else ""
        return vnet, subnet

    @staticmethod
    def _power_state(instance_view: object) -> str:
        if not isinstance(instance_view, Mapping):
            return ""
        statuses = instance_view.get("statuses") or []
        if not isinstance(statuses, list):
            return ""
        for status in statuses:
            if not isinstance(status, Mapping):
                continue
            code = str(status.get("code") or "")
            if code.lower().startswith("powerstate/"):
                return code.split("/", 1)[1]
        return ""
