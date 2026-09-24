import unittest
from unittest import mock

from incidentpack.integrations.servicenow import (
    ServiceNowClient,
    ServiceNowError,
    ServiceNowSettings,
)


class ServiceNowTests(unittest.TestCase):
    def test_settings_require_environment_credentials(self):
        with self.assertRaisesRegex(ServiceNowError, "SERVICENOW_PASSWORD"):
            ServiceNowSettings.from_env(
                {"SERVICENOW_URL": "https://dev.service-now.com", "SERVICENOW_USER": "api-user"}
            )

    def test_settings_reject_plain_http_before_sending_credentials(self):
        env = {
            "SERVICENOW_URL": "http://instance.service-now.com",
            "SERVICENOW_USER": "api-user",
            "SERVICENOW_PASSWORD": "secret",
        }
        with self.assertRaisesRegex(ServiceNowError, "must use https"):
            ServiceNowSettings.from_env(env)

    def test_password_is_hidden_from_repr(self):
        settings = ServiceNowSettings("https://dev.service-now.com", "api-user", "super-secret")
        self.assertNotIn("super-secret", repr(settings))

    def test_add_work_notes_looks_up_number_then_patches_sys_id(self):
        http = mock.Mock()
        http.request_json.side_effect = [
            {
                "result": [
                    {
                        "sys_id": "abc123",
                        "number": "INC0012345",
                        "short_description": "Site outage",
                        "state": "2",
                        "priority": "2",
                    }
                ]
            },
            {"result": {"sys_id": "abc123", "number": "INC0012345"}},
        ]
        client = ServiceNowClient(
            ServiceNowSettings("https://dev.service-now.com", "api-user", "secret"), http=http
        )
        incident = client.add_work_notes("inc0012345", "# Evidence\nhealthy")
        self.assertEqual(incident.number, "INC0012345")
        self.assertEqual(http.request_json.call_count, 2)
        patch_call = http.request_json.call_args_list[1]
        self.assertEqual(patch_call.args[0], "PATCH")
        self.assertTrue(patch_call.args[1].endswith("/api/now/table/incident/abc123"))
        self.assertEqual(patch_call.kwargs["json_body"]["work_notes"], "# Evidence\nhealthy")

    def test_missing_incident_is_clear_error(self):
        http = mock.Mock()
        http.request_json.return_value = {"result": []}
        client = ServiceNowClient(
            ServiceNowSettings("https://dev.service-now.com", "api-user", "secret"), http=http
        )
        with self.assertRaisesRegex(ServiceNowError, "was not found"):
            client.get_incident("INC0099999")

    def test_incident_number_format_is_validated_before_api_call(self):
        http = mock.Mock()
        client = ServiceNowClient(
            ServiceNowSettings("https://dev.service-now.com", "api-user", "secret"), http=http
        )
        with self.assertRaisesRegex(ServiceNowError, "INC followed by digits"):
            client.get_incident("INC001^ORstate=1")
        http.request_json.assert_not_called()

    def test_http_failure_is_wrapped_as_servicenow_error(self):
        from incidentpack.integrations.http import ApiError

        http = mock.Mock()
        http.request_json.side_effect = ApiError("connection failed")
        client = ServiceNowClient(
            ServiceNowSettings("https://dev.service-now.com", "api-user", "secret"), http=http
        )
        with self.assertRaisesRegex(ServiceNowError, "ServiceNow lookup failed"):
            client.get_incident("INC0012345")


if __name__ == "__main__":
    unittest.main()
