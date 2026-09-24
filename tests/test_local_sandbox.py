import json
import socket
import unittest
from urllib.request import urlopen

from lab.local_sandbox import start_sandbox


class LocalSandboxTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = start_sandbox(http_port=0, tcp_port=0, refused_port=0)

    def tearDown(self):
        self.sandbox.close()

    def test_http_health_endpoint(self):
        with urlopen(
            f"http://{self.sandbox.host}:{self.sandbox.http_port}/health", timeout=2
        ) as response:
            payload = json.loads(response.read().decode())
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "ok")

    def test_tcp_banner_endpoint(self):
        with socket.create_connection(
            (self.sandbox.host, self.sandbox.tcp_port), timeout=2
        ) as connection:
            banner = connection.recv(128)
        self.assertEqual(banner, b"incident-pack-sandbox\n")

    def test_refused_port_returns_connection_refused(self):
        with self.assertRaises(ConnectionRefusedError):
            socket.create_connection(
                (self.sandbox.host, self.sandbox.refused_port), timeout=2
            )


if __name__ == "__main__":
    unittest.main()
