# Security Policy

## Intended use

Network Incident Pack is a troubleshooting and evidence-collection tool. Run it only against systems, networks, and services that you own or are explicitly authorized to test.

The project intentionally limits one run to a troubleshooting-sized scope:

- maximum 32 unique TCP ports
- maximum 16 collection workers
- maximum 3 TCP attempts per port
- maximum 30 seconds per TCP connect attempt
- maximum 60 seconds per host command

These limits are guardrails, not a substitute for authorization or network change controls.

## Credential handling

Credentials and access tokens must be supplied through environment variables. Do not commit `.env` files, private keys, exported cloud credentials, or reports containing sensitive infrastructure data.

The report layer rejects known secret-bearing keys and redacts recognizable authorization/password/token patterns from report text and integration error bodies. This is defense in depth; it is not a guarantee that arbitrary sensitive data can never appear in raw command output. Review reports before sharing them publicly.

## External integrations

- NetBox integration is read-only.
- Azure Resource Manager integration is read-only.
- ServiceNow writes occur only when `--servicenow-update` is explicitly supplied.
- TLS verification is not disabled by the application.
- API redirects are not automatically followed with integration credentials.

## Reporting a vulnerability

Use GitHub's private **Report a vulnerability** / Security Advisory flow when it is available for this repository. Do not post credentials, tokens, private infrastructure data, or working exploit details in a public issue.

## Supported release

Security fixes are applied to the latest tagged release.

## Input-validation boundary

Host and integration endpoint validation is intended to prevent accidental option/URL confusion, malformed operator configuration, and obvious credential-routing mistakes in an operations tool. Integration endpoints are operator-configured rather than arbitrary attacker-supplied request parameters. Validation rejects control/whitespace characters, non-ASCII host/endpoint text, malformed hostnames, embedded URL credentials, query/fragment data, backslash ambiguity, and invalid ports. This is defense in depth; the project does not claim to be a hardened URL parser for hostile multi-tenant input.


## Release hygiene

Release ZIPs are built with `git archive`, not by compressing a working directory. This keeps `.git`, virtual environments, Python caches, build metadata, generated reports, and other local artifacts out of distributable source archives. CI verifies the built archive before merge.
