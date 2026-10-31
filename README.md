# Danubia Goes Azure

A fictional 250-employee Slovak manufacturer, **Danubia Components s.r.o.**, moves from its own server room to Microsoft Azure.
The migration is split into 10 projects; this repo grows with each one.

| # | Project | Status |
|---|---------|--------|
| 1 | Cloud foundation, guardrails and on-prem simulation | In progress |
| 2 | Identity for 250 staff | Planned |
| 3 | ERP database migration (SQL Server to Azure SQL) | Planned |
| 4 | File server migration (to Blob Storage) | Planned |
| 5 | Invoice automation (Document Intelligence) | Planned |
| 6 | Intranet modernisation (Container Apps) | Planned |
| 7 | Integration and events | Planned |
| 8 | Machine data and analytics | Planned |
| 9 | Internal AI assistant | Planned |
| 10 | Operations, DR and FinOps | Planned |

**Budget rule:** the whole Azure subscription stays under EUR 3 per month.

## Repository layout

```
assessment/      generated migration assessment
docs/            company profile and architecture decision records (ADRs)
infra/           Bicep infrastructure as code
onprem-sim/      generated "on-premises" data (not committed)
src/danubia/     Python: simulators and assessment tools
tests/           tests
.github/         GitHub Actions pipelines
```
