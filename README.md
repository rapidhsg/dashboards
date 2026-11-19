# Dashboards

Every Rapid Roofing dashboard, in one place. One folder per dashboard; each folder holds the page people
see and the numbers builder behind it.

| Folder | Dashboard | Live at |
|---|---|---|
| `rr1/` | RR1, the quarterly thermometer (quarter to date vs goals) | https://rapidhsg.github.io/dashboards/rr1/ |
| `rr2/` | RR2, the sales scoreboard (rolling 90 days, reps and setters) | https://rapidhsg.github.io/dashboards/rr2/ |
| `rep-board/` | Rep Board (reps across, metrics down) | https://rapidhsg.github.io/dashboards/rep-board/ |

## How it works

```
rapidhsg/rr-metrics-data  (private: AccuLynx data + the locked metric rules)
          │  every 15 min
          ▼
.github/workflows/refresh.yml  runs  rr1/build.py, rr2/build.py, rep-board/build.py
          │  each writes its folder's data.json (totals only, no customer details)
          ▼
GitHub Pages serves each folder's index.html, which reads its data.json
```

- **No dashboard defines a metric or calls AccuLynx.** Every number comes from `rules/rr_metrics.py` in
  `rapidhsg/rr-metrics-data`, so the dashboards always match the rr-metrics skill and each other.
  To change how a metric is counted, or who is on the sales team, change it there. Never here.
- **Each dashboard builds on its own.** If one fails, the others still publish, the failed one keeps its last
  good numbers, the job turns red and an alert is emailed (`shared/config.json` → `alertRecipients`).
- **rr-metrics-data starts the refresh** right after each new AccuLynx pull, so the boards are usually current
  within a few minutes. The 15-minute schedule is the backup.

## What's in each folder

Each dashboard folder has:
- `index.html`: the page (layout, colors, logo). No math.
- `build.py`: the numbers builder. Picks which metrics, which dates and which goals; writes `data.json`.
- `data.json`: the published numbers. Written by the refresh job; never edit by hand.
- `config.json` / `goals.json` (if any): that dashboard's display settings.

`shared/` holds what every builder uses: `dashlib.py` (finds the rules and data, checks the data is fresh
and complete, sends alerts) and `config.json` (alert recipients, AccuLynx schedule, `asOfDate`).

## Every quarter

Update `rr1/goals.json` with the new quarter's 7 goals. The label must match exactly, e.g. `"Q1 2027"`.

## Add a dashboard

1. Make a new folder with `index.html` and `build.py` (copy `rr1/` as a starting point).
2. Add a build step for it in `.github/workflows/refresh.yml` and add its `data.json` to the publish step.

## Run a builder on your own computer

```bash
pip install pandas
GH_TOKEN=<read-only token for rr-metrics-data> python rr1/build.py
```
Without `RRM_RULES` / `RRM_DATA` set, the builder clones rr-metrics-data itself.

## Repo secrets

- `RR_METRICS_READ_TOKEN`: read-only token for `rapidhsg/rr-metrics-data`.
- `RESEND_API_KEY`: failure alert emails.

## History

This repo brings together `rapidhsg/dashboard-engine`, `rapidhsg/rr1`, `rapidhsg/rr2` and
`rapidhsg/rr-rep-board` (2026-11-19), with their full commit history. Use `git log --follow <file>` to see
a file's history from before the move.
