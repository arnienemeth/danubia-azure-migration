"""Generate 30 days of sensor logs for Danubia's 12 production machines.

Run:   uv run python -m danubia.simulate.machines

One CSV per machine per day, one row per minute, as an old machine PC would dump them.
Two hidden problems are planted for Project 8 to discover:
- M07 has a bearing wearing out: vibration creeps up over the last 10 days, then alarms.
- M03 has overheating spikes on some afternoons.
"""

from __future__ import annotations

import shutil
from datetime import date, datetime, timedelta

import numpy as np
import polars as pl
from rich.console import Console

from danubia.config import PROJECT_ROOT

SEED = 11
TODAY = date(2026, 10, 31)
DAYS = 30
ROOT = PROJECT_ROOT / "onprem-sim" / "machine-logs"
MACHINES = {f"M{i:02d}": ("press" if i <= 6 else "cnc" if i <= 10 else "moulding") for i in range(1, 13)}
BASE = {  # normal operating values per machine type
    "press": {"temp": 48, "vib": 2.2, "rpm": 0, "kw": 22},
    "cnc": {"temp": 41, "vib": 1.4, "rpm": 4200, "kw": 15},
    "moulding": {"temp": 210, "vib": 0.8, "rpm": 120, "kw": 35},
}


def day_frame(rng: np.random.Generator, machine: str, kind: str, day: date, day_index: int) -> pl.DataFrame:
    minutes = 24 * 60
    stamps = [datetime.combine(day, datetime.min.time()) + timedelta(minutes=m) for m in range(minutes)]
    hour = np.arange(minutes) // 60
    weekday = day.weekday() < 5
    running = (hour >= 6) & (hour < 22) & weekday  # two shifts, Monday to Friday
    b = BASE[kind]

    temp = np.where(running, b["temp"], 22) + rng.normal(0, 1.2, minutes)
    vib = np.where(running, b["vib"], 0.05) + np.abs(rng.normal(0, 0.15, minutes))
    rpm = np.where(running, b["rpm"], 0) + rng.normal(0, b["rpm"] * 0.01 + 0.1, minutes)
    kw = np.where(running, b["kw"], 0.4) + rng.normal(0, 0.8, minutes)

    if machine == "M07" and day_index >= DAYS - 10:  # bearing wear
        wear = (day_index - (DAYS - 10) + 1) * 0.35
        vib = vib + np.where(running, wear, 0)
    if machine == "M03" and weekday and rng.random() < 0.3:  # afternoon overheating
        spike = (hour >= 14) & (hour < 16)
        temp = temp + np.where(spike & running, rng.uniform(25, 40), 0)

    status = np.where(~running, "IDLE", "RUNNING")
    alarm = running & ((vib > b["vib"] * 2.5) | (temp > b["temp"] + 20))
    status = np.where(alarm, "ALARM", status)

    return pl.DataFrame({
        "timestamp": stamps,
        "machine_id": machine,
        "machine_type": kind,
        "temperature_c": temp.round(1),
        "vibration_mm_s": vib.round(2),
        "spindle_rpm": rpm.clip(0).round(0),
        "power_kw": kw.clip(0).round(1),
        "status": status,
    })


def main() -> None:
    console = Console()
    rng = np.random.default_rng(SEED)
    if ROOT.exists():
        shutil.rmtree(ROOT)
    first_day = TODAY - timedelta(days=DAYS)
    alarms = {}
    with console.status("Writing machine logs ..."):
        for machine, kind in MACHINES.items():
            folder = ROOT / machine
            folder.mkdir(parents=True)
            for i in range(DAYS):
                day = first_day + timedelta(days=i)
                df = day_frame(rng, machine, kind, day, i)
                df.write_csv(folder / f"{machine}_{day:%Y%m%d}.csv")
                alarms[machine] = alarms.get(machine, 0) + df.filter(pl.col("status") == "ALARM").height
    files = sum(1 for _ in ROOT.rglob("*.csv"))
    size = sum(p.stat().st_size for p in ROOT.rglob("*.csv")) / 1_048_576
    console.print(f"[green]done[/] {files} files, {size:,.0f} MB, {files * 1440:,} rows")
    console.print("Alarm minutes per machine: " + ", ".join(f"{m}={n}" for m, n in alarms.items() if n))


if __name__ == "__main__":
    main()
