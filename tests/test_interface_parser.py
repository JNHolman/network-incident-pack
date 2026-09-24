import unittest

from incidentpack.parsers.interfaces import parse_interface_output

LINUX = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP group default
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.25/24 brd 192.168.1.255 scope global eth0
    inet6 fe80::42:acff:fe11:2/64 scope link
3: eth1: <BROADCAST,MULTICAST> mtu 1500 state DOWN group default
    link/ether 02:42:ac:11:00:03 brd ff:ff:ff:ff:ff:ff
"""

MACOS = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
    inet 127.0.0.1 netmask 0xff000000
    status: active
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
    ether aa:bb:cc:dd:ee:ff
    inet 10.0.0.25 netmask 0xffffff00 broadcast 10.0.0.255
    inet6 fe80::1234%en0 prefixlen 64 secured scopeid 0x6
    status: active
en7: flags=8822<BROADCAST,SMART,SIMPLEX,MULTICAST> mtu 1500
    status: inactive
"""

WINDOWS = """Ethernet adapter Ethernet:

   Connection-specific DNS Suffix  . : example.local
   Physical Address. . . . . . . . . : 00-11-22-33-44-55
   IPv4 Address. . . . . . . . . . . : 10.0.0.25(Preferred)
   Link-local IPv6 Address . . . . . : fe80::abcd:1234%6(Preferred)

Wireless LAN adapter Wi-Fi:

   Media State . . . . . . . . . . . : Media disconnected
   Physical Address. . . . . . . . . : AA-BB-CC-DD-EE-FF
"""


class InterfaceParserTests(unittest.TestCase):
    def test_linux_interfaces(self):
        result = parse_interface_output(LINUX, os_name="linux")
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["interface_count"], 3)
        self.assertEqual(result["up_count"], 2)
        self.assertEqual(result["usable_up_count"], 1)
        eth0 = next(item for item in result["interfaces"] if item["name"] == "eth0")
        self.assertEqual(eth0["ipv4"], ["192.168.1.25"])
        self.assertEqual(eth0["mac"], "02:42:ac:11:00:02")
        self.assertTrue(eth0["is_up"])

    def test_macos_interfaces(self):
        result = parse_interface_output(MACOS, os_name="macos")
        self.assertEqual(result["interface_count"], 3)
        en0 = next(item for item in result["interfaces"] if item["name"] == "en0")
        self.assertEqual(en0["state"], "active")
        self.assertEqual(en0["ipv4"], ["10.0.0.25"])
        self.assertEqual(en0["ipv6"], ["fe80::1234"])

    def test_windows_interfaces(self):
        result = parse_interface_output(WINDOWS, os_name="windows")
        self.assertEqual(result["interface_count"], 2)
        ethernet = result["interfaces"][0]
        wifi = result["interfaces"][1]
        self.assertEqual(ethernet["ipv4"], ["10.0.0.25"])
        self.assertEqual(ethernet["mac"], "00:11:22:33:44:55")
        self.assertTrue(ethernet["is_up"])
        self.assertFalse(wifi["is_up"])

    def test_no_interfaces_is_unknown(self):
        result = parse_interface_output("garbage", os_name="linux")
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["parse_error"])

    def test_parsed_interfaces_all_down_is_failed(self):
        text = "2: eth0: <BROADCAST,MULTICAST> mtu 1500 state DOWN group default"
        result = parse_interface_output(text, os_name="linux")
        self.assertEqual(result["status"], "failed")

    def test_loopback_alone_does_not_make_local_interfaces_healthy(self):
        text = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN group default
    inet 127.0.0.1/8 scope host lo
"""
        result = parse_interface_output(text, os_name="linux")
        self.assertEqual(result["up_count"], 1)
        self.assertEqual(result["usable_up_count"], 0)
        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
