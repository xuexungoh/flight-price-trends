# Tracking Flight Prices

A daily flight-price scraper and dashboard tracking the cheapest published fares from **Singapore (SIN)** to **Bangkok (BKK)**, **Phuket (HKT)** and **Taipei (TPE)** for June 2026 travel. Singapore Airlines and Scoot are the priority carriers; all other airlines are recorded as reference signal.

Public dashboard: <https://xuexungoh.github.io/flight-price-trends/>
Live in-app view: open the **flight-price-trends** artifact tab in Cowork.

---

## Objectives

1. Watch how round-trip and one-way June 2026 fares move day-by-day from now until departure.
2. Highlight the cheapest fare ever seen per route (the "anchor" we'd buy at) and how today's price compares.
3. Compare Singapore Airlines and Scoot prices against the broader market (all carriers visible on the aggregator).
4. Deliver the daily summary in three surfaces: a Gmail draft, a Cowork artifact, and a public GitHub Pages site — all updated automatically.

## What we pull

For each of the three routes we fetch the Trip.com landing page once per day:

| Route | URL |
|-------|-----|
| SIN → BKK | <https://sg.trip.com/flights/singapore-to-bangkok/airfares-sin-bkk/> |
| SIN → HKT | <https://sg.trip.com/flights/singapore-to-phuket/airfares-sin-hkt/> |
| SIN → TPE | <https://sg.trip.com/flights/singapore-to-taipei/airfares-sin-tpe/> |

From each page we parse three structures:

- **Monthly summary** lines such as `June: From S$ 175 with Scoot, departing on Tue, Jun 2.` — the source for the cheapest one-way June fare per airline.
- **Round-trip cards** — each shows outbound leg, return leg and total round-trip price. We filter to June departures with a 3-5 night stay, then take the cheapest.
- **Headline round-trip deal** — the "Round-Trip Flight Deals: From S$ X with Y" banner. Used as a last-resort fallback (within the same carrier tier).

Per snapshot we record up to four CSV rows per route:

| metric | category | meaning |
|--------|----------|---------|
| `one_way_june` | `priority` | Cheapest June one-way on SIA or Scoot |
| `one_way_june` | `reference` | Cheapest June one-way on any carrier |
| `round_trip_june` | `priority` | Cheapest SIA/Scoot June round-trip, 3-5 nights (with intra-SIA/Scoot fallback) |
| `round_trip_june` | `reference` | Cheapest any-airline June round-trip, 3-5 nights (with any-airline fallback) |

Rows where the priority and reference would be identical are de-duplicated.

## Repository layout

```
Tracking Flight Prices/
├── README.md                  ← this file
├── flight_parser.py           Parses Trip.com markdown into structured deal records
├── update_csv.py              Picks the cheapest priority + reference rows per route, appends to CSV
├── analyze.py                 Computes trend statistics (vs prior day, vs 7-day avg, lowest seen)
├── build_artifact.py          Renders the artifact HTML (KPI cards, trend chart, history table)
├── deploy.sh                  Publishes artifact.html to the GitHub Pages repo
│
├── flight_prices.csv          Append-only log of every daily snapshot
├── artifact.html              Generated dashboard (also served from GitHub Pages)
├── public/index.html          Copy of artifact.html for any static hosts that serve /public
├── vercel.json                Legacy Vercel config (kept for reference; current host is GitHub Pages)
│
├── tmp/                       Daily fetched Trip.com pages — overwritten each run, gitignored
├── .github-token              GitHub PAT for pushes — never committed
├── .vercel-token              Legacy Vercel token — never committed
└── .gitignore
```

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Scraping transport | Cowork `web_fetch` MCP tool | The sandbox network can't reach Trip.com directly; the MCP tool bypasses that |
| Parsing | Python 3.11+, standard library only | No third-party packages — keeps the daily run self-contained |
| Storage | Append-only CSV | One file, version-controlled, dead-simple to diff |
| Dashboard | Self-contained HTML + Chart.js v4 | Single file deploys to anywhere; no build step |
| Public hosting | GitHub Pages (main branch root) | Free, auto-publishes on `git push`, sandbox can reach `github.com` |
| Daily automation | Cowork scheduled task (cron `0 8 * * *`) | Runs unattended in the user's local timezone with all required tool permissions |
| Notification | Gmail MCP `create_draft` | Compose-only — user reviews and sends |
| Aesthetic | Editorial travel-poster (serif display + monospace labels, warm paper palette) | Distinctive, calm, readable — designed against generic dashboard aesthetics |

## Execution flow — one daily run

```
┌──────────────────────────────────────────────────────────────────────┐
│  08:07 SGT — scheduled task "flight-price-daily-scrape" fires        │
└──────────────────────────────────────────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 1. web_fetch × 3                  │  →  tmp/bkk.md, tmp/hkt.md, tmp/tpe.md
   │    Trip.com landing pages         │
   └───────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 2. python update_csv.py           │  appends 4-12 rows to flight_prices.csv
   │    flight_parser → cheapest deals │
   └───────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 3. python build_artifact.py       │  rewrites artifact.html
   └───────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 4. python analyze.py --text       │  produces the email body
   └───────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 5. bash deploy.sh                 │  clones github.com:xuexungoh/flight-price-trends,
   │                                   │  copies artifact.html → index.html,
   │                                   │  commits + pushes → Pages republishes
   └───────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 6. update_artifact (Cowork)       │  refreshes the in-app artifact tab
   └───────────────────────────────────┘
              │
              ▼
   ┌───────────────────────────────────┐
   │ 7. gmail create_draft             │  drafts an email to xuexun@eogspecialist.com
   │                                   │  with the trend summary + dashboard URL
   └───────────────────────────────────┘
```

## Data caveats

- Trip.com landing pages cache their results — the "as of" date is often days or weeks old. Real-time pricing for June 2026 may be more accurate when checked directly on Singapore Airlines or Scoot's own sites. The dashboard reflects what Trip.com surfaces as the cheapest **publicly indexed** fare; treat it as a directional signal, not an exact quote.
- Some carriers (e.g. budget no-frills) sit outside the SIA/Scoot priority tier but are still recorded under `category=reference`. Filter by category in the CSV if you only care about the priority tier.
- The CSV is append-only — once a row is written, daily runs never overwrite past snapshots. If a row is wrong, edit the file directly and rebuild via `python3 build_artifact.py`.

## Manual operations

Run a full daily pipeline by hand (uses already-fetched tmp files, or pass real Trip.com markdown):

```bash
cd "/Users/xuexun/Desktop/VS Code Files/Personal Projects/Tracking Flight Prices"
python3 update_csv.py tmp/bkk.md tmp/hkt.md tmp/tpe.md
python3 build_artifact.py
python3 analyze.py --text       # human-readable summary
bash deploy.sh                  # publishes to GitHub Pages
```

Trigger the scheduled task immediately (rather than waiting for 08:00):

> Open the **Scheduled** sidebar in Cowork, find `flight-price-daily-scrape`, click **Run now**.

Pause the schedule:

> Toggle the task off in the Scheduled sidebar, or call `mcp__scheduled-tasks__update_scheduled_task` with `enabled: false`.

## Setup notes

- The daily scheduled task is registered with cron `0 8 * * *` in the user's local timezone (SGT). Cowork applies a small dispatch jitter so the actual fire time is ~08:07.
- The Gmail connector creates **drafts** — by design, no MCP-side tool autonomously sends mail. The draft lands in your Gmail Drafts folder; review and hit Send.
- GitHub Pages on the free tier requires a **public** repo. The `flight-price-trends` repo is public; the `.github-token` is gitignored so the secret never leaves the workspace.
- An earlier attempt to deploy to Vercel was abandoned because the sandbox proxy can't reach `api.vercel.com` reliably, but `vercel.json` is kept in case a future move back to Vercel becomes useful.

## License

Personal project. Trip.com is the upstream data source — please respect their terms of service.
