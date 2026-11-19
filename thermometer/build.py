"""Thermometer, the quarterly thermometer: builds thermometer/data.json.

Quarter to date vs the quarter's goals. Every count and dollar comes from the locked rr-metrics rules;
this file only picks the window and pairs each number with its goal.
Display settings: thermometer/config.json. Quarterly goals: thermometer/goals.json. Shared settings: shared/config.json.
On any failure nothing is written (the board keeps the last good numbers) and an alert is emailed.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
import dashlib  # noqa: E402

NAME = "Thermometer"
CONFIG = json.loads((HERE / "config.json").read_text())
GOALS = json.loads((HERE / "goals.json").read_text())


def main():
    rr, df, data_dir, run_iso, run_dt = dashlib.load(NAME)
    run_ymd = dashlib.report_day(run_dt).isoformat()
    q = dashlib.quarter_for(dashlib.report_day(run_dt))
    goals = GOALS.get(q["label"])
    if not goals:
        dashlib.fail(NAME, "failed: goals not set", [f'No goals for "{q["label"]}" in thermometer/goals.json.'])

    m = rr.metrics(df, q["startDate"], run_ymd)
    rip, _ = rr.revenue_in_progress(str(data_dir / "Revenue_In_Progress_latest.csv"), q["startDate"], q["endDate"])
    actuals = {"sales": m["sales"], "in_progress": rip, "revenue": m["revenue"], "upsells": m["upgrades"],
               "leads": m["leads"], "sits": m["sits"], "jobs": m["jobs_installed"]}
    data = {"quarter": {**q, "refreshDate": run_ymd}, "freshness": dashlib.freshness(run_iso),
            "metrics": [{**x, "actual": round(actuals[x["key"]]), "goal": goals[x["key"]]} for x in CONFIG["metrics"]]}

    bad = [f'"{x["key"]}" goal missing' for x in data["metrics"] if not goals.get(x["key"])]
    if bad:
        dashlib.fail(NAME, "BLOCKED by validation gate", bad)
    out = dashlib.write(HERE, data)
    print(f"OK {NAME} -> {out}: {q['label']} @ {run_ymd} (AccuLynx run {run_iso}): "
          + ", ".join(f"{k}={v}" for k, v in actuals.items()))


if __name__ == "__main__":
    main()
