import socket
import threading
import time
import unittest
from unittest import mock

from incidentpack.collectors.host import run_host_commands
from incidentpack.collectors.tcp import run_tcp_checks, tcp_check


class _FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class TcpCollectorTests(unittest.TestCase):
    def test_timeout_retries_then_succeeds(self):
        connector = mock.Mock(side_effect=[socket.timeout("slow"), _FakeConnection()])
        result = tcp_check(
            "10.0.0.1",
            443,
            timeout=1.0,
            max_attempts=3,
            retry_delay=0,
            connector=connector,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(connector.call_count, 2)

    def test_connection_refused_is_not_retried(self):
        connector = mock.Mock(side_effect=ConnectionRefusedError("refused"))
        result = tcp_check(
            "10.0.0.1",
            22,
            max_attempts=4,
            retry_delay=0,
            connector=connector,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "connection_refused")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(connector.call_count, 1)

    def test_concurrent_tcp_results_preserve_port_order(self):
        def fake_check(host, port, **kwargs):
            time.sleep({443: 0.03, 22: 0.01, 80: 0.02}[port])
            return {"host": host, "port": port, "ok": True}

        with mock.patch("incidentpack.collectors.tcp.tcp_check", side_effect=fake_check):
            results = run_tcp_checks("10.0.0.1", [443, 22, 80], max_workers=3)
        self.assertEqual([item["port"] for item in results], [443, 22, 80])


class HostConcurrencyTests(unittest.TestCase):
    def test_commands_overlap_and_preserve_configured_order(self):
        lock = threading.Lock()
        active = 0
        max_active = 0

        def fake_run(command, timeout):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep({"first": 0.03, "second": 0.01, "third": 0.02}[command[0]])
            with lock:
                active -= 1
            return {"cmd": command[0]}

        commands = [["first"], ["second"], ["third"]]
        with mock.patch("incidentpack.collectors.host.run_command", side_effect=fake_run):
            results = run_host_commands(commands, timeout=5, max_workers=3)

        self.assertGreaterEqual(max_active, 2)
        self.assertEqual([item["cmd"] for item in results], ["first", "second", "third"])


if __name__ == "__main__":
    unittest.main()
