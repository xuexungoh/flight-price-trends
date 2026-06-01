"""
Reads flight_prices.csv and computes plain trend statistics per (dest, metric):
  today, prior_day, delta_day, avg_7d, delta_vs_7d, lowest_so_far, lowest_date,
  trend_direction (over the last up-to-5 snapshots: 'down' / 'flat' / 'up').

Prints a JSON object: {"BKK": {"one_way_june": {...}, ...}, ...}
Also writes a human-readable summary to stdout when --text is passed.

Used by build_artifact.py and the scheduled task email step.
"""
import csv
import json
import os
import sys
from collections import defaultdict
from statistics import mean

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(ROOT, "flight_prices.csv")
DEST_LABEL = {"BKK": "Bangkok", "HKT": "Phuket", "TPE": "Taipei"}


def _load() -> list[dict]:
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _pct(a: float, b: float) -> float | None:
    if b is None or b == 0:
        return None
    return round((a - b) / b * 100, 1)


def _trend(values: list[int]) -> str:
    """Direction over the last few prices: down / flat / up."""
    if len(values) < 2:
        return "flat"
    first, last = values[0], values[-1]
    if last < first * 0.97:
        return "down"
    if last > first * 1.03:
        return "up"
    return "flat"


def compute_stats(rows: list[dict]) -> dict:
    """Group rows by (dest, metric), sort by date, compute stats."""
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        grouped[(r["dest"], r["metric"])].append(r)

    out: dict[str, dict[str, dict]] = {}
    for (dest, metric), series in grouped.items():
        series.sort(key=lambda x: x["snapshot_date"])
        prices = [int(x["price_sgd"]) for x in series]
        latest = series[-1]
        prior = series[-2] if len(series) >= 2 else None
        recent_7 = prices[-7:]
        lowest_idx = min(range(len(prices)), key=lambda i: prices[i])

        stats = {
            "latest_price": prices[-1],
            "latest_date": latest["snapshot_date"],
            "latest_meta": {k: latest.get(k, "") for k in (
                "dep_date", "ret_date", "airline_out", "airline_in", "note"
            )},
            "prior_price": prices[-2] if prior else None,
            "delta_day_pct": _pct(prices[-1], prices[-2]) if prior else None,
            "avg_7d": round(mean(recent_7), 0) if recent_7 else None,
            "delta_vs_7d_pct": _pct(prices[-1], mean(recent_7)) if recent_7 else None,
            "lowest_so_far": min(prices),
            "lowest_date": series[lowest_idx]["snapshot_date"],
            "snapshots": len(series),
            "trend_recent": _trend(prices[-5:]),
        }
        out.setdefault(dest, {})[metric] = stats
    return out


def as_text(stats: dict) -> str:
    lines = ["Flight price snapshot —", ""]
    for dest in ("BKK", "HKT", "TPE"):
        d = stats.get(dest, {})
        if not d:
            lines.append(f"  {DEST_LABEL[dest]} ({dest}): no data yet")
            lines.append("")
            continue
        lines.append(f"  {DEST_LABEL[dest]} ({dest})")
        for metric_label, metric_key in (("One-way June", "one_way_june"), ("Round-trip June", "round_trip_june")):
            s = d.get(metric_key)
            if not s:
                lines.append(f"    {metric_label}: no data")
                continue
            m = s["latest_meta"]
            who = m["airline_out"]
            if m["airline_in"] and m["airline_in"] != m["airline_out"]:
                who = f"{m['airline_out']} / {m['airline_in']}"
            dates = m["dep_date"]
            if m["ret_date"]:
                dates = f"{m['dep_date']} → {m['ret_date']}"
            day = (
                f" (yesterday S${s['prior_price']}, {_fmt_pct(s['delta_day_pct'])})"
                if s["prior_price"] is not None else " (first snapshot)"
            )
            avg = (
                f" 7-day avg S${int(s['avg_7d'])}, {_fmt_pct(s['delta_vs_7d_pct'])} vs avg."
                if s["avg_7d"] is not None and s["snapshots"] >= 2 else ""
            )
            low = f" Lowest seen: S${s['lowest_so_far']} on {s['lowest_date']}."
            lines.append(
                f"    {metric_label}: S${s['latest_price']} — {who}, {dates}{day}.{avg}{low} Trend: {s['trend_recent']}."
            )
            if m["note"].startswith("fallback"):
                lines.append(f"      (note: {m['note']})")
        lines.append("")
    return "\n".join(lines).rstrip()


def _fmt_pct(p) -> str:
    if p is None:
        return "n/a"
    sign = "+" if p > 0 else ""
    return f"{sign}{p}%"


def main():
    rows = _load()
    stats = compute_stats(rows)
    if "--text" in sys.argv:
        print(as_text(stats))
    else:
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
