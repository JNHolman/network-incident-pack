import unittest

from incidentpack.parsers.routes import parse_route_output


LINUX = """default via 192.168.1.1 dev eth0 proto dhcp metric 100
10.20.0.0/16 via 192.168.1.254 dev eth0 metric 50
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.25 metric 100
"""

MACOS = """Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            192.168.1.1        UGScg                 en0
127                127.0.0.1          UCS                   lo0
192.168.1          link#6             UCS                   en0      !

Internet6:
Destination                             Gateway                         Flags         Netif Expire
"""

WINDOWS = """IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      10.0.0.1       10.0.0.25     25
        10.0.0.0    255.255.255.0         On-link       10.0.0.25    281
===========================================================================
Persistent Routes:
  None
"""


class RouteParserTests(unittest.TestCase):
    def test_linux_default_route(self):
        result = parse_route_output(LINUX, os_name="linux")
        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["default_route"])
        self.assertEqual(result["default_gateway"], "192.168.1.1")
        self.assertEqual(result["default_interface"], "eth0")
        self.assertEqual(result["route_count"], 3)

    def test_macos_default_route(self):
        result = parse_route_output(MACOS, os_name="macos")
        self.assertTrue(result["default_route"])
        self.assertEqual(result["default_gateway"], "192.168.1.1")
        self.assertEqual(result["default_interface"], "en0")

    def test_windows_default_route(self):
        result = parse_route_output(WINDOWS, os_name="windows")
        self.assertTrue(result["default_route"])
        self.assertEqual(result["default_gateway"], "10.0.0.1")
        self.assertEqual(result["default_interface"], "10.0.0.25")
        self.assertEqual(result["routes"][0]["metric"], 25)

    def test_route_table_without_default_is_degraded(self):
        result = parse_route_output("10.0.0.0/24 dev eth0 metric 100", os_name="linux")
        self.assertEqual(result["status"], "degraded")
        self.assertFalse(result["default_route"])

    def test_unparseable_route_output_is_unknown(self):
        result = parse_route_output("not routes", os_name="linux")
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["parse_error"])


if __name__ == "__main__":
    unittest.main()
