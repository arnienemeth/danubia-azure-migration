"""Discovery and migration assessment of Danubia's on-premises estate.

Run:   uv run python -m danubia.assess.inventory
Output: assessment/migration-assessment.md

It does in plain Python what a consultant (or Azure Migrate with its appliance) does in week one:
inventory the database, the file server and the machine logs; find risks; and propose a migration
decision per workload. The report contains counts, sizes and file paths only, never personal data
values or secrets, so it is safe to commit and share.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime
from pathlib import Path

import polars as pl
from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine, text

from danubia.config import PROJECT_ROOT, onprem_engine

TODAY = date(2026, 10, 31)
FILESHARE = PROJECT_ROOT / "onprem-sim" / "fileshare"
MACHINE_LOGS = PROJECT_ROOT / "onprem-sim" / "machine-logs"
REPORT = PROJECT_ROOT / "assessment" / "migration-assessment.md"
SQL2016_END_OF_SUPPORT = date(2026, 7, 14)  # end of extended support for SQL Server 2016

# What personal data looks like inside text
PII = {
    "birth number": re.compile(r"\b\d{6}/\d{3,4}\b"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
}
# Lines that look like stored credentials ("password: ...", "admin: ...")
SECRET_LINE = re.compile(r"(?im)^.*\b(password|passwd|pwd|secret|admin|account)\b\s*:.*$")
# File names that signal version clutter
CLUTTER = re.compile(r"(?i)(copy of|_final|_v\d+\b|\(\d+\))")
# What sensitive database columns are usually called
SENSITIVE_COLUMN = {
    "personal ID": re.compile(r"birth|rodne|national_id|ssn", re.I),
    "bank account": re.compile(r"iban|bank_account", re.I),
    "salary": re.compile(r"salary|wage", re.I),
    "contact details": re.compile(r"email|phone|address", re.I),
}


# ====================================================================== database
def assess_database(engine: Engine) -> dict:
    with engine.connect() as conn:
        version, edition, level = conn.execute(text(
            "SELECT CAST(SERVERPROPERTY('ProductVersion') AS varchar(30)), "
            "CAST(SERVERPROPERTY('Edition') AS varchar(60)), CAST(SERVERPROPERTY('ProductLevel') AS varchar(20))"
        )).one()
        compat, recovery = conn.execute(text(
            "SELECT compatibility_level, recovery_model_desc FROM sys.databases WHERE name = DB_NAME()")).one()
        size_mb = conn.execute(text("SELECT SUM(size) * 8 / 1024.0 FROM sys.database_files")).scalar_one()
        last_backup = conn.execute(text(
            "SELECT MAX(backup_finish_date) FROM msdb.dbo.backupset WHERE database_name = DB_NAME()")).scalar_one()
        protected = conn.execute(text(
            "SELECT (SELECT COUNT(*) FROM sys.masked_columns) + "
            "(SELECT COUNT(*) FROM sys.columns WHERE encryption_type IS NOT NULL)")).scalar_one()
        columns = conn.execute(text(
            "SELECT t.name, c.name, ty.name FROM sys.columns c "
            "JOIN sys.tables t ON t.object_id = c.object_id "
            "JOIN sys.types ty ON ty.user_type_id = c.user_type_id ORDER BY t.name, c.column_id")).all()

        sensitive = []
        for table, column, col_type in columns:
            reasons = [label for label, rx in SENSITIVE_COLUMN.items() if rx.search(column)]
            if col_type in ("varchar", "nvarchar", "char", "nchar"):
                # look at a sample of real values, because names can lie
                sample = conn.execute(text(
                    f"SELECT TOP 200 CAST([{column}] AS nvarchar(200)) FROM dbo.[{table}] WHERE [{column}] IS NOT NULL"
                )).scalars().all()
                blob = "\n".join(sample)
                for label in ("birth number", "IBAN"):
                    if PII[label].search(blob) and label not in reasons:
                        reasons.append(f"{label} (found in data)")
            if reasons:
                sensitive.append({"table": table, "column": column, "category": ", ".join(reasons)})

    tables = pl.read_database(
        """SELECT t.name AS table_name,
                  SUM(CASE WHEN s.index_id IN (0, 1) THEN s.row_count ELSE 0 END) AS row_count,
                  CAST(SUM(s.reserved_page_count) * 8 / 1024.0 AS DECIMAL(10, 2)) AS reserved_mb,
                  (SELECT COUNT(*) FROM sys.columns c WHERE c.object_id = t.object_id) AS columns,
                  (SELECT COUNT(*) FROM sys.foreign_keys f WHERE f.parent_object_id = t.object_id) AS foreign_keys,
                  (SELECT COUNT(*) FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id > 0) AS indexes,
                  OBJECTPROPERTY(t.object_id, 'TableHasPrimaryKey') AS has_primary_key
           FROM sys.tables t
           JOIN sys.dm_db_partition_stats s ON s.object_id = t.object_id
           GROUP BY t.object_id, t.name
           ORDER BY t.name""",
        engine,
    )
    return {
        "version": version, "edition": edition, "level": level, "compat": compat, "recovery": recovery,
        "size_mb": float(size_mb), "last_backup": last_backup, "protected_columns": protected,
        "tables": tables, "sensitive": sensitive,
    }


# ====================================================================== file server
def area_of(rel: Path) -> str:
    """'HR/Personnel/0042_Novak/file.txt' -> 'HR/Personnel'."""
    return "/".join(rel.parts[:2]) if len(rel.parts) > 2 else rel.parts[0]


def scan_fileshare(root: Path) -> pl.DataFrame:
    records = []
    for dirpath, _, names in os.walk(root):
        for name in names:
            path = Path(dirpath) / name
            data = path.read_bytes()
            rel = path.relative_to(root)
            record = {
                "path": rel.as_posix(), "area": area_of(rel), "name": name,
                "ext": path.suffix.lower().lstrip("."), "bytes": len(data),
                "modified": datetime.fromtimestamp(path.stat().st_mtime),
                "sha256": hashlib.sha256(data).hexdigest(),  # fingerprint: same content = same hash
                "birth_numbers": 0, "ibans": 0, "emails": 0, "secret_lines": 0,
                "clutter": bool(CLUTTER.search(name)),
            }
            if record["ext"] in ("txt", "csv"):
                content = data.decode("utf-8", errors="ignore")
                record["birth_numbers"] = len(PII["birth number"].findall(content))
                record["ibans"] = len(PII["IBAN"].findall(content))
                record["emails"] = len(PII["email"].findall(content))
                record["secret_lines"] = len(SECRET_LINE.findall(content))
            records.append(record)
    df = pl.DataFrame(records)
    return df.with_columns(
        age_days=(pl.lit(TODAY) - pl.col("modified").dt.date()).dt.total_days(),
        has_pii=(pl.col("birth_numbers") + pl.col("ibans")) > 0,
        in_hr=pl.col("area").str.starts_with("HR"),
    )


def summarise_fileshare(files: pl.DataFrame) -> dict:
    per_area = (
        files.group_by("area").agg(
            pl.len().alias("files"),
            (pl.col("bytes").sum() / 1_048_576).round(2).alias("mb"),
            ((pl.col("age_days") > 730).mean() * 100).round(0).alias("pct_over_2y"),
            ((pl.col("age_days") > 1825).mean() * 100).round(0).alias("pct_over_5y"),
            pl.col("has_pii").sum().alias("files_with_pii"),
            pl.col("clutter").sum().alias("clutter_names"),
        ).sort("area")
    )
    dupes = files.group_by("sha256").agg(pl.len().alias("copies"), pl.col("bytes").first()).filter(pl.col("copies") > 1)
    tiers = files.select(
        hot=(pl.col("age_days") <= 730).sum(),
        cool=((pl.col("age_days") > 730) & (pl.col("age_days") <= 1825)).sum(),
        archive=(pl.col("age_days") > 1825).sum(),
    ).row(0, named=True)
    return {
        "files": files.height,
        "mb": files["bytes"].sum() / 1_048_576,
        "oldest": files["modified"].min(),
        "per_area": per_area,
        "duplicate_groups": dupes.height,
        "redundant_files": int((dupes["copies"] - 1).sum()) if dupes.height else 0,
        "redundant_mb": float(((dupes["copies"] - 1) * dupes["bytes"]).sum() / 1_048_576) if dupes.height else 0.0,
        "clutter": int(files["clutter"].sum()),
        "pii_in_hr": int(files.filter(pl.col("in_hr") & pl.col("has_pii")).height),
        "pii_outside_hr": files.filter(~pl.col("in_hr") & pl.col("has_pii"))["path"].to_list(),
        "credential_files": files.filter(pl.col("secret_lines") > 0)["path"].to_list(),
        "files_with_emails": int((files["emails"] > 0).sum()),
        "tiers": tiers,
        "pdfs": int((files["ext"] == "pdf").sum()),
    }


# ====================================================================== machine logs
def assess_machines(root: Path) -> dict:
    csvs = sorted(root.rglob("*.csv"))
    if not csvs:
        return {"files": 0}
    days = sorted({p.stem.split("_")[1] for p in csvs})
    rows = sum(p.read_bytes().count(b"\n") - 1 for p in csvs)
    return {
        "files": len(csvs), "machines": len({p.parent.name for p in csvs}),
        "mb": sum(p.stat().st_size for p in csvs) / 1_048_576, "rows": rows,
        "first_day": datetime.strptime(days[0], "%Y%m%d").date(),
        "last_day": datetime.strptime(days[-1], "%Y%m%d").date(),
    }


# ====================================================================== report
def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    return "\n".join(out)


def build_findings(db: dict, fs: dict) -> list[list]:
    findings = []
    if fs["credential_files"]:
        findings.append(["CRITICAL", "Passwords stored in plain text on the file server",
                         ", ".join(f"`{p}`" for p in fs["credential_files"]),
                         "Rotate every listed password now; move secrets to Azure Key Vault; delete the file", "1, 2"])
    if fs["pii_outside_hr"]:
        findings.append(["HIGH", "Personal data (birth numbers, IBANs) outside the HR area",
                         ", ".join(f"`{p}`" for p in fs["pii_outside_hr"]),
                         "Remove or move to HR; restrict access; report to the DPO under GDPR", "4"])
    if TODAY > SQL2016_END_OF_SUPPORT and db["compat"] <= 130:
        findings.append(["HIGH", "ERP runs at SQL Server 2016 level; 2016 extended support ended "
                         f"{SQL2016_END_OF_SUPPORT:%d %b %Y}",
                         f"compatibility level {db['compat']}", "Migrate to Azure SQL Database (always patched)", "3"])
    if db["last_backup"] is None:
        findings.append(["HIGH", "No backup of the ERP database recorded", "msdb.dbo.backupset is empty",
                         "Azure SQL gives automatic backups with point-in-time restore; test a restore", "3, 10"])
    if db["sensitive"] and db["protected_columns"] == 0:
        findings.append(["MEDIUM", f"{len(db['sensitive'])} sensitive database columns, none masked or encrypted",
                         ", ".join(f"`{s['table']}.{s['column']}`" for s in db["sensitive"]),
                         "Dynamic data masking and Entra ID roles in Azure SQL; least-privilege access", "2, 3"])
    if fs["redundant_files"] or fs["clutter"]:
        findings.append(["LOW", "Duplicate and version-cluttered files",
                         f"{fs['redundant_files']} exact duplicates ({fs['redundant_mb']:.2f} MB), "
                         f"{fs['clutter']} 'copy/final/v2' names",
                         "Clean up before migrating; enable Blob versioning instead of manual copies", "4"])
    findings.append(["INFO", "Supplier invoices exist only as PDFs and are typed in by hand",
                     f"{fs['pdfs']:,} PDF files", "Automate extraction with Azure AI Document Intelligence", "5"])
    return findings


def render(db: dict, fs: dict, ml: dict) -> str:
    t = db["tables"]
    total_rows = int(t["row_count"].sum())
    findings = build_findings(db, fs)
    counts = {s: sum(1 for f in findings if f[0] == s) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    tiers = fs["tiers"]

    parts = [
        "# Danubia Components: on-premises migration assessment",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `src/danubia/assess/inventory.py`. "
        "Contains counts, sizes and paths only; no personal data values or secrets.",
        "## Executive summary",
        f"- **Estate:** 1 SQL Server database ({db['size_mb']:,.0f} MB, {len(t)} tables, {total_rows:,} rows), "
        f"a file server with {fs['files']:,} files ({fs['mb']:,.1f} MB, oldest from {fs['oldest']:%Y}), and "
        f"{ml.get('files', 0)} machine log files from {ml.get('machines', 0)} machines.",
        f"- **Risks:** {counts['CRITICAL']} critical, {counts['HIGH']} high, {counts['MEDIUM']} medium, "
        f"{counts['LOW']} low. The critical and high findings must be fixed before or during the migration, "
        "not after it.",
        f"- **Storage:** {tiers['cool'] + tiers['archive']:,} of {fs['files']:,} files "
        f"({(tiers['cool'] + tiers['archive']) / fs['files']:.0%}) have not changed in over 2 years and can go "
        "straight to cheaper cool or archive tiers.",
        "- **Recommendation:** proceed with the landing zone (Project 1) and identity (Project 2) first, "
        "then migrate the database and files with the controls listed below.",
        "## Findings",
        md_table(["Severity", "Finding", "Evidence", "Action", "Project"], findings),
        "## 1. Database",
        md_table(["Property", "Value"], [
            ["Product version", f"{db['version']} ({db['edition']}, {db['level']})"],
            ["Compatibility level", f"{db['compat']} (SQL Server 2016 behaviour)"],
            ["Recovery model", db["recovery"]],
            ["Allocated size", f"{db['size_mb']:,.0f} MB"],
            ["Last backup", db["last_backup"] or "none recorded"],
            ["Masked or encrypted columns", db["protected_columns"]],
        ]),
        "### Tables",
        md_table(["Table", "Rows", "Reserved MB", "Columns", "Foreign keys", "Indexes", "Primary key"],
                 [[r["table_name"], f"{r['row_count']:,}", r["reserved_mb"], r["columns"], r["foreign_keys"],
                   r["indexes"], "yes" if r["has_primary_key"] else "**no**"] for r in t.iter_rows(named=True)]),
        "### Sensitive columns",
        md_table(["Table", "Column", "Why"], [[s["table"], s["column"], s["category"]] for s in db["sensitive"]]),
        "## 2. File server",
        md_table(["Area", "Files", "MB", "% unchanged > 2 y", "% unchanged > 5 y", "Files with personal data",
                  "Clutter names"],
                 [[r["area"], f"{r['files']:,}", r["mb"], f"{r['pct_over_2y']:.0f}%", f"{r['pct_over_5y']:.0f}%",
                   r["files_with_pii"], r["clutter_names"]] for r in fs["per_area"].iter_rows(named=True)]),
        f"Personal data: {fs['pii_in_hr']} files inside HR (expected), {len(fs['pii_outside_hr'])} outside HR "
        f"(not expected). {fs['files_with_emails']:,} files contain email addresses. PDF contents are not scanned "
        "here; Project 5 reads them with Document Intelligence.",
        "### Proposed storage tiers in Azure Blob Storage",
        md_table(["Tier", "Rule", "Files"], [
            ["Hot", "changed in the last 2 years", f"{tiers['hot']:,}"],
            ["Cool", "unchanged 2 to 5 years", f"{tiers['cool']:,}"],
            ["Archive", "unchanged over 5 years (check legal retention first)", f"{tiers['archive']:,}"],
        ]),
        "## 3. Machine logs",
        (f"{ml['files']} CSV files from {ml['machines']} machines, {ml['first_day']:%d %b %Y} to "
         f"{ml['last_day']:%d %b %Y}: {ml['rows']:,} sensor readings ({ml['mb']:,.0f} MB). "
         "They are written to disk and never analysed; no database or dashboard exists."
         if ml.get("files") else "No machine logs found."),
        "## 4. Migration decision per workload",
        md_table(["Workload", "Measured size", "Decision", "Azure target", "Project"], [
            ["ERP database", f"{db['size_mb']:,.0f} MB, {total_rows:,} rows", "Replatform", "Azure SQL Database", 3],
            ["File server", f"{fs['files']:,} files, {fs['mb']:,.1f} MB", "Replatform",
             "Blob Storage with versioning, soft delete and lifecycle tiers", 4],
            ["Supplier invoices", f"{fs['pdfs']:,} PDFs", "Refactor", "Document Intelligence + Functions", 5],
            ["Intranet app", "1 app", "Replatform", "Container Apps with Entra ID sign-in", 6],
            ["Machine logs", f"{ml.get('rows', 0):,} rows", "Refactor", "Azure Data Explorer", 8],
            ["Active Directory", f"{int(t.filter(pl.col('table_name') == 'employees')['row_count'].sum())} users",
             "Replatform",
             "Entra ID with MFA", 2],
            ["NAS backups", "-", "Retire", "Built-in Azure backups", 10],
        ]),
        "## 5. Next steps",
        "1. Fix the critical finding today: rotate the exposed passwords.\n"
        "2. Deploy the landing zone with EU-only policy, budget and Key Vault (Project 1).\n"
        "3. Create named accounts with MFA for all staff and remove shared admin accounts (Project 2).\n"
        "4. Migrate the ERP database with row-count and checksum validation (Project 3).",
    ]
    return "\n\n".join(parts) + "\n"


def console_summary(console: Console, db: dict, fs: dict) -> None:
    table = Table(title="Assessment findings")
    table.add_column("Severity")
    table.add_column("Finding")
    colours = {"CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan", "INFO": "dim"}
    for severity, finding, *_ in build_findings(db, fs):
        table.add_row(f"[{colours[severity]}]{severity}[/]", finding)
    console.print(table)


def main() -> None:
    console = Console()
    with console.status("Assessing the database ..."):
        db = assess_database(onprem_engine())
    with console.status("Scanning the file server ..."):
        fs = summarise_fileshare(scan_fileshare(FILESHARE))
    with console.status("Assessing machine logs ..."):
        ml = assess_machines(MACHINE_LOGS)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(render(db, fs, ml), encoding="utf-8")
    console_summary(console, db, fs)
    console.print(f"[green]Report written:[/] {REPORT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
