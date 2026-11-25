# Working in rapidhsg/dashboards (Claude Code sessions)

- No metric is defined here. Every number comes from `rules/rr_metrics.py` in `rapidhsg/rr-metrics-data`.
- Never edit a `data.json`; the refresh job writes them.
- **Adding or removing a sales rep:** follow the checklist in `CLAUDE.md` in `rapidhsg/rr-metrics-data`.
  In this repo it touches `sales-scoreboard/config.json` (`repDisplay`) and `rep-board/build.py` (`REPS`).
  If rr-metrics-data is not in the session, ask Joe to add it before starting.
