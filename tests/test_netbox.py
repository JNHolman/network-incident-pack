import unittest
from unittest import mock

from incidentpack.integrations.netbox import NetBoxClient, NetBoxError, NetBoxSettings


class NetBoxTests(unittest.TestCase):
    def test_settings_require_environment_secrets(self):
        with self.assertRaisesRegex(NetBoxError, "NETBOX_TOKEN"):
            NetBoxSettings.from_env({"NETBOX_URL": "https://netbox.example"})

    def test_settings_reject_plain_http_before_sending_token(self):
        env = {"NETBOX_URL": "http://netbox.example.com", "NETBOX_TOKEN": "secret"}
        with self.assertRaisesRegex(NetBoxError, "must use https"):
            NetBoxSettings.from_env(env)

    def test_token_is_hidden_from_repr(self):
        settings = NetBoxSettings("https://netbox.example", "super-secret-token")
        self.assertNotIn("super-secret-token", repr(settings))

    def test_device_lookup_normalizes_primary_ip_and_metadata(self):
        http = mock.Mock()
        http.request_json.return_value = {
            "count": 1,
            "results": [
                {
                    "name": "edge-01",
                    "primary_ip4": {"address": "10.20.0.1/24", "dns_name": "edge-01.example.com"},
                    "site": {"name": "Louisville"},
                    "role": {"name": "edge-router"},
                }
            ],
        }
        client = NetBoxClient(NetBoxSettings("https://netbox.example", "secret"), http=http)
        device = client.get_device("edge-01")
        self.assertEqual(device.address, "10.20.0.1")
        self.assertEqual(device.dns_name, "edge-01.example.com")
        self.assertEqual(device.site, "Louisville")
        self.assertEqual(device.role, "edge-router")
        _, kwargs = http.request_json.call_args
        self.assertEqual(kwargs["params"]["name"], "edge-01")
        self.assertEqual(kwargs["headers"]["Authorization"], "Token secret")

    def test_device_without_primary_ip_is_rejected(self):
        http = mock.Mock()
        http.request_json.return_value = {"results": [{"name": "edge-01"}]}
        client = NetBoxClient(NetBoxSettings("https://netbox.example", "secret"), http=http)
        with self.assertRaisesRegex(NetBoxError, "no primary IP"):
            client.get_device("edge-01")

    def test_http_failure_is_wrapped_as_netbox_error(self):
        from incidentpack.integrations.http import ApiError

        http = mock.Mock()
        http.request_json.side_effect = ApiError("HTTP 503")
        client = NetBoxClient(NetBoxSettings("https://netbox.example", "secret"), http=http)
        with self.assertRaisesRegex(NetBoxError, "NetBox lookup failed"):
            client.get_device("edge-01")


if __name__ == "__main__":
    unittest.main()
