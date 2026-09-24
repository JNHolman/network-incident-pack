import unittest
from unittest import mock

import requests

from incidentpack.integrations.http import ApiError, JsonApiClient, RetryPolicy


class _Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, BaseException):
            raise self._payload
        return self._payload


class JsonApiClientTests(unittest.TestCase):
    def setUp(self):
        self.session = mock.Mock()
        self.client = JsonApiClient(
            timeout=2.0,
            retry_policy=RetryPolicy(max_attempts=3, initial_delay=0),
            session=self.session,
        )

    def test_timeout_retries_then_returns_json(self):
        self.session.request.side_effect = [
            requests.Timeout("slow"),
            _Response(200, {"ok": True}),
        ]
        result = self.client.request_json("GET", "https://example.test/api")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(self.session.request.call_count, 2)

    def test_503_retries_then_succeeds(self):
        self.session.request.side_effect = [
            _Response(503, {"error": "busy"}),
            _Response(200, {"ok": True}),
        ]
        result = self.client.request_json("GET", "https://example.test/api")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(self.session.request.call_count, 2)

    def test_400_is_not_retried(self):
        self.session.request.return_value = _Response(400, {"error": "bad"}, "bad request")
        with self.assertRaisesRegex(ApiError, "HTTP 400"):
            self.client.request_json("GET", "https://example.test/api")
        self.assertEqual(self.session.request.call_count, 1)

    def test_error_body_redacts_credential_patterns(self):
        self.session.request.return_value = _Response(
            401,
            {"error": "denied"},
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
        )
        with self.assertRaises(ApiError) as caught:
            self.client.request_json("GET", "https://example.test/api")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_request_uses_original_url_even_if_log_redaction_would_change_it(self):
        self.session.request.return_value = _Response(200, {"ok": True})
        url = "https://example.test/api?access_token=temporary-secret"
        self.client.request_json("GET", url)
        self.assertEqual(self.session.request.call_args.args[1], url)


    def test_redirects_are_not_followed_with_credentials(self):
        self.session.request.return_value = _Response(302, None, "redirect")
        with self.assertRaisesRegex(ApiError, "HTTP 302"):
            self.client.request_json(
                "GET",
                "https://example.test/api",
                headers={"Authorization": "Bearer secret"},
            )
        self.assertFalse(self.session.request.call_args.kwargs["allow_redirects"])

    def test_invalid_json_is_clear_error(self):
        self.session.request.return_value = _Response(200, ValueError("bad json"))
        with self.assertRaisesRegex(ApiError, "not valid JSON"):
            self.client.request_json("GET", "https://example.test/api")


if __name__ == "__main__":
    unittest.main()
