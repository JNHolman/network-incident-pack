import unittest

from incidentpack.parsers.traceroute import (
    parse_traceroute_command_result,
    parse_traceroute_output,
)


class TracerouteParserTests(unittest.TestCase):
    def test_linux_complete_with_intermediate_timeout(self):
        output = """traceroute to 8.8.8.8 (8.8.8.8), 30 hops max, 60 byte packets
 1  192.168.1.1  1.123 ms  0.945 ms  0.881 ms
 2  * * *
 3  10.0.0.1  10.222 ms  9.111 ms  8.333 ms
 4  8.8.8.8  20.123 ms  19.876 ms  20.001 ms
"""
        result = parse_traceroute_output(output, target="8.8.8.8")
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["target_reached"])
        self.assertEqual(result["target_address"], "8.8.8.8")
        self.assertEqual(result["hop_count"], 4)
        self.assertEqual(result["responding_hops"], 3)
        self.assertEqual(result["timeout_hops"], 1)
        self.assertEqual(result["hops"][0]["latencies_ms"], [1.123, 0.945, 0.881])
        self.assertTrue(result["hops"][1]["timed_out"])

    def test_macos_complete_uses_same_unix_format(self):
        output = """traceroute to example.com (93.184.216.34), 64 hops max, 52 byte packets
 1  192.168.1.1  1.012 ms  0.921 ms  0.855 ms
 2  93.184.216.34  18.100 ms  17.900 ms  18.000 ms
"""
        result = parse_traceroute_output(output, target="example.com")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["target_address"], "93.184.216.34")
        self.assertEqual(result["hop_count"], 2)

    def test_windows_complete(self):
        output = """Tracing route to dns.google [8.8.8.8]
over a maximum of 30 hops:

  1    <1 ms    <1 ms    <1 ms  192.168.1.1
  2     *        *        *     Request timed out.
  3    10 ms    11 ms    10 ms  10.0.0.1
  4    20 ms    19 ms    20 ms  8.8.8.8

Trace complete.
"""
        result = parse_traceroute_output(output, target="dns.google")
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["target_reached"])
        self.assertEqual(result["timeout_hops"], 1)
        self.assertEqual(result["hops"][0]["latencies_ms"], [1.0, 1.0, 1.0])

    def test_partial_path_does_not_claim_destination_reached(self):
        output = """traceroute to 203.0.113.10 (203.0.113.10), 30 hops max, 60 byte packets
 1  192.168.1.1  1.000 ms  1.100 ms  1.200 ms
 2  10.0.0.1  8.000 ms  8.100 ms  8.200 ms
 3  * * *
 4  * * *
"""
        result = parse_traceroute_output(output, target="203.0.113.10")
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["target_reached"])
        self.assertEqual(result["responding_hops"], 2)
        self.assertEqual(result["timeout_hops"], 2)

    def test_all_timeout_hops_are_failed(self):
        output = """traceroute to 203.0.113.10 (203.0.113.10), 30 hops max, 60 byte packets
 1  * * *
 2  * * *
 3  * * *
"""
        result = parse_traceroute_output(output, target="203.0.113.10")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["target_reached"])
        self.assertEqual(result["hop_count"], 3)

    def test_unparseable_output_is_unknown(self):
        result = parse_traceroute_output(
            "traceroute utility failed unexpectedly",
            target="203.0.113.10",
            execution_error_type="os_error",
        )
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["target_reached"])
        self.assertEqual(result["parse_error"], "hop data not found")
        self.assertEqual(result["execution_error_type"], "os_error")

    def test_command_result_adapter_preserves_execution_error(self):
        result = parse_traceroute_command_result(
            {
                "stdout": "traceroute to 8.8.8.8 (8.8.8.8), 30 hops max\n 1  * * *",
                "stderr": "",
                "error_type": "nonzero_exit",
            },
            target="8.8.8.8",
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["execution_error_type"], "nonzero_exit")


if __name__ == "__main__":
    unittest.main()
