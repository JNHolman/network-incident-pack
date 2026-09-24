import os
import unittest
from unittest import mock

from incidentpack.integrations.azure import (
    AzureClient,
    AzureError,
    AzureSettings,
)


VM_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/incident-pack-lab/providers/Microsoft.Compute/virtualMachines/ip-lab-vm"
)
NIC_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/incident-pack-lab/providers/Microsoft.Network/networkInterfaces/ip-lab-nic"
)
PIP_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/incident-pack-lab/providers/Microsoft.Network/publicIPAddresses/ip-lab-pip"
)
SUBNET_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/incident-pack-lab/providers/Microsoft.Network/virtualNetworks/ip-lab-vnet/"
    "subnets/default"
)
NSG_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/"
    "resourceGroups/incident-pack-lab/providers/Microsoft.Network/networkSecurityGroups/ip-lab-nsg"
)


class AzureIntegrationTests(unittest.TestCase):
    def test_settings_require_token_and_hide_it_from_repr(self):
        with self.assertRaisesRegex(AzureError, "AZURE_ACCESS_TOKEN"):
            AzureSettings.from_env({})
        settings = AzureSettings.from_env({"AZURE_ACCESS_TOKEN": "super-secret"})
        self.assertNotIn("super-secret", repr(settings))

    def test_rejects_non_vm_resource_id(self):
        client = AzureClient(AzureSettings(access_token="x"), http=mock.Mock())
        with self.assertRaisesRegex(AzureError, "virtualMachines"):
            client.get_vm_context(
                "/subscriptions/x/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/nic"
            )

    def test_vm_context_collects_network_metadata_without_subscription_id(self):
        http = mock.Mock()
        http.request_json.side_effect = [
            {
                "name": "ip-lab-vm",
                "location": "eastus",
                "properties": {
                    "provisioningState": "Succeeded",
                    "hardwareProfile": {"vmSize": "Standard_B1s"},
                    "instanceView": {
                        "statuses": [
                            {"code": "ProvisioningState/succeeded"},
                            {"code": "PowerState/running"},
                        ]
                    },
                    "networkProfile": {"networkInterfaces": [{"id": NIC_ID}]},
                },
            },
            {
                "name": "ip-lab-nic",
                "properties": {
                    "networkSecurityGroup": {"id": NSG_ID},
                    "ipConfigurations": [
                        {
                            "properties": {
                                "privateIPAddress": "10.10.1.4",
                                "subnet": {"id": SUBNET_ID},
                                "publicIPAddress": {"id": PIP_ID},
                            }
                        }
                    ],
                },
            },
            {"name": "ip-lab-pip", "properties": {"ipAddress": "20.30.40.50"}},
        ]
        client = AzureClient(AzureSettings(access_token="secret"), http=http)
        report = client.get_vm_context(VM_ID).to_report()

        self.assertEqual(report["provider"], "azure")
        self.assertEqual(report["name"], "ip-lab-vm")
        self.assertEqual(report["resource_group"], "incident-pack-lab")
        self.assertEqual(report["power_state"], "running")
        self.assertEqual(report["network"]["nics"][0]["private_ips"], ["10.10.1.4"])
        self.assertEqual(report["network"]["nics"][0]["public_ips"], ["20.30.40.50"])
        self.assertEqual(report["network"]["nics"][0]["virtual_networks"], ["ip-lab-vnet"])
        self.assertEqual(report["network"]["nics"][0]["subnets"], ["default"])
        self.assertEqual(report["network"]["nics"][0]["network_security_group"], "ip-lab-nsg")
        self.assertNotIn("subscription", str(report).lower())
        self.assertNotIn("00000000-0000-0000-0000-000000000000", str(report))

    def test_arm_requests_use_bearer_header_but_token_never_enters_report(self):
        http = mock.Mock()
        http.request_json.side_effect = [
            {
                "name": "ip-lab-vm",
                "location": "eastus",
                "properties": {
                    "hardwareProfile": {},
                    "networkProfile": {"networkInterfaces": []},
                    "instanceView": {"statuses": []},
                },
            }
        ]
        client = AzureClient(AzureSettings(access_token="secret-token"), http=http)
        report = client.get_vm_context(VM_ID).to_report()
        kwargs = http.request_json.call_args.kwargs
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertNotIn("secret-token", str(report))

    def test_settings_reject_plain_http_management_endpoint(self):
        env = {
            "AZURE_ACCESS_TOKEN": "token",
            "AZURE_MANAGEMENT_URL": "http://management.azure.com",
        }
        with self.assertRaisesRegex(AzureError, "must use https"):
            AzureSettings.from_env(env)


if __name__ == "__main__":
    unittest.main()
