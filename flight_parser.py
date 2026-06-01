"""
Parses Trip.com flight page markdown text and extracts:

  1. cheapest_one_way_june   - lowest "Month: From S$ X with {airline}, departing on {date}"
                               entry for June with SIA/Scoot.
  2. cheapest_round_trip_june - lowest round-trip card with both legs on SIA/Scoot,
                               departure in June and return 3-5 days later.
  3. headline_round_trip     - the "Round-Trip Flight Deals: From S$ X with {airline}..."
                               line at the top of the page (any month/airline).

Usage from CLI:
    python flight_parser.py BKK < trip_bkk.md
"""
import json
import re
import sys
from datetime import datetime, date
from typing import Optional

DEST_CITY = {"BKK": "Bangkok", "HKT": "Phuket", "TPE": "Taipei"}
ALLOWED_AIRLINES = {"Scoot", "Singapore Airlines"}
CURRENT_YEAR = 2026
TARGET_MONTH = 6


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def parse_monthly_one_way(text: str) -> list[dict]:
    """Extract 'June: From S$ 175 with Scoot, departing on Tue, Jun 2.' lines."""
    flat = _norm(text)
    pat = re.compile(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r":\s*From\s*S\$\s*(\d+)\s*with\s*([A-Za-z][A-Za-z &]+?),"
        r"\s*departing on\s*(?:\w+,\s*)?([A-Za-z]+\s*\d+)(?:,\s*\d{4})?\."
    )
    out = []
    for m in pat.finditer(flat):
        month_name, price, airline, dep_str = m.groups()
        out.append({
            "month": month_name,
            "price_sgd": int(price),
            "airline": airline.strip(),
            "dep_date": _parse_date(dep_str),
        })
    return out


def parse_headline_round_trip(text: str) -> Optional[dict]:
    """Extract the 'Round-Trip Flight Deals\nGrab round-trip flights from just S$ X with Y, ..."""
    flat = _norm(text)
    pat = re.compile(
        r"Round-Trip Flight Deals\s*Grab round-trip flights from just S\$\s*(\d+)\s*with\s*"
        r"([A-Za-z][A-Za-z &]+?),\s*a Direct flight departing on\s*(?:\w+,\s*)?([A-Za-z]+\s*\d+)"
        r"\s*and returning on\s*(?:\w+,\s*)?([A-Za-z]+\s*\d+)"
    )
    m = pat.search(flat)
    if not m:
        return None
    return {
        "price_sgd": int(m.group(1)),
        "airline": m.group(2).strip(),
        "dep_date": _parse_date(m.group(3)),
        "ret_date": _parse_date(m.group(4)),
    }


def parse_round_trips(text: str, dest_code: str) -> list[dict]:
    """Extract every round-trip card (outbound + return + price)."""
    city = DEST_CITY[dest_code]
    flat = _norm(text)
    # leg_re finds "{Origin} - {Dest} | {Day, Mon DD} | {Airline}"
    leg_re = re.compile(
        r"(Singapore\s*-\s*" + city + r"|" + city + r"\s*-\s*Singapore)"
        r"\s*\|\s*\w+,\s*([A-Za-z]+\s*\d+)\s*\|\s*([A-Za-z][A-Za-z &]+?)\s*"
        r"(?=S\$|Singapore|" + city + r"|Find more)"
    )
    price_re = re.compile(r"S\$\s*(\d+)")
    deals: list[dict] = []
    pos = 0
    while True:
        m_out = leg_re.search(flat, pos)
        if not m_out:
            break
        if m_out.group(1).startswith(city):
            pos = m_out.end()
            continue
        m_in = leg_re.search(flat, m_out.end())
        if not m_in:
            break
        if not m_in.group(1).startswith(city):
            pos = m_out.end()
            continue
        window = flat[m_in.end(): m_in.end() + 400]
        m_price = price_re.search(window)
        if not m_price:
            pos = m_in.end()
            continue
        deals.append({
            "dep_date": _parse_date(m_out.group(2)),
            "ret_date": _parse_date(m_in.group(2)),
            "airline_out": m_out.group(3).strip(),
            "airline_in": m_in.group(3).strip(),
            "price_sgd": int(m_price.group(1)),
        })
        pos = m_in.end() + m_price.end()
    # de-dup
    seen, unique = set(), []
    for d in deals:
        key = (d["dep_date"], d["ret_date"], d["airline_out"], d["airline_in"], d["price_sgd"])
        if key not in seen:
            seen.add(key); unique.append(d)
    return unique


def _parse_date(s: str) -> Optional[str]:
    """'Jun 24' -> '2026-06-24'."""
    s = (s or "").strip()
    for fmt in ("%b %d", "%B %d"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d.replace(year=CURRENT_YEAR).isoformat()
        except ValueError:
            continue
    return None


def best_one_way_june_sia_scoot(monthly: list[dict]) -> Optional[dict]:
    """Pick the cheapest June entry from monthly_one_way list with SIA/Scoot."""
    best = None
    for m in monthly:
        if m["month"] != "June":
            continue
        if m["airline"] not in ALLOWED_AIRLINES:
            continue
        if best is None or m["price_sgd"] < best["price_sgd"]:
            best = m
    return best


def best_one_way_june_any(monthly: list[dict]) -> Optional[dict]:
    """Cheapest June entry regardless of airline (fallback)."""
    best = None
    for m in monthly:
        if m["month"] != "June":
            continue
        if best is None or m["price_sgd"] < best["price_sgd"]:
            best = m
    return best


def best_round_trip_june_3to5n(deals: list[dict]) -> Optional[dict]:
    best = None
    for d in deals:
        if not d["dep_date"] or not d["ret_date"]:
            continue
        if d["airline_out"] not in ALLOWED_AIRLINES or d["airline_in"] not in ALLOWED_AIRLINES:
            continue
        dep = date.fromisoformat(d["dep_date"])
        ret = date.fromisoformat(d["ret_date"])
        if dep.month != TARGET_MONTH:
            continue
        stay = (ret - dep).days
        if not (3 <= stay <= 5):
            continue
        if best is None or d["price_sgd"] < best["price_sgd"]:
            best = d
    return best


def best_round_trip_relaxed(deals: list[dict]) -> Optional[dict]:
    best = None
    for d in deals:
        if d["airline_out"] not in ALLOWED_AIRLINES or d["airline_in"] not in ALLOWED_AIRLINES:
            continue
        if best is None or d["price_sgd"] < best["price_sgd"]:
            best = d
    return best


def summarize(text: str, dest_code: str) -> dict:
    monthly = parse_monthly_one_way(text)
    headline_rt = parse_headline_round_trip(text)
    deals = parse_round_trips(text, dest_code)
    return {
        "monthly_one_way": monthly,
        "headline_round_trip": headline_rt,
        "round_trip_deals": deals,
        "cheapest_one_way_june_sia_scoot": best_one_way_june_sia_scoot(monthly),
        "cheapest_one_way_june_any": best_one_way_june_any(monthly),
        "cheapest_rt_june_3to5n_sia_scoot": best_round_trip_june_3to5n(deals),
        "cheapest_rt_any_sia_scoot": best_round_trip_relaxed(deals),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in DEST_CITY:
        print("usage: python flight_parser.py {BKK|HKT|TPE} < page.md", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(summarize(sys.stdin.read(), sys.argv[1]), indent=2))
