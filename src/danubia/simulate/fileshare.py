"""Generate Danubia's on-prem file server \\fs01 as a folder tree of ~10,000 files.

Run (after the ERP generator):   uv run python -m danubia.simulate.fileshare

What makes it realistic, and useful for later projects:
- department folders with typical document types (PDF supplier invoices, CSV shipping notes, ...)
- last-modified dates spread over 9 years, so storage tiering decisions mean something
- personal data where it belongs (HR) AND where it should not be (a "Public" export, an IT notes file)
- messy naming habits: "Copy of", "final_v2", duplicates
HR files are built from the real employees table, so files and database agree.
"""

from __future__ import annotations

import os
import random
import shutil
import time
import unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
from faker import Faker
from fpdf import FPDF
from rich.console import Console
from rich.table import Table

from danubia.config import PROJECT_ROOT, onprem_engine

SEED = 7
TODAY = date(2026, 10, 31)
ROOT = PROJECT_ROOT / "onprem-sim" / "fileshare"

FAKERS = {"SK": Faker("sk_SK"), "HU": Faker("hu_HU"), "AT": Faker("de_AT"), "DE": Faker("de_DE")}
fake = FAKERS["SK"]


def latin1(text: str) -> str:
    """PDF core fonts only know Latin-1; fold accents (č -> c) so text always renders."""
    return unicodedata.normalize("NFKD", text).encode("latin-1", "ignore").decode("latin-1")


def random_past(max_years: float = 9.0, min_days: int = 0) -> datetime:
    days = random.randint(min_days, int(max_years * 365))
    return datetime.combine(TODAY, datetime.min.time()) - timedelta(days=days, seconds=random.randint(0, 86_399))


def set_age(path: Path, when: datetime) -> None:
    ts = time.mktime(when.timetuple())
    os.utime(path, (ts, ts))


# ---------------------------------------------------------------- Finance
SUPPLIERS = [(c, FAKERS[c].company(), FAKERS[c].address().replace("\n", ", ")) for c in
             ["SK"] * 12 + ["HU"] * 5 + ["AT"] * 4 + ["DE"] * 7]
ITEMS = ["Steel coil DC01 1.5 mm", "Aluminium sheet AW-5754", "PP granulate black", "Machine oil ISO VG 46",
         "Cutting inserts CNMG", "Pallets EUR 1200x800", "Cardboard boxes 600x400", "Nitrile gloves (100)",
         "Hydraulic hose DN10", "Welding wire G3Si1", "Maintenance service (hours)", "Electricity surcharge"]


def supplier_invoice_pdf(path: Path, number: str, issued: date, supplier: tuple[str, str, str]) -> None:
    country, name, address = supplier
    lines = [(random.choice(ITEMS), random.randint(1, 200), round(random.uniform(2, 900), 2))
             for _ in range(random.randint(1, 6))]
    net = round(sum(q * p for _, q, p in lines), 2)
    vat = round(net * 0.20, 2)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for text in [latin1(name), latin1(address), f"VAT ID: {country}{random.randint(10**9, 10**10 - 1)}", "",
                 f"Invoice no: {number}", f"Issue date: {issued:%d.%m.%Y}",
                 f"Due date: {issued + timedelta(days=30):%d.%m.%Y}", "",
                 "Bill to: Danubia Components s.r.o., Priemyselna 12, 821 09 Bratislava, SK2020123456", ""]:
        pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    for header, width in [("Item", 95), ("Qty", 20), ("Unit EUR", 30), ("Total EUR", 35)]:
        pdf.cell(width, 7, header, border=1)
    pdf.ln()
    pdf.set_font("Helvetica", size=10)
    for item, qty, price in lines:
        for value, width in [(item, 95), (str(qty), 20), (f"{price:,.2f}", 30), (f"{qty * price:,.2f}", 35)]:
            pdf.cell(width, 7, value, border=1)
        pdf.ln()
    pdf.ln(4)
    for text in [f"Net: EUR {net:,.2f}", f"VAT 20%: EUR {vat:,.2f}", f"TOTAL: EUR {net + vat:,.2f}", "",
                 f"Pay to IBAN: {FAKERS['SK'].iban()}"]:
        pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def make_finance() -> None:
    for n in range(3000):
        issued = random_past(max_years=3).date()
        supplier = random.choice(SUPPLIERS)
        folder = ROOT / "Finance" / "SupplierInvoices" / str(issued.year)
        folder.mkdir(parents=True, exist_ok=True)
        number = f"{supplier[0]}-{issued.year}-{n + 10000:05d}"  # unique, so no file overwrites another
        path = folder / f"invoice_{number}.pdf"
        supplier_invoice_pdf(path, number, issued, supplier)
        set_age(path, datetime.combine(issued, datetime.min.time()) + timedelta(hours=random.randint(8, 17)))
    budget = ROOT / "Finance" / "Budgets"
    budget.mkdir(parents=True, exist_ok=True)
    for year in range(2018, 2027):
        for name in [f"budget_{year}.csv", f"budget_{year}_final.csv", f"budget_{year}_final_v2.csv"]:
            p = budget / name
            p.write_text("cost_center,month,budget_eur\n" + "\n".join(
                f"CC-{cc}00,{m},{random.randint(20_000, 400_000)}" for cc in range(1, 9) for m in range(1, 13)),
                encoding="utf-8")
            set_age(p, datetime(year - 1, 12, random.randint(1, 28)))


# ---------------------------------------------------------------- HR (personal data, where it belongs)
def make_hr(employees: pl.DataFrame) -> None:
    for e in employees.iter_rows(named=True):
        folder = ROOT / "HR" / "Personnel" / f"{e['employee_id']:04d}_{latin1(e['last_name']).replace(' ', '')}"
        folder.mkdir(parents=True, exist_ok=True)
        hired = datetime.combine(e["hired_on"], datetime.min.time())
        personal = folder / "personal_data.txt"
        personal.write_text(
            f"Name: {e['first_name']} {e['last_name']}\nBirth number: {e['birth_number']}\n"
            f"Address: {FAKERS[e['country']].address()}\nPhone: {FAKERS[e['country']].phone_number()}\n"
            f"IBAN: {e['iban']}\nEmail: {e['email']}\n", encoding="utf-8")
        set_age(personal, hired)
        contract = folder / "employment_contract.txt"
        contract.write_text(
            f"EMPLOYMENT CONTRACT\nEmployer: Danubia Components s.r.o.\nEmployee: {e['first_name']} {e['last_name']}\n"
            f"Position: {e['job_title']}\nStart date: {e['hired_on']:%d.%m.%Y}\n"
            f"Monthly gross salary: EUR {e['monthly_salary_eur']:,.2f}\n", encoding="utf-8")
        set_age(contract, hired)
        if not e["is_active"]:
            leaver = folder / "termination_letter.txt"
            leaver.write_text(f"Termination of employment: {e['first_name']} {e['last_name']}\n", encoding="utf-8")
            set_age(leaver, random_past(max_years=1))


# ---------------------------------------------------------------- other departments
def text_files(folder: str, prefix: str, count: int, ext: str, body, max_years: float = 9.0) -> None:
    d = ROOT / folder
    d.mkdir(parents=True, exist_ok=True)
    for n in range(count):
        p = d / f"{prefix}_{n:05d}.{ext}"
        p.write_text(body(n), encoding="utf-8")
        set_age(p, random_past(max_years))


def make_departments() -> None:
    text_files("Quality/InspectionReports", "inspection", 2000, "txt", lambda n: (
        f"Inspection report QI-{n:05d}\nPart: DC-{random.randint(1, 300):04d}\n"
        f"Sample size: {random.choice([5, 10, 20, 50])}\nDefects found: {random.choices([0, 1, 2, 5], [80, 12, 6, 2])[0]}\n"
        f"Inspector: {fake.name()}\nResult: {random.choices(['PASS', 'FAIL'], [92, 8])[0]}\n"))
    text_files("Production/WorkInstructions", "wi", 1500, "txt", lambda n: (
        f"Work instruction WI-{n:05d}\nMachine: M{random.randint(1, 12):02d}\n" + fake.paragraph(nb_sentences=10)))
    text_files("Warehouse/ShippingNotes", "shipping", 2000, "csv", lambda n: (
        "order_id,carrier,pallets,weight_kg\n"
        f"{random.randint(1, 20000)},{random.choice(['DHL', 'Raben', 'DB Schenker', 'GLS'])},"
        f"{random.randint(1, 12)},{random.randint(80, 9000)}\n"), max_years=3)
    text_files("Sales/PriceLists", "pricelist", 300, "csv", lambda n: (
        "sku,price_eur\n" + "\n".join(f"DC-{s:04d},{random.uniform(0.15, 12):.2f}" for s in range(1, 301))))
    text_files("Sales/Quotes", "quote", 500, "txt", lambda n: (
        f"Quotation Q-{n:05d}\nCustomer: {random.choice(list(FAKERS.values())).company()}\n"
        f"Contact: {fake.name()} <{fake.email()}>\n" + fake.paragraph(nb_sentences=4)), max_years=4)

    board = ROOT / "Management" / "Board"
    board.mkdir(parents=True, exist_ok=True)
    for n in range(130):
        when = random_past()
        for name in [f"board_minutes_{when:%Y_%m}_{n}.txt", f"Copy of board_minutes_{when:%Y_%m}_{n}.txt",
                     f"board_minutes_{when:%Y_%m}_{n}_FINAL.txt"]:
            p = board / name
            p.write_text("Board meeting minutes\n" + fake.paragraph(nb_sentences=12), encoding="utf-8")
            set_age(p, when)


# ---------------------------------------------------------------- the risky leftovers an assessment must find
def make_risky_files(employees: pl.DataFrame) -> None:
    public = ROOT / "Public" / "Exports"
    public.mkdir(parents=True, exist_ok=True)
    export = public / "hr_export_for_payroll_DO_NOT_SHARE.csv"
    employees.select("employee_id", "first_name", "last_name", "birth_number", "iban", "monthly_salary_eur") \
        .write_csv(export)
    set_age(export, random_past(max_years=2))

    it = ROOT / "IT" / "Admin"
    it.mkdir(parents=True, exist_ok=True)
    notes = it / "server_notes.txt"
    notes.write_text("fs01 local admin: administrator / Danubia2017!\nERP sa password: Erp_sa_2016\n"
                     "VPN shared account: vpnuser / Summer2019\n", encoding="utf-8")  # fake, for the scan to find
    set_age(notes, datetime(2019, 3, 14, 10, 0))


def summary(console: Console) -> None:
    rows = [{"folder": "/".join(p.relative_to(ROOT).parts[:2]), "bytes": p.stat().st_size,
             "modified": datetime.fromtimestamp(p.stat().st_mtime)} for p in ROOT.rglob("*") if p.is_file()]
    df = pl.DataFrame(rows).group_by("folder").agg(
        pl.len().alias("files"),
        (pl.col("bytes").sum() / 1_048_576).round(1).alias("MB"),
        pl.col("modified").min().dt.year().alias("oldest"),
    ).sort("folder")
    table = Table(title=f"Simulated file server fs01: {len(rows):,} files")
    for col in df.columns:
        table.add_column(col, justify="right" if col != "folder" else "left")
    for r in df.iter_rows():
        table.add_row(*[str(v) for v in r])
    console.print(table)


def main() -> None:
    console = Console()
    random.seed(SEED)
    Faker.seed(SEED)
    if ROOT.exists():
        shutil.rmtree(ROOT)  # rebuild from scratch: same seed, same files
    ROOT.mkdir(parents=True)

    employees = pl.read_database("SELECT * FROM dbo.employees", onprem_engine())
    steps = [("Finance (3,000 PDF invoices)", make_finance), ("HR personnel files", lambda: make_hr(employees)),
             ("Other departments", make_departments), ("Risky leftovers", lambda: make_risky_files(employees))]
    for label, step in steps:
        with console.status(f"Writing {label} ..."):
            step()
        console.print(f"[green]done[/] {label}")
    summary(console)


if __name__ == "__main__":
    main()
