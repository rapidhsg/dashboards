"""GP Pacing: builds gp-pacing/data.json for the Gross Profit Pacing board (index.html) from rapidhsg/rr-metrics-data.

Every count comes from rules/rr_metrics.py. Goals, tiers and gates come from gp_plan.json.
Gross profit = jobs installed this quarter. Actual = installed jobs already Closed in AccuLynx (or a
closed P&L month from gp_plan.json). Estimate = installed jobs not Closed yet, at the margin the closed
ones are running. The board always shows the two separately. The bonus itself is paid on the company P&L.

On any failure nothing is written (the board keeps the last good numbers) and an alert is emailed.

    python gp-pacing/build.py     # env: REPORT_DATE (optional); local runs clone rr-metrics-data (GH_TOKEN once private)
"""
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
import dashlib  # noqa: E402

NAME = "GP Pacing"
ET = dashlib.ET
PLAN = json.loads((HERE / "gp_plan.json").read_text())


def main():
    import pandas as pd

    rr, df, data_dir, run_iso, pulled = dashlib.load(NAME)
    today = pd.Timestamp(os.environ.get("REPORT_DATE") or datetime.now(ET).date()).normalize()

    q = (today.month - 1) // 3
    q_start = pd.Timestamp(today.year, q * 3 + 1, 1)
    q_end = q_start + pd.offsets.QuarterEnd(0)
    key = f"{today.year}-Q{q + 1}"
    goals = PLAN["quarters"].get(key)
    if not goals:
        dashlib.fail(NAME, "failed: goals not set", [f"No goals for {key} in gp-pacing/gp_plan.json. Joe sets them at quarterly planning."])

    rip = str(data_dir / "Revenue_In_Progress_latest.csv")

    days_total = (q_end - q_start).days + 1
    days_done = (today - q_start).days + 1
    weeks_left = max((q_end - today).days, 1) / 7

    gp_goal = goals["revenue_goal"] * goals["gp_goal_pct"]
    floor_pct = goals["gp_goal_pct"] * PLAN["gates"]["margin_floor_share_of_goal"]

    # Quarter to date, rr_metrics rules. Close rate uses the sales team roster (Richie's direct reps).
    m = rr.metrics(df, q_start, today)

    # Gross profit = jobs installed (Completed date) this quarter. ACTUAL = installed jobs already Closed
    # (profit is final in AccuLynx), same GP rule as rr_metrics (no Call Backs, no $0 or 100% profit jobs).
    # ESTIMATE = installed jobs not Closed yet, at the margin the closed ones are running.
    ca = df["Contract Amount"]
    inst = rr.masks(df, q_start, today)["revenue"]
    is_closed = inst & (df["Current Milestone"] == "Closed")
    good = is_closed & (df["Profit"] != 0) & (df["Profit %"] != 1)
    actual_gp = float(df.loc[good, "Profit"].sum())
    actual_value = float(ca[good].sum())
    margin = actual_gp / actual_value if actual_value else goals["gp_goal_pct"]
    open_mask = inst & ~is_closed
    open_value = float(ca[open_mask].sum())
    est_gp = open_value * margin

    # A month whose P&L is closed replaces AccuLynx for that month (actual, no estimate).
    months = []
    for start in pd.date_range(q_start, q_end, freq="MS"):
        if start > today:
            break
        end = min(start + pd.offsets.MonthEnd(0), today)
        inm = df["Completed Milestone Date"].between(start, end)
        a_gp = float(df.loc[good & inm, "Profit"].sum())
        o_val = float(ca[open_mask & inm].sum())
        pl = PLAN["pl_months"].get(f"{start:%Y-%m}") or {}
        row = {"month": f"{start:%B}", "installed": round(float(ca[inst & inm].sum())),
               "closed_jobs": int((good & inm).sum()), "actual_gp": round(a_gp),
               "open_jobs": int((open_mask & inm).sum()), "open_value": round(o_val),
               "estimate_gp": round(o_val * margin), "source": "AccuLynx"}
        if pl.get("gross_profit") is not None:
            actual_gp += float(pl["gross_profit"]) - a_gp
            est_gp -= o_val * margin
            row.update({"actual_gp": round(float(pl["gross_profit"])), "estimate_gp": 0, "source": "P&L"})
        months.append(row)
    gp_to_date = actual_gp + est_gp

    sched_value, sched_jobs = rr.revenue_in_progress(rip, today, q_end)  # installs on the schedule through quarter end
    projected = gp_to_date + float(sched_value) * margin

    tiers = []
    for t in PLAN["tiers"]:
        target = gp_goal * t["at"]
        gp_needed = max(0.0, target - gp_to_date)
        rev_needed = gp_needed / margin if margin else 0
        tiers.append({
            "name": t["name"], "at": t["at"], "rate": t["rate"],
            "gp_target": round(target), "bonus": round(target * t["rate"]),
            "gp_needed": round(gp_needed), "install_needed": round(rev_needed),
            "per_week": round(rev_needed / weeks_left),
            "beyond_schedule": round(max(0.0, rev_needed - float(sched_value))),
            "hit": bool(gp_to_date >= target),
        })

    def bonus_at(gp):
        rate = 0
        for t in PLAN["tiers"]:
            if gp >= gp_goal * t["at"]:
                rate = t["rate"]
        return gp * rate

    sold, demos = m["close_sold_team"], m["close_sits_team"]
    cr = sold / demos if demos else 0
    cr_min = PLAN["gates"]["team_close_rate_min"]
    sales_short = max(0, math.ceil(cr_min * demos - sold - 1e-9))

    out = {
        "updated": pulled.isoformat(timespec="seconds"),
        "quarter": f"Q{q + 1} {today.year}",
        "day": days_done, "days": days_total, "quarter_end": f"{q_end:%b} {q_end.day}", "weeks_left": round(weeks_left, 1),
        "revenue_goal": goals["revenue_goal"], "gp_goal_pct": goals["gp_goal_pct"], "gp_goal": round(gp_goal),
        "gp_to_date": round(gp_to_date), "actual_gp": round(actual_gp), "estimate_gp": round(est_gp),
        "installed": round(float(ca[inst].sum())), "installed_jobs": int(inst.sum()),
        "closed_jobs": int(good.sum()), "closed_value": round(actual_value),
        "open_jobs": int(open_mask.sum()), "open_value": round(open_value),
        "pace_target": round(gp_goal * days_done / days_total),
        "months": months,
        "scheduled": {"value": round(float(sched_value)), "jobs": int(sched_jobs)},
        "projected_gp": round(projected),
        "projected_bonus": round(bonus_at(projected)),
        "tiers": tiers,
        "gates": {
            "margin": {"value": round(margin, 4), "min": round(floor_pct, 4), "pass": bool(margin >= floor_pct)},
            "close_rate": {"value": round(cr, 4), "min": cr_min, "pass": bool(cr >= cr_min),
                           "sold": int(sold), "demos": int(demos), "sales_short": sales_short},
        },
        "base_quarter": round(PLAN["base_salary_annual"] / 4),
    }
    path = dashlib.write(HERE, out)
    print(f"OK {NAME} -> {path} ({out['quarter']} day {days_done}/{days_total}, GP to date ${gp_to_date:,.0f})")


if __name__ == "__main__":
    main()
