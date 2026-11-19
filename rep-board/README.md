# Rep Board

Richie's board: reps across the top, metrics down the side.

Rows, in order: close rate, sales this week, sales this month, sales this quarter,
sales this year, gross profit (with GP%), sits. Close rate and sits are quarter to date,
gross profit is year to date, weeks run Monday to Sunday.

## Files
- `index.html`: the board, styled to Rapid Roofing Design System V2 (same header, chips, black bars and footer as the Thermometer and Sales Scoreboard). Reads `data.json`.
- `assets/`: white Rapid logo, R mark, and the brand fonts (Barlow Condensed, Inter), bundled so nothing loads from outside.
- `build.py`: the numbers builder. Picks the reps and date windows; every number comes from `rules/rr_metrics.py` in `rapidhsg/rr-metrics-data`. The reps and their column order are the `REPS` list at the top. Marco and Josh are left out on purpose.
- `data.json`: the numbers, rebuilt every 15 minutes by the repo's refresh job.

## Visibility
This board was first meant for Richie only. As of 2026-11-19 it is published publicly with the other
dashboards (Joe's call). It shows sales and gross profit by rep, but no customer details.
