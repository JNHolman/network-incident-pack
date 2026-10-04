# Incident Evidence Pack

> Representative deterministic mock report from the baseline scenario. It demonstrates the human-readable handoff format; live cloud evidence is documented separately in [Azure Live Validation Evidence](azure_validation.md).

## Incident Summary

Host reachability is **HEALTHY**. DNS, ICMP, traceroute, and two requested TCP services succeeded. TCP/22 returned a connection refusal, so the overall incident state is **DEGRADED**: the host is reachable, but the requested SSH service is unavailable or not listening.

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

- DNS: `app.example.com` resolved to `93.184.216.34`
- Ping: **HEALTHY** — 4/4 replies, 0% loss, 23.25 ms average
- Traceroute: **COMPLETE** — target reached in 4 hops; one intermediate hop did not reply
- Interfaces: **HEALTHY** — 1 usable interface up
- Routes: **HEALTHY** — default route present
- Neighbors: **HEALTHY** — 1 entry, 0 unresolved
- TCP/443: **CONNECTED**
- TCP/80: **CONNECTED**
- TCP/22: **CONNECTION REFUSED**

## Selected Raw Evidence

The full report retains the original command output. These excerpts show the evidence behind the summarized decision without reproducing every collected section.

### Routing table

```text
default via 192.168.1.1 dev eth0 proto dhcp metric 100
192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.25 metric 100
```

### Ping

```text
PING 10.20.30.40 (10.20.30.40) 56(84) bytes of data.
64 bytes from 10.20.30.40: icmp_seq=1 ttl=57 time=22.1 ms

--- 10.20.30.40 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3004ms
rtt min/avg/max/mdev = 22.100/23.250/24.400/0.900 ms
```

### Traceroute

```text
traceroute to 10.20.30.40 (10.20.30.40), 30 hops max, 60 byte packets
 1  192.168.1.1  1.100 ms  1.000 ms  0.900 ms
 2  * * *
 3  10.20.0.1  8.100 ms  8.000 ms  7.900 ms
 4  10.20.30.40  22.400 ms  22.200 ms  22.300 ms
```

## Handoff

The evidence supports a reachable target with a service-specific issue on TCP/22. Investigation should continue at the SSH service or host policy layer rather than treating the target as generally unreachable.
