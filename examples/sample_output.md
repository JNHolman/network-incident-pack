# Incident Evidence Pack

## Metadata
- Report Schema: `2`
- Timestamp (UTC): `2026-01-29T06:07:27+00:00`
- Host: `demo-host`
- OS: `linux`
- Target: `10.20.30.40`
- DNS Name: `app.example.com`
- Ports: `443, 80, 22`
- Mode: `mock`
- Mock Scenario: `baseline`

## Health Summary
- Overall: **DEGRADED**
- Reachability: **HEALTHY**
- Finding: 2/3 requested TCP checks connected

## Collection Summary
- Host commands: **6/6 succeeded** (0 timed out)
- TCP checks: **2/3 connected**
- Parser errors: **0**

## Context
- **Impact**: 
- **Symptoms**: 
- **Scope**: 
- **Recent Changes**: 
- **Actions Taken**: 

## Key Results
- DNS: ✅ `app.example.com` -> 93.184.216.34
- Ping: **HEALTHY** (received 4/4, loss 0%, avg 23.25 ms)
- Traceroute: **COMPLETE** (4 hops observed, 1 timeout hop, target reached)
- Interfaces: **HEALTHY** (1 usable up, 2 total)
- Routes: **HEALTHY** (2 routes, default route present)
- Neighbors: **HEALTHY** (1 entries, 0 unresolved)
- TCP 10.20.30.40:443: ✅ connect ok after 1 attempt
- TCP 10.20.30.40:80: ✅ connect ok after 1 attempt
- TCP 10.20.30.40:22: ❌ ConnectionRefusedError: Connection refused after 1 attempt

## Raw Command Outputs
### `ip addr`

```text
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 state UNKNOWN
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.25/24 brd 192.168.1.255 scope global eth0
```

### `ip route`

```text
default via 192.168.1.1 dev eth0 proto dhcp metric 100
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.25 metric 100
```

### `ip neigh`

```text
192.168.1.1 dev eth0 lladdr 00:11:22:33:44:55 REACHABLE
```

### `ping -c 4 10.20.30.40`

```text
PING 10.20.30.40 (10.20.30.40) 56(84) bytes of data.
64 bytes from 10.20.30.40: icmp_seq=1 ttl=57 time=22.1 ms

--- 10.20.30.40 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3004ms
rtt min/avg/max/mdev = 22.100/23.250/24.400/0.900 ms
```

### `traceroute -n 10.20.30.40`

```text
traceroute to 10.20.30.40 (10.20.30.40), 30 hops max, 60 byte packets
 1  192.168.1.1  1.100 ms  1.000 ms  0.900 ms
 2  * * *
 3  10.20.0.1  8.100 ms  8.000 ms  7.900 ms
 4  10.20.30.40  22.400 ms  22.200 ms  22.300 ms
```

### `ss -tulpn`

```text
Netid State  Local Address:Port  Peer Address:Port
```
