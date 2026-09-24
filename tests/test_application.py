import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from incidentpack.integrations.azure import AzureNicContext, AzureVmContext

from incidentpack.application import IncidentPackRequest, run_incident_pack
from incidentpack.integrations.netbox import NetBoxDevice
from incidentpack.integrations.servicenow import ServiceNowError


class ApplicationServiceTests(unittest.TestCase):
    def test_mock_workflow_runs_without_argparse(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_incident_pack(
                IncidentPackRequest(
                    target="10.20.30.40",
                    dns_name="app.example.com",
                    ports=[443, 22],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                )
            )
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(result.evidence["meta"]["target"], "10.20.30.40")
            self.assertTrue(Path(result.output_paths["json"]).exists())
            self.assertTrue(Path(result.output_paths["md"]).exists())

    def test_netbox_client_factory_is_injectable(self):
        client = mock.Mock()
        client.get_device.return_value = NetBoxDevice(
            name="edge-01",
            address="10.20.0.1",
            dns_name="edge-01.example.com",
            site="Louisville",
            role="edge-router",
        )
        factory = mock.Mock(return_value=client)
        env = {"NETBOX_URL": "https://netbox.example.com", "NETBOX_TOKEN": "demo-token"}
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, env, clear=False):
            result = run_incident_pack(
                IncidentPackRequest(
                    netbox_device="edge-01",
                    ports=[443],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                ),
                netbox_client_factory=factory,
            )
        self.assertEqual(result.evidence["meta"]["target"], "10.20.0.1")
        self.assertEqual(result.evidence["inventory"]["source"], "netbox")
        factory.assert_called_once()
        client.get_device.assert_called_once_with("edge-01")

    def test_servicenow_client_factory_is_injectable(self):
        client = mock.Mock()
        client.add_work_notes.return_value = mock.Mock(number="INC0012345")
        factory = mock.Mock(return_value=client)
        env = {
            "SERVICENOW_URL": "https://instance.service-now.com",
            "SERVICENOW_USER": "api-user",
            "SERVICENOW_PASSWORD": "demo-password",
        }
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, env, clear=False):
            result = run_incident_pack(
                IncidentPackRequest(
                    target="1.1.1.1",
                    ports=[443],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                    servicenow_update="INC0012345",
                ),
                servicenow_client_factory=factory,
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(
            result.evidence["integrations"]["servicenow"],
            {"status": "updated", "incident": "INC0012345"},
        )
        client.add_work_notes.assert_called_once()

    def test_servicenow_failure_preserves_report_and_nonzero_result(self):
        client = mock.Mock()
        client.add_work_notes.side_effect = ServiceNowError("API unavailable")
        env = {
            "SERVICENOW_URL": "https://instance.service-now.com",
            "SERVICENOW_USER": "api-user",
            "SERVICENOW_PASSWORD": "demo-password",
        }
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, env, clear=False):
            result = run_incident_pack(
                IncidentPackRequest(
                    target="1.1.1.1",
                    ports=[443],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                    servicenow_update="INC0012345",
                ),
                servicenow_client_factory=lambda settings: client,
            )
            payload = json.loads(Path(result.output_paths["json"]).read_text(encoding="utf-8"))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(payload["integrations"]["servicenow"]["status"], "failed")
        self.assertIn("API unavailable", payload["integrations"]["servicenow"]["error"])

    def test_live_collector_can_be_injected_for_application_test(self):
        calls = []

        def fake_live_collector(**kwargs):
            calls.append(kwargs)
            from incidentpack.evidence import mock_evidence

            evidence = mock_evidence(
                kwargs["target"],
                kwargs["dns_name"],
                kwargs["ports"],
                inventory=kwargs["inventory"],
                timeout=kwargs["timeout"],
                tcp_timeout=kwargs["tcp_timeout"],
                tcp_attempts=kwargs["tcp_attempts"],
                max_workers=kwargs["max_workers"],
            )
            evidence["meta"]["mode"] = "live"
            return evidence

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_incident_pack(
                IncidentPackRequest(
                    target="1.1.1.1",
                    ports=[443],
                    non_interactive=True,
                    out_dir=tmpdir,
                ),
                live_collector=fake_live_collector,
            )
        self.assertEqual(result.evidence["meta"]["mode"], "live")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["non_interactive"])

    def test_azure_enrichment_is_injectable_and_report_safe(self):
        context = AzureVmContext(
            name="ip-lab-vm",
            resource_group="incident-pack-lab",
            location="eastus",
            vm_size="Standard_B1s",
            provisioning_state="Succeeded",
            power_state="running",
            nics=[
                AzureNicContext(
                    name="ip-lab-nic",
                    private_ips=["10.10.1.4"],
                    public_ips=["20.30.40.50"],
                    virtual_networks=["ip-lab-vnet"],
                    subnets=["default"],
                    network_security_group="ip-lab-nsg",
                )
            ],
        )
        client = mock.Mock()
        client.get_vm_context.return_value = context
        env = {"AZURE_ACCESS_TOKEN": "temporary-arm-token"}
        resource_id = (
            "/subscriptions/00000000-0000-0000-0000-000000000000/"
            "resourceGroups/incident-pack-lab/providers/Microsoft.Compute/virtualMachines/ip-lab-vm"
        )
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, env, clear=False):
            result = run_incident_pack(
                IncidentPackRequest(
                    target="20.30.40.50",
                    ports=[22],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                    azure_vm_resource_id=resource_id,
                ),
                azure_client_factory=lambda settings: client,
            )
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.evidence["cloud"]["provider"], "azure")
        self.assertEqual(result.evidence["integrations"]["azure"]["status"], "enriched")
        self.assertNotIn("temporary-arm-token", str(result.evidence))
        self.assertNotIn("00000000-0000-0000-0000-000000000000", str(result.evidence))

    def test_azure_enrichment_failure_preserves_local_report(self):
        from incidentpack.integrations.azure import AzureError

        client = mock.Mock()
        client.get_vm_context.side_effect = AzureError("ARM denied")
        env = {"AZURE_ACCESS_TOKEN": "temporary-arm-token"}
        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.dict(os.environ, env, clear=False):
            result = run_incident_pack(
                IncidentPackRequest(
                    target="20.30.40.50",
                    ports=[22],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                    azure_vm_resource_id=(
                        "/subscriptions/00000000-0000-0000-0000-000000000000/"
                        "resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
                    ),
                ),
                azure_client_factory=lambda settings: client,
            )
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(result.evidence["integrations"]["azure"]["status"], "failed")
        self.assertIn("ARM denied", result.evidence["integrations"]["azure"]["error"])

    def test_config_cannot_bypass_runtime_worker_limit(self):
        import yaml
        from incidentpack.validation import MAX_WORKERS

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "inventory.yaml")
            with open(config_path, "w", encoding="utf-8") as handle:
                yaml.safe_dump(
                    {
                        "version": 1,
                        "defaults": {"max_workers": MAX_WORKERS + 1},
                    },
                    handle,
                )
            with self.assertRaisesRegex(ValueError, "--workers cannot exceed"):
                run_incident_pack(
                    IncidentPackRequest(
                        target="10.20.30.40",
                        ports=[443],
                        config_path=config_path,
                        mock=True,
                        non_interactive=True,
                        out_dir=tmpdir,
                    )
                )

    def test_nonbaseline_mock_scenario_requires_mock_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, "requires --mock"):
                run_incident_pack(
                    IncidentPackRequest(
                        target="10.20.30.40",
                        ports=[443],
                        mock=False,
                        mock_scenario="unreachable",
                        non_interactive=True,
                        out_dir=tmpdir,
                    )
                )

    def test_mock_scenario_flows_through_application_service(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_incident_pack(
                IncidentPackRequest(
                    target="10.20.30.40",
                    ports=[443],
                    mock=True,
                    mock_scenario="unreachable",
                    non_interactive=True,
                    out_dir=tmpdir,
                )
            )
        self.assertEqual(result.evidence["meta"]["scenario"], "unreachable")
        self.assertEqual(result.evidence["health"]["status"], "failed")

    def test_baseline_keeps_legacy_injected_mock_builder_signature(self):
        calls = []

        def legacy_mock_builder(target, dns_name, ports, inventory=None, *, timeout, tcp_timeout, tcp_attempts, max_workers):
            calls.append(target)
            from incidentpack.evidence import mock_evidence
            return mock_evidence(
                target,
                dns_name,
                ports,
                inventory=inventory,
                timeout=timeout,
                tcp_timeout=tcp_timeout,
                tcp_attempts=tcp_attempts,
                max_workers=max_workers,
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_incident_pack(
                IncidentPackRequest(
                    target="10.20.30.40",
                    ports=[443],
                    mock=True,
                    non_interactive=True,
                    out_dir=tmpdir,
                ),
                mock_builder=legacy_mock_builder,
            )
        self.assertEqual(calls, ["10.20.30.40"])
        self.assertEqual(result.evidence["meta"]["scenario"], "baseline")


if __name__ == "__main__":
    unittest.main()
