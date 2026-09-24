# Design Notes

## Keep the raw evidence

Parsed fields are useful for automation, but an engineer may still need the original command output during escalation. Reports keep both.

## Reachability and service state are different

A refused TCP connection is a failed service check, but the RST proves the target answered at Layer 4. Likewise, failed ping does not prove a host is down when TCP succeeds.

## Use concurrency where the work is waiting

TCP checks and host commands are I/O-bound, so bounded `ThreadPoolExecutor` pools reduce collection time without adding multiprocessing complexity. Output order is restored before reporting.

Retries are selective. Timeouts/resets and transient API errors may be retried; connection refusals, bad configuration, and missing commands are recorded immediately.

## Keep external systems optional

NetBox is used for read-only inventory resolution. Azure ARM is used for optional read-only cloud network context. ServiceNow writes only when `--servicenow-update` is supplied. The core incident pack still works with none of these systems available.

Credentials come from environment variables. Structured secret-bearing fields are rejected, and recognizable authorization/credential patterns embedded in text are redacted before reports are written or sent externally.

## Stay focused on incident collection

The core remains host-side and vendor-neutral. A cloud-hosted target uses the same network checks as an on-premises target; Azure data is supplemental control-plane context. Device-specific adapters can be added later if they provide useful troubleshooting evidence, but this repository is not intended to become a general network-management or cloud-provisioning project.

## Release archives come from Git, not the working directory

Release ZIPs are built with `scripts/build_release.sh`, which wraps `git archive`. Only files tracked at the selected Git ref are included. Local virtual environments, `.git`, caches, generated reports, and build metadata therefore cannot enter a release archive merely because they exist in the maintainer's working directory.
