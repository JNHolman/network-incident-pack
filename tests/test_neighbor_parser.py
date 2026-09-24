import unittest

from incidentpack.parsers.neighbors import parse_neighbor_output


class NeighborParserTests(unittest.TestCase):
    def test_linux_neighbor_states(self):
        text = """192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
192.168.1.50 dev eth0 FAILED
"""
        result = parse_neighbor_output(text, os_name="linux")
        self.assertEqual(result["neighbor_count"], 2)
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(result["status"], "degraded")

    def test_macos_arp(self):
        text = """? (192.168.1.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
? (192.168.1.50) at (incomplete) on en0 ifscope [ethernet]
"""
        result = parse_neighbor_output(text, os_name="macos")
        self.assertEqual(result["neighbor_count"], 2)
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(result["neighbors"][0]["interface"], "en0")

    def test_windows_arp(self):
        text = """Interface: 10.0.0.25 --- 0x6
  Internet Address      Physical Address      Type
  10.0.0.1              00-11-22-33-44-55     dynamic
  10.0.0.20             aa-bb-cc-dd-ee-ff     static
"""
        result = parse_neighbor_output(text, os_name="windows")
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["neighbor_count"], 2)
        self.assertEqual(result["neighbors"][0]["mac"], "00:11:22:33:44:55")

    def test_empty_neighbor_cache_is_unknown_not_failed(self):
        result = parse_neighbor_output("", os_name="linux")
        self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
