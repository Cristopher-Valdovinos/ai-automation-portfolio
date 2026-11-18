"""Weekly pipeline: one command that updates data and writes the report.

Steps:
  1. Download any missing month since HISTORY_START, and re-download the
     previous and current month (they keep growing until the month closes).
  2. Estimate contract end dates with the rules.
  3. If Ollama is running, read durations of new large contracts with the
     LLM and estimate again. If not, the step is skipped (the report still
     works, with rules only).
  4. Write the prospect report for today.

Usage:
    python src/run_weekly.py
    python src/run_weekly.py --date 2026-11-17   # report as of another day

Meant to be scheduled once a week (see scripts/schedule_weekly.ps1).
"""

import argparse
import time
from datetime import date

import pandas as pd

import estimate_contracts
import extract_durations
import fetch_orders
import weekly_report

HISTORY_START = "2024-01"


def months_to_refresh(today: pd.Timestamp) -> set[tuple[int, int]]:
    """The current and previous month: their files are still incomplete."""
    current = today.to_period("M")
    return {(p.year, p.month) for p in (current - 1, current)}


def update_data(today: pd.Timestamp) -> None:
    refresh = months_to_refresh(today)
    for year, month in fetch_orders.month_range(HISTORY_START, f"{today:%Y-%m}"):
        fetch_orders.process_month(year, month, refresh=(year, month) in refresh)


def run(today: pd.Timestamp) -> None:
    start = time.time()
    print(f"== Weekly run for {today:%Y-%m-%d} ==")

    print("\n[1/4] Updating data")
    update_data(today)

    print("\n[2/4] Estimating contracts")
    estimate_contracts.main()

    print("\n[3/4] Reading durations with the LLM")
    if extract_durations.ollama_available():
        extract_durations.run()
        estimate_contracts.main()
    else:
        print("Ollama is not running: skipped (report uses rules only)")

    print("\n[4/4] Writing report")
    report = weekly_report.run(today)

    print(f"\nDone in {time.time() - start:.0f}s -> {report}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=str(date.today()), help="report date, YYYY-MM-DD")
    args = parser.parse_args()
    run(pd.Timestamp(args.date))


if __name__ == "__main__":
    main()
