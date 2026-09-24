# Lab Validation

The repo includes a small loopback lab so the live path can show both success and failure without touching a production network.

## Run the full live demo

From the repository root:

```bash
python3 -m lab.live_demo --out-dir ./lab-output
```

The script starts temporary local endpoints and runs three real collections:

| Case | What actually happens | Expected result |
| --- | --- | --- |
| `healthy` | two TCP ports are listening and `localhost` resolves | `HEALTHY`, reachability `HEALTHY` |
| `service-refused` | one port is listening and one localhost port is deliberately unused | `DEGRADED`, reachability `HEALTHY` |
| `dns-failure` | the IP/TCP path works but a `.invalid` DNS name is queried | `DEGRADED`, reachability `HEALTHY` |

Each case writes its own JSON and Markdown report under `lab-output/`.

This is intentionally different from the mock scenarios: the TCP handshakes, refusal, DNS lookup, local host commands, parsing, health calculation, schema validation, and file writes all use the normal live collection path.

## Run the sandbox manually

```bash
python3 lab/local_sandbox.py
```

Default endpoints:

- HTTP listener: `127.0.0.1:18080`
- TCP banner listener: `127.0.0.1:18022`
- deliberately refused TCP port: `127.0.0.1:18081`

Healthy run:

```bash
incident-pack \
  --target 127.0.0.1 \
  --dns-name localhost \
  --ports 18080 18022 \
  --non-interactive \
  --out-dir ./lab-output/healthy
```

Service-refused run:

```bash
incident-pack \
  --target 127.0.0.1 \
  --dns-name localhost \
  --ports 18080 18081 \
  --non-interactive \
  --out-dir ./lab-output/service-refused
```

DNS-failure run:

```bash
incident-pack \
  --target 127.0.0.1 \
  --dns-name incident-pack-demo.invalid \
  --ports 18080 \
  --non-interactive \
  --out-dir ./lab-output/dns-failure
```

## What stays mocked

A deterministic mock is still the better tool for conditions that are awkward or unsafe to manufacture locally, such as a completely unreachable target or a host-command collector timeout. See [Demo Scenarios](DEMO_SCENARIOS.md).

For a real cloud-hosted validation, use the disposable VM workflow in [Azure Lab Validation](AZURE_LAB.md). Developer/test NetBox or ServiceNow environments can be validated separately; the repository does not need a full emulated enterprise network.
