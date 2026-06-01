"""
Reads three Trip.com markdown text files and appends today's price snapshot
to flight_prices.csv. STRICT FILTER — only Singapore Airlines and Scoot fares
are recorded. If neither carrier shows a matching fare for a route on a given
day, the row is simply omitted (no fallback to other carriers).

Metrics per destination per day:

    one_way_june    = cheapest June 2026 one-way fare on SIA/Scoot
                      (from Trip.com's "Month: From S$ X" monthly summary)
    round_trip_june = cheapest SIA/Scoot round-trip card, June departure,
                      return 3-5 days later. Fallback within SIA/Scoot only:
                      relaxes the month + stay-length filter, never the airline.

Usage:
    python update_csv.py <bkk.md> <hkt.md> <tpe.md>

CSV columns:
    snapshot_date,dest,metric,price_sgd,dep_date,ret_date,airline_out,airline_in,note
"""
import csv
import json
import os
import sys
from datetime import datetime, timezone

from flight_parser import summarize

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(ROOT, "flight_prices.csv")
ROUTES = [("BKK", "Bangkok"), ("HKT", "Phuket"), ("TPE", "Taipei")]

HEADER = [
    "snapshot_date", "dest", "metric", "price_sgd",
    "dep_date", "ret_date", "airline_out", "airline_in", "note",
]


def ensure_header(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(HEADER)


def append_row(path: str, row: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([row.get(k, "") for k in HEADER])


def build_one_way_row(date_str: str, dest: str, summary: dict) -> dict | None:
    """SIA/Scoot only, June only. No fallback to other carriers."""
    best = summary["cheapest_one_way_june_sia_scoot"]
    if not best:
        return None
    return {
        "snapshot_date": date_str, "dest": dest, "metric": "one_way_june",
        "price_sgd": best["price_sgd"],
        "dep_date": best.get("dep_date") or "",
        "ret_date": "",
        "airline_out": best["airline"],
        "airline_in": "",
        "note": "sia_scoot",
    }


def build_round_trip_row(date_str: str, dest: str, summary: dict) -> dict | None:
    """SIA/Scoot only. Prefer June 3-5 night; fallback to any SIA/Scoot RT
    (still strictly SIA/Scoot — never other carriers)."""
    best = summary["cheapest_rt_june_3to5n_sia_scoot"]
    note = "june_3to5n_sia_scoot"
    if not best:
        best = summary["cheapest_rt_any_sia_scoot"]
        note = "fallback_any_month_sia_scoot"
    if not best:
        return None
    return {
        "snapshot_date": date_str, "dest": dest, "metric": "round_trip_june",
        "price_sgd": best["price_sgd"],
        "dep_date": best["dep_date"],
        "ret_date": best["ret_date"],
        "airline_out": best["airline_out"],
        "airline_in": best["airline_in"],
        "note": note,
    }


def main() -> None:
    if len(sys.argv) != 4:
        print("usage: python update_csv.py <bkk.md> <hkt.md> <tpe.md>", file=sys.stderr)
        sys.exit(1)
    paths = {"BKK": sys.argv[1], "HKT": sys.argv[2], "TPE": sys.argv[3]}
    ensure_header(CSV_PATH)
    today = datetime.now(timezone.utc).date().isoformat()
    summary_out = []
    for code, _city in ROUTES:
        path = paths[code]
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except (FileNotFoundError, IsADirectoryError):
            print(f"# skip {code}: file not found {path}", file=sys.stderr)
            continue
        if len(text) < 1000:
            print(f"# skip {code}: file too small ({len(text)} bytes) — likely failed fetch", file=sys.stderr)
            continue
        summary = summarize(text, code)
        for builder in (build_one_way_row, build_round_trip_row):
            row = builder(today, code, summary)
            if row:
                append_row(CSV_PATH, row)
                summary_out.append(row)
    print(json.dumps(summary_out, indent=2))


if __name__ == "__main__":
    main()
