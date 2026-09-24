import unittest

from incidentpack.inventory import InventoryError, resolve_device, resolve_direct_target

CONFIG = {
    "version": 1,
    "defaults": {"ports": [443, 80, 22]},
    "sites": {
        "site-a": {"default_ports": [443, 22]},
        "site-b": {},
    },
    "devices": {
        "app01": {
            "address": "10.20.30.40",
            "dns_name": "app01.example.com",
            "site": "site-a",
            "role": "application-server",
        },
        "fw01": {
            "address": "10.20.0.1",
            "site": "site-a",
            "role": "firewall",
            "ports": [443, 8443, 443],
        },
        "db01": {
            "address": "10.30.40.50",
            "site": "site-b",
        },
    },
}


class InventoryTests(unittest.TestCase):
    def test_site_defaults_are_used_when_device_has_no_ports(self):
        target = resolve_device(CONFIG, "app01")
        self.assertEqual(target.address, "10.20.30.40")
        self.assertEqual(target.dns_name, "app01.example.com")
        self.assertEqual(target.ports, [443, 22])
        self.assertEqual(target.site, "site-a")
        self.assertEqual(target.role, "application-server")

    def test_device_ports_override_site_and_global_defaults(self):
        target = resolve_device(CONFIG, "fw01")
        self.assertEqual(target.ports, [443, 8443])

    def test_global_ports_are_used_when_site_has_no_defaults(self):
        target = resolve_device(CONFIG, "db01")
        self.assertEqual(target.ports, [443, 80, 22])

    def test_cli_overrides_device_dns_and_ports(self):
        target = resolve_device(
            CONFIG,
            "fw01",
            cli_dns_name="override.example.com",
            cli_ports=[22, 9443, 22],
        )
        self.assertEqual(target.dns_name, "override.example.com")
        self.assertEqual(target.ports, [22, 9443])

    def test_direct_target_can_inherit_global_ports(self):
        target = resolve_direct_target("1.1.1.1", config=CONFIG)
        self.assertEqual(target.address, "1.1.1.1")
        self.assertEqual(target.ports, [443, 80, 22])
        self.assertEqual(target.device, "")

    def test_direct_target_rejects_option_injection(self):
        with self.assertRaisesRegex(InventoryError, "cannot begin"):
            resolve_direct_target("--help")

    def test_inventory_rejects_invalid_command_target(self):
        config = {
            "devices": {"bad01": {"address": "-i"}},
            "sites": {},
            "defaults": {},
        }
        with self.assertRaisesRegex(InventoryError, "cannot begin"):
            resolve_device(config, "bad01")

    def test_direct_target_accepts_scoped_ipv6(self):
        target = resolve_direct_target("fe80::1%eth0")
        self.assertEqual(target.address, "fe80::1%eth0")

    def test_unknown_device_is_rejected(self):
        with self.assertRaisesRegex(InventoryError, "was not found"):
            resolve_device(CONFIG, "missing01")

    def test_unknown_site_reference_is_rejected(self):
        config = {
            "devices": {"app01": {"address": "10.0.0.1", "site": "missing-site"}},
            "sites": {},
            "defaults": {},
        }
        with self.assertRaisesRegex(InventoryError, "unknown site"):
            resolve_device(config, "app01")

    def test_missing_address_is_rejected(self):
        config = {"devices": {"app01": {}}, "sites": {}, "defaults": {}}
        with self.assertRaisesRegex(InventoryError, "address is required"):
            resolve_device(config, "app01")

    def test_invalid_configured_port_is_rejected(self):
        config = {
            "devices": {"app01": {"address": "10.0.0.1", "ports": [443, 70000]}},
            "sites": {},
            "defaults": {},
        }
        with self.assertRaisesRegex(InventoryError, "invalid TCP port"):
            resolve_device(config, "app01")

    def test_metadata_is_report_safe(self):
        target = resolve_device(CONFIG, "app01")
        self.assertEqual(
            target.metadata("config/inventory.yaml"),
            {
                "source": "config/inventory.yaml",
                "device": "app01",
                "site": "site-a",
                "role": "application-server",
            },
        )


if __name__ == "__main__":
    unittest.main()
