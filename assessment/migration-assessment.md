# Danubia Components: on-premises migration assessment

Generated 2026-10-31 15:19 by `src/danubia/assess/inventory.py`. Contains counts, sizes and paths only; no personal data values or secrets.

## Executive summary

- **Estate:** 1 SQL Server database (208 MB, 6 tables, 40,411 rows), a file server with 10,226 files (7.6 MB, oldest from 2011), and 360 machine log files from 12 machines.

- **Risks:** 1 critical, 3 high, 1 medium, 1 low. The critical and high findings must be fixed before or during the migration, not after it.

- **Storage:** 5,662 of 10,226 files (55%) have not changed in over 2 years and can go straight to cheaper cool or archive tiers.

- **Recommendation:** proceed with the landing zone (Project 1) and identity (Project 2) first, then migrate the database and files with the controls listed below.

## Findings

| Severity | Finding | Evidence | Action | Project |
| --- | --- | --- | --- | --- |
| CRITICAL | Passwords stored in plain text on the file server | `IT/Admin/server_notes.txt` | Rotate every listed password now; move secrets to Azure Key Vault; delete the file | 1, 2 |
| HIGH | Personal data (birth numbers, IBANs) outside the HR area | `Public/Exports/hr_export_for_payroll_DO_NOT_SHARE.csv` | Remove or move to HR; restrict access; report to the DPO under GDPR | 4 |
| HIGH | ERP runs at SQL Server 2016 level; 2016 extended support ended 14 Jul 2026 | compatibility level 130 | Migrate to Azure SQL Database (always patched) | 3 |
| HIGH | No backup of the ERP database recorded | msdb.dbo.backupset is empty | Azure SQL gives automatic backups with point-in-time restore; test a restore | 3, 10 |
| MEDIUM | 5 sensitive database columns, none masked or encrypted | `customers.contact_email`, `employees.email`, `employees.birth_number`, `employees.iban`, `employees.monthly_salary_eur` | Dynamic data masking and Entra ID roles in Azure SQL; least-privilege access | 2, 3 |
| LOW | Duplicate and version-cluttered files | 130 exact duplicates (0.06 MB), 278 'copy/final/v2' names | Clean up before migrating; enable Blob versioning instead of manual copies | 4 |
| INFO | Supplier invoices exist only as PDFs and are typed in by hand | 3,000 PDF files | Automate extraction with Azure AI Document Intelligence | 5 |

## 1. Database

| Property | Value |
| --- | --- |
| Product version | 16.0.4305.5 (Developer Edition (64-bit), RTM) |
| Compatibility level | 130 (SQL Server 2016 behaviour) |
| Recovery model | FULL |
| Allocated size | 208 MB |
| Last backup | none recorded |
| Masked or encrypted columns | 0 |

### Tables

| Table | Rows | Reserved MB | Columns | Foreign keys | Indexes | Primary key |
| --- | --- | --- | --- | --- | --- | --- |
| customers | 400 | 0.13 | 8 | 0 | 1 | yes |
| departments | 8 | 0.14 | 4 | 0 | 2 | yes |
| employees | 250 | 0.14 | 12 | 1 | 2 | yes |
| invoices | 19,453 | 2.15 | 8 | 1 | 3 | yes |
| orders | 20,000 | 2.02 | 9 | 3 | 3 | yes |
| products | 300 | 0.14 | 7 | 0 | 2 | yes |

### Sensitive columns

| Table | Column | Why |
| --- | --- | --- |
| customers | contact_email | contact details |
| employees | email | contact details |
| employees | birth_number | personal ID, birth number (found in data) |
| employees | iban | bank account, IBAN (found in data) |
| employees | monthly_salary_eur | salary |

## 2. File server

| Area | Files | MB | % unchanged > 2 y | % unchanged > 5 y | Files with personal data | Clutter names |
| --- | --- | --- | --- | --- | --- | --- |
| Finance/Budgets | 27 | 0.04 | 78% | 44% | 0 | 18 |
| Finance/SupplierInvoices | 3,000 | 4.95 | 34% | 0% | 0 | 0 |
| HR/Personnel | 507 | 0.09 | 86% | 66% | 250 | 0 |
| IT/Admin | 1 | 0.0 | 100% | 100% | 0 | 0 |
| Management/Board | 390 | 0.2 | 72% | 41% | 0 | 260 |
| Production/WorkInstructions | 1,500 | 0.63 | 80% | 45% | 0 | 0 |
| Public/Exports | 1 | 0.02 | 0% | 0% | 1 | 0 |
| Quality/InspectionReports | 2,000 | 0.23 | 78% | 46% | 0 | 0 |
| Sales/PriceLists | 300 | 1.22 | 79% | 41% | 0 | 0 |
| Sales/Quotes | 500 | 0.12 | 50% | 0% | 0 | 0 |
| Warehouse/ShippingNotes | 2,000 | 0.11 | 33% | 0% | 0 | 0 |

Personal data: 250 files inside HR (expected), 1 outside HR (not expected). 750 files contain email addresses. PDF contents are not scanned here; Project 5 reads them with Document Intelligence.

### Proposed storage tiers in Azure Blob Storage

| Tier | Rule | Files |
| --- | --- | --- |
| Hot | changed in the last 2 years | 4,564 |
| Cool | unchanged 2 to 5 years | 3,435 |
| Archive | unchanged over 5 years (check legal retention first) | 2,227 |

## 3. Machine logs

360 CSV files from 12 machines, 01 Oct 2026 to 30 Oct 2026: 518,400 sensor readings (31 MB). They are written to disk and never analysed; no database or dashboard exists.

## 4. Migration decision per workload

| Workload | Measured size | Decision | Azure target | Project |
| --- | --- | --- | --- | --- |
| ERP database | 208 MB, 40,411 rows | Replatform | Azure SQL Database | 3 |
| File server | 10,226 files, 7.6 MB | Replatform | Blob Storage with versioning, soft delete and lifecycle tiers | 4 |
| Supplier invoices | 3,000 PDFs | Refactor | Document Intelligence + Functions | 5 |
| Intranet app | 1 app | Replatform | Container Apps with Entra ID sign-in | 6 |
| Machine logs | 518,400 rows | Refactor | Azure Data Explorer | 8 |
| Active Directory | 250 users | Replatform | Entra ID with MFA | 2 |
| NAS backups | - | Retire | Built-in Azure backups | 10 |

## 5. Next steps

1. Fix the critical finding today: rotate the exposed passwords.
2. Deploy the landing zone with EU-only policy, budget and Key Vault (Project 1).
3. Create named accounts with MFA for all staff and remove shared admin accounts (Project 2).
4. Migrate the ERP database with row-count and checksum validation (Project 3).
