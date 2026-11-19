"""Rep Board: builds rep-board/data.json.

Reps across the top, metrics down the side: close rate, sales this week / month / quarter / year,
gross profit (with GP%), sits. Every number comes from the locked rr-metrics rules (rules/RULES.md).
This script only picks the date windows and the reps. It does no counting of its own.
On any failure nothing is written (the board keeps the last good numbers) and an alert is emailed.

    python rep-board/build.py                  # local run: clones rr-metrics-data (set GH_TOKEN once it is private)
    REPORT_DATE=2026-11-19 python rep-board/build.py   # build the board as of another day (default: today, Eastern)
"""
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
import dashlib  # noqa: E402

NAME = "Rep Board"
ET = dashlib.ET

# Board column order. Left: name shown on the board. Right: exact AccuLynx Primary Salesperson
# (must be in settings.json sales_team). Marco and Josh are left out on purpose.
REPS = [
    ("Mike Dietrich", "Michael Dietrich"),
    ("Francesco Ambrosio", "Francesco Ambrosio"),
    ("Joe Young", "Joseph Young"),
    ("Franco Querlim", "Querlim Franco"),
    ("Daniel Leverich", "Dan Leverich"),
    ("Leomar Santana", "Leo Santana"),
]


def periods(today):
    import pandas as pd
    t = pd.Timestamp(today).normalize()
    mon = t - pd.Timedelta(days=t.weekday())                     # week = Monday to Sunday
    q = (t.month - 1) // 3
    q_start = pd.Timestamp(t.year, q * 3 + 1, 1)
    q_end = q_start + pd.offsets.QuarterEnd(0)
    return {
        "week": (mon, mon + pd.Timedelta(days=6)),
        "month": (t.replace(day=1), t + pd.offsets.MonthEnd(0)),
        "quarter": (q_start, q_end),
        "year": (pd.Timestamp(t.year, 1, 1), pd.Timestamp(t.year, 12, 31)),
        "_q": q + 1,
        # weeks counted Monday to Sunday; week 1 is the week the quarter starts in
        "_wk": min(13, (mon - (q_start - pd.Timedelta(days=q_start.weekday()))).days // 7 + 1),
    }


def main():
    rr, df, data_dir, run_iso, run_dt = dashlib.load(NAME)
    pulled = run_dt
    today = datetime.fromisoformat(os.environ["REPORT_DATE"]).date() if os.environ.get("REPORT_DATE") else datetime.now(ET).date()

    names = [acc for _, acc in REPS]
    missing = [n for n in names if n not in rr.SALES_TEAM]
    if missing:
        dashlib.fail(NAME, "BLOCKED: reps not on the sales team", [f"Not on the sales_team roster in rr-metrics settings.json: {missing}. Ask Joe."])

    P = periods(today)
    ca = df["Contract Amount"]
    sp = df["Primary Salesperson"]

    # Masks from rr_metrics, one set per window. Close rate and sits = quarter to date, GP = year to date.
    M = {k: rr.masks(df, *P[k], reps=names) for k in ["week", "month", "quarter", "year"]}

    def rep_block(who):
        r = sp.isin(who)
        mq, my = M["quarter"], M["year"]
        sits_cr = int((mq["close_sits_team"] & r).sum())
        sold_cr = int((mq["close_sold_team"] & r).sum())
        gp_profit = float(df.loc[my["gp_jobs"] & r, "Profit"].sum())
        gp_contract = float(ca[my["gp_jobs"] & r].sum())
        return {
            "close_rate": round(sold_cr / sits_cr, 4) if sits_cr else 0,
            "close_counts": {"approved": sold_cr, "demos": sits_cr},
            "sits": int((mq["sits"] & r).sum()),
            "sales": {k: {"amount": round(float(ca[M[k]["sales"] & r].sum())),
                          "count": int((M[k]["jobs_sold"] & r).sum())} for k in M},
            "gp": {"amount": round(gp_profit), "pct": round(gp_profit / gp_contract, 4) if gp_contract else 0},
            # Avg Ticket (RULES.md section 4) = Sales $ / Jobs Sold, same records as the sales rows.
            "avg_ticket": {k: (round(float(ca[M[k]["sales"] & r].sum()) / n) if (n := int((M[k]["jobs_sold"] & r).sum())) else 0)
                           for k in ["quarter", "year"]},
        }

    w0, w1 = P["week"]
    out = {
        "sample": False,
        "updated": pulled.isoformat(timespec="seconds"),
        "periods": {
            "week": f"{w0:%b} {w0.day} – {w1:%b} {w1.day}",
            "month": f"{P['month'][0]:%B}",
            "quarter": f"Q{P['_q']} {today.year}",
            "year": str(today.year),
            "close_rate": f"Q{P['_q']} {today.year}",
            "sits": f"Q{P['_q']} {today.year}",
            "week_of_quarter": f"{P['_wk']} / 13",
        },
        "reps": [{"name": shown, **rep_block([acc])} for shown, acc in REPS],
        "team": rep_block(names),
    }
    path = dashlib.write(HERE, out)
    print(f"OK {NAME} -> {path} (report date {today}, data pulled {pulled:%b %d %I:%M %p} ET)")


if __name__ == "__main__":
    main()
