"""
Reads three Trip.com markdown text files and appends today's price snapshot
to flight_prices.csv. For each (destination, metric) we record up to TWO rows:

    category = priority  → cheapest fare on Singapore Airlines or Scoot
    category = reference → cheapest fare across ALL airlines on the page

If a category has no matching deal that day, that row is simply omitted.
The headline ("priority") is the one we recommend the user track; "reference"
is for context — what other carriers are offering.

Metrics:
    one_way_june    = cheapest June 2026 one-way fare
                      (from Trip.com's "Month: From S$ X" monthly summary)
    round_trip_june = cheapest June-departing round-trip with 3-5 night stay.
                      Within priority (SIA/Scoot) we fall back to any-month
                      SIA/Scoot RT if no June 3-5n match is visible; reference
                      always pulls the cheapest visible all-airline match
                      (June 3-5n preferred, any-RT otherwise).

Usage:
    python update_csv.py <bkk.md> <hkt.md> <tpe.md>

CSV columns:
    snapshot_date,dest,metric,category,price_sgd,
    dep_date,ret_date,airline_out,airline_in,note
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
    "snapshot_date", "dest", "metric", "category", "price_sgd",
    "dep_date", "ret_date", "airline_out", "airline_in", "note",
]


def ensure_header(path: str) -> None:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(HEADER)


def append_row(path: str, row: dict) -> None:
    with open(path, "a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow([row.get(k, "") for k in HEADER])


def _one_way_row(date_str: str, dest: str, best: dict, category: str) -> dict:
    return {
        "snapshot_date": date_str, "dest": dest, "metric": "one_way_june",
        "category": category,
        "price_sgd": best["price_sgd"],
        "dep_date": best.get("dep_date") or "",
        "ret_date": "",
        "airline_out": best["airline"],
        "airline_in": "",
        "note": "sia_scoot" if category == "priority" else "any_airline",
    }


def _rt_row(date_str: str, dest: str, best: dict, category: str, note: str) -> dict:
    return {
        "snapshot_date": date_str, "dest": dest, "metric": "round_trip_june",
        "category": category,
        "price_sgd": best["price_sgd"],
        "dep_date": best["dep_date"],
        "ret_date": best["ret_date"],
        "airline_out": best["airline_out"],
        "airline_in": best["airline_in"],
        "note": note,
    }


def rows_for_route(date_str: str, dest: str, summary: dict) -> list[dict]:
    out: list[dict] = []

    # --- One-way June ---
    pri_ow = summary["cheapest_one_way_june_sia_scoot"]
    if pri_ow:
        out.append(_one_way_row(date_str, dest, pri_ow, "priority"))
    ref_ow = summary["cheapest_one_way_june_any"]
    # Only emit reference if it actually differs from priority (avoids dup rows)
    if ref_ow and (not pri_ow or ref_ow["airline"] != pri_ow["airline"] or ref_ow["price_sgd"] != pri_ow["price_sgd"]):
        out.append(_one_way_row(date_str, dest, ref_ow, "reference"))

    # --- Round-trip June ---
    pri_rt = summary["cheapest_rt_june_3to5n_sia_scoot"]
    pri_note = "june_3to5n_sia_scoot"
    if not pri_rt:
        pri_rt = summary["cheapest_rt_any_sia_scoot"]
        pri_note = "fallback_any_month_sia_scoot"
    if pri_rt:
        out.append(_rt_row(date_str, dest, pri_rt, "priority", pri_note))

    ref_rt = summary["cheapest_rt_june_3to5n_any"]
    ref_note = "june_3to5n_any_airline"
    if not ref_rt:
        ref_rt = summary["cheapest_rt_any_any"]
        ref_note = "fallback_any_airline"
    if ref_rt and (not pri_rt or _rt_key(ref_rt) != _rt_key(pri_rt)):
        out.append(_rt_row(date_str, dest, ref_rt, "reference", ref_note))

    return out


def _rt_key(d: dict) -> tuple:
    return (d["dep_date"], d["ret_date"], d["airline_out"], d["airline_in"], d["price_sgd"])


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
            print(f"# skip {code}: file too small ({len(text)} bytes)", file=sys.stderr)
            continue
        summary = summarize(text, code)
        for row in rows_for_route(today, code, summary):
            append_row(CSV_PATH, row)
            summary_out.append(row)
    print(json.dumps(summary_out, indent=2))


if __name__ == "__main__":
    main()
