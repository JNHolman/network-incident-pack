# Azure Live Validation Evidence

This is a sanitized record of a real Network Incident Pack run against a disposable Azure VM. Subscription identifiers, access tokens, and the public IP address are intentionally omitted.

## Environment

```text
Cloud:              Azure
VM:                 ip-lab-vm
OS:                 Ubuntu 24.04 LTS
Region:             eastus
VM size:            Standard_D2nlds_v6
Provisioning state: Succeeded
Power state:        running

NIC:                ip-lab-vm269
Private IP:         172.16.0.4
Public IP:          [redacted]
VNet:               vnet-eastus-1
Subnet:             snet-eastus-1
NSG:                ip-lab-vm-nsg
```

## Network conditions

The lab intentionally created different failure points rather than treating every failed TCP check as the same problem.

```text
TCP/8080
NSG:       allowed
Guest:     Python HTTP service listening
Observed:  connected

TCP/8081
NSG:       allowed
Guest:     no service listening
Observed:  external client timed out
Packet:    SYN reached Ubuntu; Ubuntu emitted TCP RST

TCP/8443
NSG:       default inbound deny
Guest:     no service listening
Observed:  external client timed out
Packet:    0 packets reached the guest during the test
```

The 8081 result is deliberately recorded exactly as observed. The Incident Pack client reported a timeout even though guest packet capture showed that Ubuntu generated a reset. The report is not rewritten to claim a connection refusal that the external socket did not observe.

## Incident Pack result

The primary ARM-enriched run tested the reachable service on 8080 and the NSG-blocked port on 8443.

```text
Ping:         FAILED (100% loss)
Traceroute:   target not reached
TCP/8080:     connected
TCP/8443:     timeout

Overall:      DEGRADED
Reachability: HEALTHY
TCP health:   DEGRADED
```

The key result is the separation of reachability from individual protocol/service failures. TCP/8080 provided positive Layer 4 evidence, so failed ICMP, incomplete traceroute, and the 8443 timeout did not incorrectly mark the VM unreachable.

## Azure ARM enrichment

The same Incident Pack execution queried Azure Resource Manager and added the following report-safe cloud context:

```json
{
  "provider": "azure",
  "resource_type": "virtual_machine",
  "name": "ip-lab-vm",
  "resource_group": "incident-pack-lab",
  "location": "eastus",
  "vm_size": "Standard_D2nlds_v6",
  "provisioning_state": "Succeeded",
  "power_state": "running",
  "network": {
    "nics": [
      {
        "name": "ip-lab-vm269",
        "private_ips": ["172.16.0.4"],
        "public_ips": ["[redacted]"],
        "virtual_networks": ["vnet-eastus-1"],
        "subnets": ["snet-eastus-1"],
        "network_security_group": "ip-lab-vm-nsg"
      }
    ]
  }
}
```

Integration result:

```json
{
  "status": "enriched",
  "resource": "ip-lab-vm"
}
```

## What this proves

- the normal live collection path works against an external cloud-hosted target
- health logic uses multiple signals instead of treating ping as authoritative
- Azure control-plane context can be added without replacing packet-path evidence
- the Azure integration operates read-only and does not require infrastructure provisioning
