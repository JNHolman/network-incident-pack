# Network Incident Pack

[![CI](https://github.com/JNHolman/network-incident-pack/actions/workflows/ci.yml/badge.svg)](https://github.com/JNHolman/network-incident-pack/actions/workflows/ci.yml)
[![CodeQL](https://github.com/JNHolman/network-incident-pack/actions/workflows/codeql.yml/badge.svg)](https://github.com/JNHolman/network-incident-pack/actions/workflows/codeql.yml)

When a service is having problems, a network engineer usually starts by proving the basics: does the name resolve, is the host reachable, where does the path stop, is the requested service answering, and does the local machine have the interfaces and routes it needs?

During an incident, engineers can lose valuable time repeating those checks, interpreting partial signals differently, and manually turning troubleshooting notes into something another engineer or support team can use. That creates duplicated work and slower handoffs when the team needs a clear picture quickly.

**Network Incident Pack automates and standardizes that first pass.** It collects host-side network evidence, keeps the raw command output, turns supported results into structured data, applies explicit health rules, and produces consistent JSON and ticket-ready Markdown reports.

The goal is not to replace an engineer. It is to reduce repetitive first-pass work, make the evidence easier to interpret, and give the next person a consistent incident handoff.

## Live demo

The repository includes a [live local sandbox](lab/live_demo.py) that creates real socket and DNS conditions and sends them through the normal Incident Pack workflow.

![Network Incident Pack live demo](assets/network-incident-pack-demo.gif)

The focused `service-refused` scenario shows one of the core design decisions in the project: a failed service check does not automatically mean the host is unreachable. One TCP service connects, another returns a refusal, overall service health degrades, but reachability remains healthy because the returned TCP reset proves the remote side answered.

The sandbox also covers healthy operation and DNS failure while using the same collectors, parsers, health logic, report validation, and output writers as a normal run.

A [sample incident report](examples/sample_output.md) shows the resulting human-readable handoff.

## Why the health model matters

A single failed check rarely tells the whole story.

- **Ping failure does not automatically mean the host is unreachable.** TCP may still prove a working path.
- **TCP connection refused is a service failure, not proof of a dead host.** The remote side responded, so reachability has still been demonstrated.
- **An intermediate traceroute timeout does not automatically mean the path failed.** The destination may still be reachable.
- **Collector failure is separate from network failure.** Missing local evidence affects collection quality, not necessarily the target itself.

Network Incident Pack therefore evaluates **reachability**, **service health**, and **collection quality** separately instead of reducing an incident to a single pass/fail result.

## Key design decisions

### Keep raw evidence and structured results

Structured data makes automated health decisions and reporting possible, but engineers still need the original command output during escalation or deeper troubleshooting. The project keeps both so automation improves the evidence without hiding it.

### Use bounded concurrency

Many network checks spend most of their time waiting on I/O, so independent checks can run concurrently. Worker counts, retry counts, port counts, and timeouts are capped because faster collection should not come at the cost of uncontrolled resource use.

### Retry only when it makes sense

Timeouts, resets, and transient HTTP failures may be temporary and can benefit from another attempt. A TCP connection refusal is different: the remote system has already answered, so immediately retrying it usually adds delay without adding useful evidence.

### Keep integrations optional

The core troubleshooting workflow does not depend on NetBox, Azure, or ServiceNow being available. Those systems add context when useful, but an integration failure should not prevent the underlying network evidence from being collected.

### Add cloud context without replacing network evidence

Cloud incidents can involve both packet-path behavior and cloud control-plane configuration. Azure enrichment adds VM, NIC, IP, VNet, subnet, NSG, provisioning, and power-state context while the actual network tests remain the evidence of what the client observed.

## Azure validation

The Azure integration was validated against a real disposable Ubuntu VM from an external macOS client.

The lab intentionally created different conditions:

| Test | Result |
| --- | --- |
| TCP/8080 | service reachable |
| TCP/8081 | no listening service |
| TCP/8443 | blocked by Azure NSG |
| ICMP | failed |
| traceroute | destination not reached |

In the main Incident Pack run, TCP/8080 connected while TCP/8443 timed out. Even though ping failed and traceroute did not reach the VM, the tool correctly kept **reachability HEALTHY** because successful Layer 4 communication provided stronger positive evidence.

The same run used Azure Resource Manager to add read-only VM and network context to the report. See [Azure Live Validation Evidence](examples/azure_validation.md) for the sanitized results.

## How an incident run works

| Step | What the tool does | Why it matters |
| --- | --- | --- |
| 1 | resolves the target and effective configuration | makes the run deterministic before collection starts |
| 2 | checks local interfaces, routes, neighbors, sockets, DNS, ping, traceroute, and TCP | collects the first-pass evidence an engineer would normally gather manually |
| 3 | parses supported command output while retaining the raw evidence | gives automation structured data without removing the original evidence |
| 4 | evaluates reachability, service health, and collection quality | avoids allowing one protocol to decide every outcome |
| 5 | adds requested external context | enriches the incident without making integrations mandatory |
| 6 | sanitizes, validates, and writes JSON and Markdown reports | produces a consistent handoff with a defined report contract |

## What the project includes

- Linux, macOS, and Windows host-side evidence collection and parsing
- DNS, ping, traceroute/tracert, TCP, interface, route, neighbor, and socket evidence
- raw evidence retained alongside structured results
- bounded concurrent I/O collection with deterministic result ordering
- selective TCP and HTTP retries
- YAML/JSON inventory with explicit configuration precedence
- deterministic health evaluation and collection-completeness summaries
- versioned JSON and Markdown report validation
- optional read-only NetBox device lookup
- optional read-only Azure Resource Manager enrichment
- explicit ServiceNow work-note updates only when requested
- environment-based credential handling and report redaction
- CI, CodeQL, dependency review, Ruff, release verification, and automated tests

## Validation

The project is validated through real localhost TCP/DNS execution, live macOS execution, Ubuntu CI execution, cross-platform parser fixtures, deterministic failure scenarios, CLI/application tests, security/input-validation tests, integration contract tests, and the live Azure VM run described above.

Windows behavior is fixture-tested rather than represented as live Windows lab validation. NetBox and ServiceNow are contract-tested rather than presented as production-environment validation.

See [Validation](docs/VALIDATION.md) for the full evidence boundaries.

## Engineering

The CLI is a thin entry point over a reusable application service. Collection, parsing, health evaluation, integrations, and reporting are separated so the workflow is easier to test, extend, and reason about.

See [Engineering and Architecture](docs/ENGINEERING.md) for the application flow, module boundaries, and deeper design rationale.

## Run the demo locally

Requires Python 3.10+.

```bash
python -m pip install -e .
python -m lab.live_demo --scenario service-refused --out-dir ./lab-output
```

Run the full local validation matrix by omitting `--scenario`.

## Documentation

- [Engineering and Architecture](docs/ENGINEERING.md)
- [Validation](docs/VALIDATION.md)
- [Security](SECURITY.md)

## License

See [LICENSE](LICENSE).
