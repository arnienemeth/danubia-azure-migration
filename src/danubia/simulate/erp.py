"""Generate Danubia's on-prem ERP database: a schema with keys, then realistic fake data.

Run:   uv run python -m danubia.simulate.erp
Re-running drops and recreates everything. A fixed random seed and a fixed "today" mean
every run produces exactly the same data, so results are reproducible.
"""

from __future__ import annotations

import random
import unicodedata
from datetime import date, timedelta

import polars as pl
from faker import Faker
from rich.console import Console
from rich.table import Table
from sqlalchemy import Engine, text

from danubia.config import onprem_engine

SEED = 42
TODAY = date(2026, 10, 31)
YEARS_OF_HISTORY = 3
N_CUSTOMERS, N_PRODUCTS, N_ORDERS = 400, 300, 20_000
VAT_RATE = 0.20

# department -> (cost centre, headcount, typical job titles)
DEPARTMENTS: dict[str, tuple[str, int, list[str]]] = {
    "Production": ("CC-100", 120, ["Machine Operator", "Shift Leader", "Toolmaker", "Production Planner"]),
    "Warehouse": ("CC-200", 35, ["Warehouse Operative", "Forklift Driver", "Logistics Coordinator"]),
    "Sales": ("CC-300", 25, ["Account Manager", "Sales Assistant", "Customer Service Agent"]),
    "Finance": ("CC-400", 15, ["Accountant", "Accounts Payable Clerk", "Controller"]),
    "Quality": ("CC-500", 15, ["Quality Inspector", "Quality Engineer"]),
    "HR": ("CC-600", 8, ["HR Generalist", "Payroll Specialist"]),
    "IT": ("CC-700", 4, ["System Administrator", "IT Support"]),
    "Management": ("CC-800", 28, ["Department Manager", "Team Lead", "Executive Assistant"]),
}

# One Faker per locale, so names, cities and companies match the country
FAKERS = {"SK": Faker("sk_SK"), "HU": Faker("hu_HU"), "AT": Faker("de_AT"), "DE": Faker("de_DE")}

SCHEMA = [
    # drop in reverse dependency order so re-runs work
    "DROP TABLE IF EXISTS dbo.invoices",
    "DROP TABLE IF EXISTS dbo.orders",
    "DROP TABLE IF EXISTS dbo.products",
    "DROP TABLE IF EXISTS dbo.customers",
    "DROP TABLE IF EXISTS dbo.employees",
    "DROP TABLE IF EXISTS dbo.departments",
    """CREATE TABLE dbo.departments (
        department_id INT PRIMARY KEY,
        name          NVARCHAR(50) NOT NULL UNIQUE,
        cost_center   VARCHAR(10)  NOT NULL,
        headcount     INT          NOT NULL)""",
    """CREATE TABLE dbo.employees (
        employee_id        INT PRIMARY KEY,
        first_name         NVARCHAR(60)  NOT NULL,
        last_name          NVARCHAR(60)  NOT NULL,
        email              VARCHAR(120)  NOT NULL UNIQUE,
        department_id      INT           NOT NULL REFERENCES dbo.departments(department_id),
        job_title          NVARCHAR(80)  NOT NULL,
        country            CHAR(2)       NOT NULL,
        birth_number       VARCHAR(11)   NOT NULL,   -- personal ID: GDPR-sensitive
        iban               VARCHAR(34)   NOT NULL,   -- bank account: GDPR-sensitive
        monthly_salary_eur DECIMAL(9,2)  NOT NULL,   -- confidential
        hired_on           DATE          NOT NULL,
        is_active          BIT           NOT NULL)""",
    """CREATE TABLE dbo.customers (
        customer_id      INT PRIMARY KEY,
        name             NVARCHAR(120) NOT NULL,
        country          CHAR(2)       NOT NULL,
        city             NVARCHAR(80)  NOT NULL,
        vat_id           VARCHAR(20)   NOT NULL,
        contact_name     NVARCHAR(120) NOT NULL,
        contact_email    VARCHAR(120)  NOT NULL,
        credit_limit_eur DECIMAL(12,2) NOT NULL)""",
    """CREATE TABLE dbo.products (
        product_id     INT PRIMARY KEY,
        sku            VARCHAR(20)   NOT NULL UNIQUE,
        name           NVARCHAR(80)  NOT NULL,
        category       NVARCHAR(40)  NOT NULL,
        material       NVARCHAR(20)  NOT NULL,
        unit_price_eur DECIMAL(10,2) NOT NULL,
        unit_cost_eur  DECIMAL(10,2) NOT NULL)""",
    """CREATE TABLE dbo.orders (
        order_id       INT PRIMARY KEY,
        customer_id    INT           NOT NULL REFERENCES dbo.customers(customer_id),
        product_id     INT           NOT NULL REFERENCES dbo.products(product_id),
        sales_rep_id   INT           NOT NULL REFERENCES dbo.employees(employee_id),
        quantity       INT           NOT NULL,
        unit_price_eur DECIMAL(10,2) NOT NULL,
        order_date     DATE          NOT NULL,
        ship_date      DATE          NULL,
        status         VARCHAR(10)   NOT NULL)""",
    "CREATE INDEX ix_orders_customer ON dbo.orders(customer_id)",
    "CREATE INDEX ix_orders_order_date ON dbo.orders(order_date)",
    """CREATE TABLE dbo.invoices (
        invoice_id   INT PRIMARY KEY,
        invoice_no   VARCHAR(20)   NOT NULL UNIQUE,
        order_id     INT           NOT NULL UNIQUE REFERENCES dbo.orders(order_id),
        invoice_date DATE          NOT NULL,
        due_date     DATE          NOT NULL,
        amount_eur   DECIMAL(12,2) NOT NULL,
        vat_eur      DECIMAL(12,2) NOT NULL,
        paid_date    DATE          NULL)""",
]


def ascii_slug(value: str) -> str:
    """'Ľubomír Ďurček' -> 'lubomir.durcek' style text for email addresses."""
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return "".join(ch for ch in plain.lower() if ch.isalnum() or ch == ".")


def slovak_birth_number(birthday: date, female: bool) -> str:
    """Fake Slovak birth number (rodné číslo) in YYMMDD/XXXX form; women get +50 on the month."""
    month = birthday.month + (50 if female else 0)
    return f"{birthday:%y}{month:02d}{birthday:%d}/{random.randint(0, 9999):04d}"


def build_departments() -> pl.DataFrame:
    return pl.DataFrame(
        [
            {"department_id": i, "name": name, "cost_center": cc, "headcount": n}
            for i, (name, (cc, n, _)) in enumerate(DEPARTMENTS.items(), start=1)
        ]
    )


def build_employees() -> pl.DataFrame:
    rows, used_emails, employee_id = [], set(), 1
    for dept_id, (dept, (_, headcount, titles)) in enumerate(DEPARTMENTS.items(), start=1):
        for _ in range(headcount):
            country = "SK" if random.random() < 0.85 else "HU"
            fake = FAKERS[country]
            female = random.random() < 0.4
            first = fake.first_name_female() if female else fake.first_name_male()
            # Slovak surnames have male and female forms (Novák / Nováková)
            gendered = "last_name_female" if female else "last_name_male"
            last = getattr(fake, gendered)() if hasattr(fake, gendered) else fake.last_name()
            email = f"{ascii_slug(first)}.{ascii_slug(last)}@danubia.example"
            if email in used_emails:
                email = email.replace("@", f"{employee_id}@")
            used_emails.add(email)
            birthday = fake.date_of_birth(minimum_age=19, maximum_age=64)
            hired = fake.date_between(start_date=TODAY - timedelta(days=15 * 365), end_date=TODAY)
            rows.append(
                {
                    "employee_id": employee_id,
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "department_id": dept_id,
                    "job_title": random.choice(titles),
                    "country": country,
                    "birth_number": slovak_birth_number(birthday, female),
                    "iban": FAKERS["SK"].iban(),
                    "monthly_salary_eur": float(random.randint(1100, 4800)),
                    "hired_on": hired,
                    "is_active": random.random() > 0.04,  # a few leavers, useful in Project 2
                }
            )
            employee_id += 1
    return pl.DataFrame(rows)


def build_customers() -> pl.DataFrame:
    countries, weights = ["SK", "HU", "AT", "DE"], [35, 20, 20, 25]
    rows = []
    for customer_id in range(1, N_CUSTOMERS + 1):
        country = random.choices(countries, weights)[0]
        fake = FAKERS[country]
        rows.append(
            {
                "customer_id": customer_id,
                "name": fake.company(),
                "country": country,
                "city": fake.city(),
                "vat_id": f"{country}{random.randint(10**9, 10**10 - 1)}",
                "contact_name": fake.name(),
                "contact_email": fake.company_email(),
                "credit_limit_eur": float(random.choice([10_000, 25_000, 50_000, 100_000, 250_000])),
            }
        )
    return pl.DataFrame(rows)


def build_products() -> pl.DataFrame:
    categories = {
        "Brackets": "Steel", "Housings": "Aluminium", "Clips": "Plastic",
        "Flanges": "Steel", "Covers": "Plastic", "Shafts": "Steel", "Seals": "Rubber",
    }
    rows = []
    for product_id in range(1, N_PRODUCTS + 1):
        category, material = random.choice(list(categories.items()))
        price = round(random.uniform(0.40, 85.0), 2)
        rows.append(
            {
                "product_id": product_id,
                "sku": f"DC-{product_id:04d}-{material[:2].upper()}",
                "name": f"{category[:-1]} {random.choice(['A', 'B', 'C', 'X', 'S'])}{random.randint(10, 99)}",
                "category": category,
                "material": material,
                "unit_price_eur": price,
                "unit_cost_eur": round(price * random.uniform(0.55, 0.80), 2),
            }
        )
    return pl.DataFrame(rows)


def build_orders_and_invoices(
    products: pl.DataFrame, employees: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    prices = dict(zip(products["product_id"], products["unit_price_eur"]))
    sales_reps = employees.filter(pl.col("department_id") == 3)["employee_id"].to_list()
    start = TODAY - timedelta(days=YEARS_OF_HISTORY * 365)
    orders, invoices, seq_per_year = [], [], {}

    for order_id in range(1, N_ORDERS + 1):
        product_id = random.randint(1, N_PRODUCTS)
        order_date = start + timedelta(days=random.randint(0, YEARS_OF_HISTORY * 365))
        age = (TODAY - order_date).days
        # older orders are further along the lifecycle, like in a real ERP
        if age > 60:
            status = "paid" if random.random() < 0.92 else "invoiced"
        elif age > 14:
            status = random.choice(["shipped", "invoiced", "paid"])
        else:
            status = random.choice(["open", "open", "shipped"])
        ship_date = None if status == "open" else min(order_date + timedelta(days=random.randint(2, 10)), TODAY)
        quantity = random.randint(50, 5000)
        unit_price = round(prices[product_id] * random.uniform(0.95, 1.05), 2)

        orders.append(
            {
                "order_id": order_id,
                "customer_id": random.randint(1, N_CUSTOMERS),
                "product_id": product_id,
                "sales_rep_id": random.choice(sales_reps),
                "quantity": quantity,
                "unit_price_eur": unit_price,
                "order_date": order_date,
                "ship_date": ship_date,
                "status": status,
            }
        )

        if status in ("invoiced", "paid"):
            year = ship_date.year
            seq_per_year[year] = seq_per_year.get(year, 0) + 1
            amount = round(quantity * unit_price, 2)
            paid = min(ship_date + timedelta(days=random.randint(10, 60)), TODAY) if status == "paid" else None
            invoices.append(
                {
                    "invoice_id": len(invoices) + 1,
                    "invoice_no": f"INV-{year}-{seq_per_year[year]:05d}",
                    "order_id": order_id,
                    "invoice_date": ship_date,
                    "due_date": ship_date + timedelta(days=30),
                    "amount_eur": amount,
                    "vat_eur": round(amount * VAT_RATE, 2),
                    "paid_date": paid,
                }
            )
    return pl.DataFrame(orders), pl.DataFrame(invoices)


def create_schema(engine: Engine) -> None:
    with engine.begin() as conn:  # one transaction: all tables or none
        for statement in SCHEMA:
            conn.execute(text(statement))


def load(engine: Engine, tables: dict[str, pl.DataFrame]) -> None:
    for name, df in tables.items():  # dict order = dependency order (parents first)
        df.to_pandas().to_sql(name, engine, schema="dbo", if_exists="append", index=False, chunksize=2000)


def summary(engine: Engine, console: Console) -> None:
    report = Table(title="DanubiaERP on the simulated on-prem server")
    report.add_column("Table")
    report.add_column("Rows", justify="right")
    with engine.connect() as conn:
        for name in ["departments", "employees", "customers", "products", "orders", "invoices"]:
            rows = conn.execute(text(f"SELECT COUNT(*) FROM dbo.{name}")).scalar_one()
            report.add_row(name, f"{rows:,}")
        revenue = conn.execute(
            text("SELECT YEAR(invoice_date), SUM(amount_eur) FROM dbo.invoices GROUP BY YEAR(invoice_date) ORDER BY 1")
        ).all()
    console.print(report)
    for year, total in revenue:
        console.print(f"Invoiced revenue {year}: EUR {total:,.0f}")


def main() -> None:
    console = Console()
    random.seed(SEED)
    Faker.seed(SEED)

    with console.status("Generating data ..."):
        departments = build_departments()
        employees = build_employees()
        customers = build_customers()
        products = build_products()
        orders, invoices = build_orders_and_invoices(products, employees)

    engine = onprem_engine()
    with console.status("Creating schema and loading SQL Server ..."):
        create_schema(engine)
        load(engine, {
            "departments": departments, "employees": employees, "customers": customers,
            "products": products, "orders": orders, "invoices": invoices,
        })
    summary(engine, console)


if __name__ == "__main__":
    main()
