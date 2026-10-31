"""Central settings for all Danubia scripts.

Settings come from environment variables. For local work, values in the project's .env file are
loaded automatically (real environment variables win). Nothing secret is hard-coded here.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL, Engine, create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments. Does not override existing variables."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def setting(name: str, default: str | None = None) -> str:
    """Return a setting, or fail with a clear message if it is missing."""
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing setting {name!r}. Add it to .env (see .env.example).")
    return value


def onprem_engine(database: str = "DanubiaERP") -> Engine:
    """SQLAlchemy engine for the simulated on-prem SQL Server running in Docker."""
    url = URL.create(
        "mssql+pyodbc",
        username="sa",
        password=setting("SA_PASSWORD"),  # URL.create escapes special characters safely
        host="localhost",
        port=1433,
        database=database,
        query={
            "driver": setting("ODBC_DRIVER", "ODBC Driver 18 for SQL Server"),
            "TrustServerCertificate": "yes",  # local container uses a self-signed certificate
        },
    )
    # fast_executemany sends rows to SQL Server in batches instead of one by one
    return create_engine(url, fast_executemany=True)
