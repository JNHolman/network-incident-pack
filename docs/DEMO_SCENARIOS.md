# Deterministic Demo Scenarios

Public-safe scenarios demonstrate incident reasoning without requiring a live outage. All scenarios start from the same fixed mock host profile, modify both raw and normalized evidence consistently, and then recompute health and collection summaries.

## Baseline

```bash
incident-pack --target 10.20.30.40 --dns-name app.example.com --ports 443 80 22 \
  --mock --mock-scenario baseline --non-interactive
```

Common web ports connect while another requested service may refuse. This demonstrates mixed service health with proven target reachability.

## Healthy

```bash
incident-pack --target 10.20.30.40 --dns-name app.example.com --ports 443 22 \
  --mock --mock-scenario healthy --non-interactive
```

Every requested TCP service connects, ping succeeds, traceroute reaches the target, and local host evidence is healthy.

## DNS failure

```bash
incident-pack --target 10.20.30.40 --dns-name app.example.com --ports 443 \
  --mock --mock-scenario dns-failure --non-interactive
```

The IP remains reachable and TCP succeeds, but DNS resolution fails. This demonstrates why name resolution and IP reachability should be reported separately.

## Service refused

```bash
incident-pack --target 10.20.30.40 --ports 443 22 \
  --mock --mock-scenario service-refused --non-interactive
```

Every requested port returns a connection refusal. The tool marks service health as failed/degraded while keeping reachability healthy because the returned RST proves an L4 responder is reachable.

## Unreachable

```bash
incident-pack --target 10.20.30.40 --ports 443 22 \
  --mock --mock-scenario unreachable --non-interactive
```

Ping shows 100% loss, traceroute does not reach the destination, and TCP attempts time out. Independent failures combine into a deterministic failed reachability result.

## Collector timeout

```bash
incident-pack --target 10.20.30.40 --ports 443 \
  --mock --mock-scenario collector-timeout --non-interactive
```

The target remains healthy, but one local socket collector times out. The network health remains separate from the collection-completeness summary.

## Why scenarios are code, not static JSON fixtures

The scenario engine modifies the same evidence structure used by normal mock execution, preserves raw evidence consistent with the normalized fields, recalculates health, and recalculates collection quality. This makes the scenarios useful for regression tests as well as demos.
