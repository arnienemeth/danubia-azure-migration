# Danubia Components s.r.o. (fictional)

Bratislava-based supplier of metal and plastic parts to automotive and appliance makers.
250 employees, one plant, one warehouse, customers in SK, HU, AT, DE.

| Department | Staff |
|---|---|
| Production | 120 |
| Warehouse & logistics | 35 |
| Sales & customer service | 25 |
| Finance & accounting | 15 |
| Quality | 15 |
| HR | 8 |
| IT | 4 |
| Management | 28 |

## On-premises estate (simulated)

- ERP database: SQL Server 2016 (simulated with SQL Server 2022 at compatibility level 130)
- File server `fs01`: ~10,000 files in department folders
- Scanned supplier invoices: ~3,000 PDFs per year
- Intranet: Python/Flask app on IIS with local accounts
- Machine logs: CSV dumps from 12 machines
- Identity: on-prem Active Directory, shared admin account, no MFA
- Backups: nightly to a NAS in the same room

## Board goals

1. No data loss and a tested restore for every system.
2. MFA and least-privilege access for all 250 staff.
3. Personal data handled under GDPR and kept in the EU.
4. Faster invoice processing; use the data the company already has.
5. Predictable monthly IT cost, with alerts before overspending.
