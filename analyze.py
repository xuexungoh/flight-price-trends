"""
Reads flight_prices.csv and computes plain trend statistics per
(dest, metric, category). Two categories are tracked side-by-side:

    priority  = SIA + Scoot (the carriers the user prefers)
    reference = best of all airlines on the page (context)

Output JSON shape:
    {
      "BKK": {
        "one_way_june":   { "priority": {...}, "reference": {...} },
        "round_trip_june":{ "priority": {...}, "reference": {...} }
      }, ...
    }

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
CATEGORIES = ("priority", "reference")


def _load() -> list[dict]:
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _pct(a, b):
    if b in (None, 0):
        return None
    return round((a - b) / b * 100, 1)


def _trend(values: list[int]) -> str:
    if len(values) < 2:
        return "flat"
    first, last = values[0], values[-1]
    if last < first * 0.97: return "down"
    if last > first * 1.03: return "up"
    return "flat"


def compute_stats(rows: list[dict]) -> dict:
    """Group by (dest, metric, category), sort chronologically, build stats."""
    grouped: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for r in rows:
        cat = r.get("category") or "priority"  # legacy rows treated as priority
        grouped[(r["dest"], r["metric"], cat)].append(r)

    out: dict = {}
    for (dest, metric, cat), series in grouped.items():
        series.sort(key=lambda x: x["snapshot_date"])
        prices = [int(x["price_sgd"]) for x in series]
        latest = series[-1]
        recent7 = prices[-7:]
        lowest_idx = min(range(len(prices)), key=lambda i: prices[i])
        stats = {
            "latest_price": prices[-1],
            "latest_date": latest["snapshot_date"],
            "latest_meta": {k: latest.get(k, "") for k in (
                "dep_date", "ret_date", "airline_out", "airline_in", "note"
            )},
            "prior_price": prices[-2] if len(prices) >= 2 else None,
            "delta_day_pct": _pct(prices[-1], prices[-2]) if len(prices) >= 2 else None,
            "avg_7d": round(mean(recent7), 0) if recent7 else None,
            "delta_vs_7d_pct": _pct(prices[-1], mean(recent7)) if recent7 else None,
            "lowest_so_far": min(prices),
            "lowest_date": series[lowest_idx]["snapshot_date"],
            "snapshots": len(series),
            "trend_recent": _trend(prices[-5:]),
        }
        out.setdefault(dest, {}).setdefault(metric, {})[cat] = stats
    return out


def _fmt_pct(p) -> str:
    if p is None: return "—"
    sign = "+" if p > 0 else ""
    return f"{sign}{p}%"


def as_text(stats: dict) -> str:
    lines = ["Flight price snapshot —", ""]
    for dest in ("BKK", "HKT", "TPE"):
        d = stats.get(dest, {})
        if not d:
            lines.append(f"  {DEST_LABEL[dest]} ({dest}): no data yet")
            lines.append("")
            continue
        lines.append(f"  {DEST_LABEL[dest]} ({dest})")
        for metric_label, metric_key in (("One-way June", "one_way_june"),
                                         ("Round-trip June (3-5n)", "round_trip_june")):
            entries = d.get(metric_key, {})
            pri = entries.get("priority")
            ref = entries.get("reference")
            if not pri and not ref:
                lines.append(f"    {metric_label}: no data")
                continue
            if pri:
                lines.append(f"    {metric_label}  [SIA/Scoot]: " + _format_row(pri))
            else:
                lines.append(f"    {metric_label}  [SIA/Scoot]: not currently published")
            if ref:
                lines.append(f"    {metric_label}  [Any airline]: " + _format_row(ref))
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_row(s: dict) -> str:
    m = s["latest_meta"]
    who = m["airline_out"]
    if m["airline_in"] and m["airline_in"] != m["airline_out"]:
        who = f"{m['airline_out']} / {m['airline_in']}"
    dates = m["dep_date"]
    if m["ret_date"]:
        dates = f"{m['dep_date']} → {m['ret_date']}"
    day = f"(vs yesterday {_fmt_pct(s['delta_day_pct'])})" if s["snapshots"] >= 2 else "(first snapshot)"
    return f"S${s['latest_price']} — {who}, {dates} {day}. Lowest seen: S${s['lowest_so_far']} on {s['lowest_date']}."


def main():
    rows = _load()
    stats = compute_stats(rows)
    if "--text" in sys.argv:
        print(as_text(stats))
    else:
        print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
