# Validation

This document separates what Network Incident Pack has actually been proven to do from deterministic test coverage and planned cloud validation.

The purpose of the validation is not to recreate a production enterprise network. It is to prove that the incident workflow behaves correctly when the underlying network evidence changes.

## Live local validation

The local sandbox creates real endpoints on the loopback interface and sends them through the normal Incident Pack collection path.

Three scenarios are used because they demonstrate the most important health distinctions in a controlled environment:

| Scenario | Real condition | Expected decision | Why it matters |
| --- | --- | --- | --- |
| `healthy` | DNS resolves and both requested TCP services accept connections | overall `HEALTHY`, reachability `HEALTHY` | establishes the normal success path |
| `service-refused` | one requested localhost port has no listener | overall `DEGRADED`, reachability `HEALTHY` | proves service failure and host reachability are not the same thing |
| `dns-failure` | a `.invalid` name fails while the IP/TCP path still works | overall `DEGRADED`, reachability `HEALTHY` | proves name resolution is evaluated separately from IP reachability |

The live path uses:

- real localhost HTTP and TCP listeners
- a real TCP connection refusal
- real DNS resolution/failure
- the operating system's host-side network commands
- the normal cross-platform parsers
- the normal health engine
- report sanitization and schema validation
- the normal JSON and Markdown writers

No prebuilt result JSON is loaded for these cases.

## What the visible demo shows

The terminal demo is meant to make the incident workflow understandable without requiring a reviewer to inspect every module.

For each live scenario it presents the actual collected evidence in the same order an engineer would reason through it:

1. DNS resolution
2. local interfaces
3. routing table
4. neighbor cache
5. ping
6. traceroute/tracert
7. requested TCP services
8. collection quality
9. final health decision
10. generated report paths

The wording deliberately explains why the evidence matters. For example, a connection refusal is shown as a failed service check while the health decision keeps reachability healthy because the returned RST proves a Layer 4 responder answered.

When run in an interactive terminal, status wording changes in place so the viewer can see the workflow progress. CI output stays line-oriented and readable.

## Deterministic edge-case coverage

Some failure states are better tested deterministically than manufactured on a live machine.

The scenario engine covers:

### Baseline

A mixed service state used as the standard mock profile.

### Healthy

Requested TCP services connect, ping succeeds, traceroute reaches the target, and local host evidence is healthy.

### DNS failure

IP reachability and TCP succeed while DNS resolution fails.

### Service refused

Requested TCP services return connection refusals. Service health fails/degrades while reachability remains healthy because the remote side answered at Layer 4.

### Unreachable

Ping reports 100% loss, traceroute does not reach the destination, and TCP attempts time out. Multiple independent failures combine into failed reachability.

### Collector timeout

The target remains healthy while a local collector times out. This verifies that collection completeness does not get confused with network health.

These scenarios modify the same evidence structure used by normal mock execution and recalculate health and collection quality. They are regression tests, not screenshots standing in for live results.

## Cross-platform coverage

The host-side collection and parsers support Linux, macOS, and Windows command formats.

Current proof includes:

- automated parser fixtures for all three supported operating systems
- live local execution on macOS
- CI execution on Ubuntu
- Windows behavior validated through fixtures/parser tests rather than a claimed live Windows lab

That distinction is intentional: the repository does not claim live validation that has not been performed.

## Integration validation

### NetBox

The read-only integration is covered by HTTP contract tests and target-resolution tests. The repository does not claim validation against a production organization's NetBox environment.

### ServiceNow

The work-note integration is covered by mocked HTTP contract tests and explicit-write behavior tests. The repository does not claim validation against a production organization's ServiceNow environment.

### Azure Resource Manager

The read-only Azure adapter is covered by HTTP contract tests and was also validated against a live disposable Ubuntu 24.04 VM in Azure from an external macOS client.

The live lab used three deliberate network conditions:

| Port | Azure/guest condition | External observation | Additional proof |
| --- | --- | --- | --- |
| `8080` | NSG allowed; Python HTTP service listening | TCP connected successfully | HTTP response returned from the Azure VM |
| `8081` | NSG allowed; no service listening | external client observed a timeout | guest `tcpdump` confirmed the SYN reached Ubuntu and Ubuntu emitted a TCP RST |
| `8443` | no inbound allow rule; default NSG deny applied | external client observed a timeout | guest `tcpdump` captured 0 packets for the test |

The main Incident Pack validation run targeted ports `8080` and `8443`. ICMP returned 100% loss and traceroute did not reach the destination, but TCP/8080 connected. The health engine therefore reported:

```text
Overall:      DEGRADED
Reachability: HEALTHY
TCP checks:   1/2 connected
```

That result is important because it proves that failed ping and incomplete traceroute do not automatically override stronger positive Layer 4 evidence.

The same run also performed real Azure ARM enrichment and returned report-safe control-plane context for:

- VM name, resource group, region, size, provisioning state, and power state
- NIC name
- private and public IP addresses
- virtual network
- subnet
- network security group

The report intentionally omits subscription IDs and access tokens. A short sanitized record of the live run is kept in [`examples/azure_validation.md`](../examples/azure_validation.md).

This validation demonstrates that Azure metadata adds control-plane context without replacing packet-path evidence.

## Automated quality and regression coverage

The repository also uses automated checks for behavior that is better proven by tests than by screenshots:

- unit and CLI/application tests
- inventory/configuration precedence
- health semantics
- TCP retry behavior
- concurrency/result ordering
- input and endpoint validation
- secret rejection/redaction
- report-contract validation
- release-archive verification
- Ruff
- CodeQL
- dependency review
- CI across supported Python versions

## Validation boundaries

Network Incident Pack is currently represented as a host-side network/infrastructure incident automation project.

It is **not** represented as proof of:

- production multi-vendor device collection
- production NetBox or ServiceNow integration
- infrastructure provisioning
- full network-management functionality

Those boundaries keep the portfolio claims aligned with what the repository can actually demonstrate.
