import unittest

from incidentpack.parsers.ping import parse_ping_command_result, parse_ping_output


class PingParserTests(unittest.TestCase):
    def test_linux_success(self):
        output = """PING 1.1.1.1 (1.1.1.1) 56(84) bytes of data.
64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=22.1 ms
64 bytes from 1.1.1.1: icmp_seq=2 ttl=57 time=23.8 ms

--- 1.1.1.1 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3004ms
rtt min/avg/max/mdev = 22.100/23.250/24.400/0.900 ms
"""
        result = parse_ping_output(output)
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["reachable"])
        self.assertEqual(result["packets_sent"], 4)
        self.assertEqual(result["packets_received"], 4)
        self.assertEqual(result["packet_loss_percent"], 0.0)
        self.assertEqual(result["avg_latency_ms"], 23.25)
        self.assertEqual(result["jitter_ms"], 0.9)

    def test_linux_partial_loss_is_degraded(self):
        output = """4 packets transmitted, 3 received, 25% packet loss, time 3003ms
rtt min/avg/max/mdev = 20.000/22.000/25.000/2.000 ms
"""
        result = parse_ping_output(output)
        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["reachable"])
        self.assertEqual(result["packet_loss_percent"], 25.0)

    def test_linux_total_loss_is_failed_without_rtt(self):
        result = parse_ping_output(
            "4 packets transmitted, 0 received, 100% packet loss, time 3067ms"
        )
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["reachable"])
        self.assertIsNone(result["avg_latency_ms"])

    def test_macos_success_parses_stddev(self):
        output = """--- example.com ping statistics ---
4 packets transmitted, 4 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 15.104/16.225/18.455/1.302 ms
"""
        result = parse_ping_output(output)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["avg_latency_ms"], 16.225)
        self.assertEqual(result["jitter_ms"], 1.302)

    def test_windows_success(self):
        output = """Ping statistics for 1.1.1.1:
    Packets: Sent = 4, Received = 4, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 18ms, Maximum = 22ms, Average = 20ms
"""
        result = parse_ping_output(output)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["avg_latency_ms"], 20.0)
        self.assertIsNone(result["jitter_ms"])

    def test_windows_total_loss(self):
        output = """Ping statistics for 10.10.10.10:
    Packets: Sent = 4, Received = 0, Lost = 4 (100% loss),
"""
        result = parse_ping_output(output)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["reachable"])

    def test_unparseable_output_is_unknown(self):
        result = parse_ping_output(
            "ping utility failed unexpectedly", execution_error_type="os_error"
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["reachable"])
        self.assertEqual(result["parse_error"], "packet statistics not found")
        self.assertEqual(result["execution_error_type"], "os_error")

    def test_command_result_adapter_preserves_execution_error(self):
        result = parse_ping_command_result(
            {
                "stdout": "4 packets transmitted, 0 received, 100% packet loss, time 3000ms",
                "stderr": "",
                "error_type": "nonzero_exit",
            }
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["execution_error_type"], "nonzero_exit")


if __name__ == "__main__":
    unittest.main()
