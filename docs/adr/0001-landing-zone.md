# ADR 0001: Landing zone design for Danubia

**Status:** accepted · **Date:** 2026-11-01 · **Project:** 1

## Context

Danubia (250 employees, EU customers, personal data of staff and customers) is moving its workloads to Azure. Before any data moves, there must be a place to land that enforces data residency, cost control and secret handling. The Azure subscription also contains older, unrelated projects, and the budget for the whole subscription is EUR 3 per month.

## Decisions

### 1. Region: Sweden Central, with an EU-only allow list
- Sweden Central is an EU region with broad service availability, including Azure OpenAI, which Project 9 needs.
- The allow list also contains West Europe, North Europe and Germany West Central, so later projects can use a service that is missing in Sweden Central without leaving the EU.

### 2. Three resource groups by lifecycle: platform, data, apps
- Shared services (Key Vault, logs) live longer than any single application.
- Data (SQL, storage) needs stricter access than applications.
- Separate groups allow separate permissions and separate clean-up.

### 3. Built-in policies with Deny, assigned per Danubia resource group
- **Allowed locations** (GDPR data residency) and **Require a tag on resources** (`costCenter` for chargeback).
- Built-in definitions are maintained by Microsoft and recognised by auditors; no custom policy code to maintain.
- **Deny**, not Audit: a guardrail that only reports is easy to ignore.
- **Per resource group, not per subscription:** the subscription holds older projects in US and Canadian regions. A subscription-wide Deny would mark them non-compliant and block changes to them. A real company would do the same: protect the new landing zone first, widen the scope after the old estate is cleaned up.

### 4. Budget on the whole subscription
- Costs from any project count against the same card. A budget limited to Danubia would hide the real spend.
- Alerts at 50% and 100% of actual spend, plus 100% of forecast, so the warning comes before the money is gone.

### 5. Key Vault in RBAC mode; secrets read with DefaultAzureCredential
- RBAC mode uses the same Entra ID roles as the rest of Azure; there is one access model to audit.
- Managing the vault and reading its secrets are separate roles. The subscription owner has to be granted *Key Vault Secrets Officer* explicitly.
- `DefaultAzureCredential` uses `az login` on a laptop and a managed identity in Azure: no code change when workloads move to the cloud.

### 6. GitHub Actions with OIDC federation, no client secret
- No secret to leak, rotate or expire.
- Federated credentials are limited to the `main` branch and pull requests, in both the classic subject format and the newer format with immutable owner and repository IDs (rename-safe).
- The pipeline identity has Contributor and Resource Policy Contributor rights. It cannot create role assignments, so it cannot grant itself or others more access. Humans grant access; the pipeline deploys.

### 7. Log Analytics with a 0.1 GB daily cap
- Logs are essential, but uncapped logging is the most common surprise on a small Azure bill.

## Consequences

- Any resource outside the EU or without a `costCenter` tag in the Danubia resource groups is refused at creation time.
- Every infrastructure change goes through a pull request with a what-if preview.
- The pipeline's Contributor scope is broader than needed; Project 2 replaces it with a custom role scoped to the landing zone.
- Private networking, Conditional Access and PIM are documented as production requirements but are out of the demo budget.
