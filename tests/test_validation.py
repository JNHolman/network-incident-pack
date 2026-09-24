import unittest

from incidentpack.validation import (
    MAX_COMMAND_TIMEOUT_SECONDS,
    MAX_PORTS_PER_RUN,
    MAX_TCP_ATTEMPTS,
    MAX_TCP_TIMEOUT_SECONDS,
    MAX_WORKERS,
    validate_host,
    validate_https_endpoint,
    validate_ports,
    validate_tcp_attempts,
    validate_tcp_timeout,
    validate_timeout,
    validate_workers,
)


class HostValidationTests(unittest.TestCase):
    def test_accepts_ipv4_ipv6_and_hostname(self):
        self.assertEqual(validate_host("10.20.30.40"), "10.20.30.40")
        self.assertEqual(validate_host("2001:db8::10"), "2001:db8::10")
        self.assertEqual(validate_host("fe80::1%eth0"), "fe80::1%eth0")
        self.assertEqual(validate_host("app01.example.com"), "app01.example.com")

    def test_rejects_option_like_target(self):
        with self.assertRaisesRegex(ValueError, "cannot begin"):
            validate_host("-i")

    def test_rejects_whitespace_and_url(self):
        with self.assertRaises(ValueError):
            validate_host("10.0.0.1 --help")
        with self.assertRaises(ValueError):
            validate_host("https://example.com")

    def test_rejects_bad_hostname_labels(self):
        with self.assertRaises(ValueError):
            validate_host("bad_name.example.com")
        with self.assertRaises(ValueError):
            validate_host("-bad.example.com")

    def test_rejects_unicode_and_control_character_confusion(self):
        bad_values = [
            "examp\u200ble.com",
            "example.com\x00--help",
            "example.com\n--help",
            "example.com\t--help",
        ]
        for value in bad_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    validate_host(value)


class IntegrationEndpointValidationTests(unittest.TestCase):
    def test_accepts_https_endpoint(self):
        self.assertEqual(
            validate_https_endpoint("https://netbox.example.com/", "NETBOX_URL"),
            "https://netbox.example.com",
        )

    def test_rejects_plain_http(self):
        with self.assertRaisesRegex(ValueError, "must use https"):
            validate_https_endpoint("http://example.com", "API_URL")

    def test_rejects_embedded_credentials(self):
        with self.assertRaisesRegex(ValueError, "embedded credentials"):
            validate_https_endpoint("https://user:pass@example.com", "API_URL")

    def test_rejects_query_or_fragment(self):
        with self.assertRaises(ValueError):
            validate_https_endpoint("https://example.com?token=abc", "API_URL")
        with self.assertRaises(ValueError):
            validate_https_endpoint("https://example.com/#frag", "API_URL")

    def test_rejects_parser_confusion_inputs(self):
        bad_values = [
            "https://a.com\t@evil.com",
            "https://a.com\\@evil.com",
            "https://user%3Apass@example.com",
            "https://example.com:99999",
            "https://examp\u200ble.com",
        ]
        for value in bad_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    validate_https_endpoint(value, "API_URL")


class RuntimeGuardrailTests(unittest.TestCase):
    def test_allows_maximum_bounded_values(self):
        validate_ports(list(range(1, MAX_PORTS_PER_RUN + 1)))
        validate_timeout(MAX_COMMAND_TIMEOUT_SECONDS)
        validate_workers(MAX_WORKERS)
        validate_tcp_attempts(MAX_TCP_ATTEMPTS)
        validate_tcp_timeout(MAX_TCP_TIMEOUT_SECONDS)

    def test_rejects_too_many_ports(self):
        with self.assertRaisesRegex(ValueError, "Too many ports"):
            validate_ports(list(range(1, MAX_PORTS_PER_RUN + 2)))

    def test_rejects_excessive_timeout(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            validate_timeout(MAX_COMMAND_TIMEOUT_SECONDS + 1)

    def test_rejects_excessive_workers(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            validate_workers(MAX_WORKERS + 1)

    def test_rejects_excessive_tcp_attempts(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            validate_tcp_attempts(MAX_TCP_ATTEMPTS + 1)

    def test_rejects_excessive_tcp_timeout(self):
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            validate_tcp_timeout(MAX_TCP_TIMEOUT_SECONDS + 0.1)


if __name__ == "__main__":
    unittest.main()
