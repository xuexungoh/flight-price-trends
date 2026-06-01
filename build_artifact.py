"""
Reads flight_prices.csv and writes a self-contained artifact.html that charts
the daily price trend per destination, for both one-way and round-trip metrics.
"""
import csv
import json
import os
from collections import defaultdict

from analyze import compute_stats

ROOT = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(ROOT, "flight_prices.csv")
OUT_PATH = os.path.join(ROOT, "artifact.html")

DEST_LABEL = {"BKK": "Bangkok", "HKT": "Phuket", "TPE": "Taipei"}
COLOR = {"BKK": "#2563eb", "HKT": "#16a34a", "TPE": "#dc2626"}


def load_rows():
    if not os.path.exists(CSV_PATH):
        return []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_payload(rows):
    by_metric_dest = defaultdict(dict)  # (metric, dest) -> {date: row}
    all_dates = set()
    for r in rows:
        all_dates.add(r["snapshot_date"])
        by_metric_dest[(r["metric"], r["dest"])][r["snapshot_date"]] = r
    sorted_dates = sorted(all_dates)
    payload = {"labels": sorted_dates, "metrics": {}}
    for metric in ("one_way_june", "round_trip_june"):
        datasets = []
        for dest in ("BKK", "HKT", "TPE"):
            series = by_metric_dest.get((metric, dest), {})
            datasets.append({
                "label": DEST_LABEL[dest],
                "dest": dest,
                "data": [int(series[d]["price_sgd"]) if d in series else None for d in sorted_dates],
                "borderColor": COLOR[dest],
                "backgroundColor": COLOR[dest] + "33",
                "tension": 0.25,
                "spanGaps": True,
                "pointRadius": 4,
            })
        payload["metrics"][metric] = datasets
    # Latest row per (metric, dest) for cards + table
    latest = {}
    for (metric, dest), series in by_metric_dest.items():
        if series:
            d_max = max(series.keys())
            latest[f"{metric}|{dest}"] = series[d_max]
    payload["latest"] = latest
    payload["rows"] = rows
    payload["stats"] = compute_stats(rows)
    return payload


def build_html(payload):
    pj = json.dumps(payload)
    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SIN flight prices - SIA & Scoot</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.0/dist/chart.umd.js" integrity="sha384-iU8HYtnGQ8Cy4zl7gbNMOhsDTTKX02BTXptVP/vqAWIaTfM7isw76iyZCsjL2eVi" crossorigin="anonymous"></script>
<style>
:root{color-scheme:light}
*{box-sizing:border-box}
body{font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#0f172a;background:transparent;margin:0;padding:16px}
h1{font-size:18px;margin:0 0 4px}
.sub{color:#64748b;font-size:12px;margin-bottom:16px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px;margin-bottom:16px}
.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.dest{padding:12px;border-radius:8px;border:1px solid #e2e8f0}
.dest .name{font-weight:600;font-size:13px;color:#475569}
.dest .price{font-size:26px;font-weight:700;margin:4px 0}
.dest .alt{font-size:13px;color:#475569;margin-top:8px;border-top:1px dashed #e2e8f0;padding-top:6px}
.dest .stats{margin:6px 0 4px;font-size:11.5px;color:#475569;line-height:1.55}
.dest .stats strong{color:#0f172a}
.meta{font-size:11px;color:#64748b}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:middle}
.tabs{display:inline-flex;gap:4px;background:#f1f5f9;padding:3px;border-radius:8px;margin-bottom:12px}
.tab{padding:6px 12px;border:0;background:transparent;border-radius:6px;font-size:12px;cursor:pointer;color:#475569}
.tab.active{background:#fff;color:#0f172a;font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,0.05)}
.chartwrap{position:relative;height:320px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:7px 6px;border-bottom:1px solid #f1f5f9}
th{color:#64748b;font-weight:600}
.empty{color:#64748b;padding:24px;text-align:center}
.tag{display:inline-block;background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:999px;font-size:11px;margin-left:6px}
</style>
</head>
<body>
<h1>SIN flight prices &mdash; SIA &amp; Scoot</h1>
<div class="sub">Daily snapshot of Trip.com&rsquo;s lowest published fares to Bangkok, Phuket, Taipei. Round-trip filter: June 2026 dep, 3-5 night stay.</div>

<div class="card">
  <div class="summary" id="summary"></div>
</div>

<div class="card">
  <div class="tabs">
    <button class="tab active" data-metric="one_way_june">One-way June</button>
    <button class="tab" data-metric="round_trip_june">Round-trip (3-5n)</button>
  </div>
  <div class="chartwrap"><canvas id="trend"></canvas></div>
</div>

<div class="card">
  <h3 style="margin:0 0 8px;font-size:14px">All snapshots</h3>
  <div id="history"></div>
</div>

<script>
const PAYLOAD = __PAYLOAD__;
const DEST_LABEL = {"BKK":"Bangkok","HKT":"Phuket","TPE":"Taipei"};
const COLOR = {"BKK":"#2563eb","HKT":"#16a34a","TPE":"#dc2626"};

let activeMetric = "one_way_june";
let chart;

function fmtPct(p) {
  if (p == null) return 'n/a';
  const sign = p > 0 ? '+' : '';
  return `${sign}${p}%`;
}
function trendBadge(s) {
  if (!s) return '';
  const map = { down: ['#16a34a','↓ down'], up: ['#dc2626','↑ up'], flat: ['#64748b','→ flat'] };
  const [c, label] = map[s.trend_recent] || map.flat;
  return `<span class="tag" style="background:${c}1a;color:${c}">${label}</span>`;
}
function renderSummary() {
  const root = document.getElementById('summary');
  root.innerHTML = '';
  ['BKK','HKT','TPE'].forEach(code => {
    const ow = PAYLOAD.latest['one_way_june|' + code];
    const rt = PAYLOAD.latest['round_trip_june|' + code];
    const ows = (PAYLOAD.stats[code] || {}).one_way_june;
    const rts = (PAYLOAD.stats[code] || {}).round_trip_june;
    const div = document.createElement('div');
    div.className = 'dest';
    div.innerHTML = `
      <div class="name"><span class="dot" style="background:${COLOR[code]}"></span>${DEST_LABEL[code]} (${code})</div>
      ${ow ? `
        <div class="price">S$${ow.price_sgd} ${trendBadge(ows)}</div>
        <div class="meta">one-way June &middot; ${ow.airline_out}${ow.dep_date ? ' &middot; dep ' + ow.dep_date : ''}</div>
        ${ows ? `<div class="stats">
          <div>vs prior day: <strong>${fmtPct(ows.delta_day_pct)}</strong></div>
          <div>vs 7-day avg (S$${ows.avg_7d != null ? Math.round(ows.avg_7d) : 'n/a'}): <strong>${fmtPct(ows.delta_vs_7d_pct)}</strong></div>
          <div>lowest seen: <strong>S$${ows.lowest_so_far}</strong> on ${ows.lowest_date}</div>
        </div>` : ''}
        <div class="meta">snapshot ${ow.snapshot_date}${ow.note && ow.note.startsWith('fallback') ? ' <span class="tag">' + ow.note + '</span>' : ''}</div>
      ` : '<div class="price">--</div><div class="meta">no one-way data</div>'}
      ${rt ? `
        <div class="alt">
          <div><strong>S$${rt.price_sgd}</strong> round-trip ${trendBadge(rts)}</div>
          <div class="meta">${rt.airline_out === rt.airline_in ? rt.airline_out : (rt.airline_out + ' / ' + rt.airline_in)} &middot; ${rt.dep_date} &rarr; ${rt.ret_date}</div>
          ${rts ? `<div class="stats">
            <div>vs prior day: <strong>${fmtPct(rts.delta_day_pct)}</strong></div>
            <div>vs 7-day avg (S$${rts.avg_7d != null ? Math.round(rts.avg_7d) : 'n/a'}): <strong>${fmtPct(rts.delta_vs_7d_pct)}</strong></div>
            <div>lowest seen: <strong>S$${rts.lowest_so_far}</strong> on ${rts.lowest_date}</div>
          </div>` : ''}
          <div class="meta">${rt.note && rt.note.startsWith('fallback') ? '<span class="tag">' + rt.note + '</span>' : ''}</div>
        </div>` : '<div class="alt"><div class="meta">no round-trip match yet</div></div>'}
    `;
    root.appendChild(div);
  });
}

function renderChart() {
  const datasets = PAYLOAD.metrics[activeMetric] || [];
  const ctx = document.getElementById('trend');
  if (PAYLOAD.labels.length === 0 || datasets.every(d => d.data.every(v => v == null))) {
    ctx.parentElement.innerHTML = '<div class="empty">No daily snapshots yet for this metric. The scheduled task populates this each morning.</div>';
    return;
  }
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'line',
    data: { labels: PAYLOAD.labels, datasets: datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
      scales: {
        x: { title: { display: true, text: 'Snapshot date' } },
        y: { title: { display: true, text: 'SGD' }, beginAtZero: false }
      }
    }
  });
}

function renderHistory() {
  const rows = (PAYLOAD.rows || []).slice().sort((a,b) => b.snapshot_date.localeCompare(a.snapshot_date) || a.dest.localeCompare(b.dest) || a.metric.localeCompare(b.metric));
  const root = document.getElementById('history');
  if (rows.length === 0) { root.innerHTML = '<div class="empty">History will appear after the first scrape runs.</div>'; return; }
  const headers = ['Snapshot','Dest','Metric','SGD','Dep','Ret','Out airline','Return airline','Note'];
  let html = '<table><thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>';
  for (const r of rows) {
    html += `<tr>
      <td>${r.snapshot_date}</td>
      <td>${DEST_LABEL[r.dest] || r.dest}</td>
      <td>${r.metric.replace('_',' ')}</td>
      <td><strong>S$${r.price_sgd}</strong></td>
      <td>${r.dep_date || ''}</td>
      <td>${r.ret_date || ''}</td>
      <td>${r.airline_out || ''}</td>
      <td>${r.airline_in || ''}</td>
      <td>${r.note || ''}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  root.innerHTML = html;
}

document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeMetric = btn.dataset.metric;
    renderChart();
  });
});

renderSummary();
renderChart();
renderHistory();
</script>
</body>
</html>
"""
    return html.replace("__PAYLOAD__", pj)


def main():
    rows = load_rows()
    payload = build_payload(rows)
    html = build_html(payload)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT_PATH}  ({len(rows)} rows)")


if __name__ == "__main__":
    main()
