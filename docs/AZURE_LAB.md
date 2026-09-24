# Azure Lab Validation

This lab validates the normal Incident Pack against a real Azure-hosted Linux VM, then enriches the same report with read-only Azure Resource Manager network context.

The Incident Pack does **not** create the VM. Azure CLI commands below are only a disposable lab setup. Check the sizes/quotas included with your own Azure offer before creating resources, and delete the resource group when finished.

## 1. Create a small Linux VM

```bash
az login
az group create --name incident-pack-lab --location eastus

az vm create \
  --resource-group incident-pack-lab \
  --name ip-lab-vm \
  --image Ubuntu2204 \
  --size Standard_B1s \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard
```

If `Standard_B1s` is not included/available for your subscription or region, select an eligible burstable size for your account.

Capture the two values used by the Incident Pack:

```bash
VM_ID="$(az vm show -g incident-pack-lab -n ip-lab-vm --query id -o tsv)"
PUBLIC_IP="$(az vm show -d -g incident-pack-lab -n ip-lab-vm --query publicIps -o tsv)"
```

## 2. Create observable network states

SSH should already be allowed on TCP/22. Open TCP/8080 and TCP/8081 in the VM NSG:

```bash
az vm open-port -g incident-pack-lab -n ip-lab-vm --port 8080 --priority 1100
az vm open-port -g incident-pack-lab -n ip-lab-vm --port 8081 --priority 1110
```

Start a simple HTTP listener only on 8080:

```bash
ssh azureuser@"$PUBLIC_IP" \
  'nohup python3 -m http.server 8080 --bind 0.0.0.0 >/tmp/incident-pack-http.log 2>&1 &'
```

This creates three useful conditions:

| Port | Expected state | Meaning |
| --- | --- | --- |
| 22 | open | real SSH service reachable |
| 8080 | open | intentionally started test service reachable |
| 8081 | allowed by NSG but no listener | TCP refusal; host reachable but service unavailable |

To demonstrate an Azure policy/drop condition, test an additional port that the NSG does **not** allow. Depending on the path and policy, this commonly manifests as a timeout rather than an active refusal.

## 3. Obtain a short-lived ARM token

```bash
export AZURE_ACCESS_TOKEN="$(az account get-access-token --resource-type arm --query accessToken -o tsv)"
```

The token is used only to make read-only ARM GET requests. It is not written into the report.

## 4. Run a real cloud-hosted incident collection

```bash
incident-pack \
  --target "$PUBLIC_IP" \
  --ports 22 8080 8081 \
  --azure-vm-resource-id "$VM_ID" \
  --non-interactive \
  --log-level INFO \
  --out-dir ./azure-lab-output
```

The normal evidence path still performs DNS/IP reachability, traceroute, TCP checks, and local collector commands. Azure enrichment adds control-plane context such as:

- Azure region and resource group
- VM size, provisioning state, and power state
- NIC name
- private/public IPs
- VNet and subnet names
- attached network security group name

The report deliberately omits the subscription ID and ARM bearer token.

## 5. What this proves

The live lab demonstrates that the Incident Pack is not limited to an on-premises topology. Its core troubleshooting model remains protocol/path based, while cloud control-plane data provides additional context around the same target.

It also preserves useful distinctions:

- open service -> successful TCP path
- allowed port with no listener -> service refusal but positive host reachability
- policy/drop behavior -> timeout does not prove the host is down
- Azure metadata -> context, not a substitute for packet-path evidence

## 6. Cleanup

```bash
az group delete --name incident-pack-lab --yes --no-wait
unset AZURE_ACCESS_TOKEN VM_ID PUBLIC_IP
```
