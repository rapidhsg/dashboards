"""Sales Scoreboard, the sales team scoreboard: builds sales-scoreboard/data.json.

Rolling window (sales-scoreboard/config.json rollingWindowDays). Reps: close rate and revenue per sit with the certified
close rate rules, current sales team from rr-metrics settings.json. Setters: appointments booked in the window.
Every count and dollar comes from the locked rr-metrics rules; this file only picks the window and arranges them.
On any failure nothing is written (the board keeps the last good numbers) and an alert is emailed.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "shared"))
import dashlib  # noqa: E402

NAME = "Sales Scoreboard"
CONFIG = json.loads((HERE / "config.json").read_text())


def main():
    rr, df, data_dir, run_iso, run_dt = dashlib.load(NAME)
    run_ymd = dashlib.report_day(run_dt).isoformat()
    q = dashlib.quarter_for(dashlib.report_day(run_dt))

    lo, hi = rr.rolling(run_ymd, CONFIG["rollingWindowDays"])
    mk = rr.masks(df, lo, hi)
    ca = df["Contract Amount"].fillna(0)
    display = {r["fullName"]: r for r in CONFIG.get("repDisplay", [])}
    order = [r["fullName"] for r in CONFIG.get("repDisplay", [])]
    reps = []
    for name in sorted(rr.SALES_TEAM, key=lambda n: order.index(n) if n in order else len(order)):
        me = df["Primary Salesperson"] == name
        sits = int((mk["close_sits_team"] & me).sum())
        sold_mask = mk["close_sold_team"] & me
        sold, dollars = int(sold_mask.sum()), round(ca[sold_mask].sum())
        d = display.get(name, {})
        reps.append({"name": name, "short": d.get("short", name.upper()), "role": d.get("role", "OUTSIDE SALES"),
                     "demos": sits, "sold": sold, "soldDollars": dollars,
                     "closeRate": round(100 * sold / sits, 1) if sits else 0,
                     "revPerSit": round(dollars / sits) if sits else 0})
    t_sits = sum(r["demos"] for r in reps)
    t_sold = sum(r["sold"] for r in reps)
    t_dol = sum(r["soldDollars"] for r in reps)
    team = {"demos": t_sits, "sold": t_sold, "soldDollars": t_dol,
            "closeRate": round(100 * t_sold / t_sits, 1) if t_sits else 0,
            "revPerSit": round(t_dol / t_sits) if t_sits else 0}

    # Setters: appointments booked in the window (locked Appointments rule), credited to "Appointment Set By".
    skip = {s.lower() for s in CONFIG.get("setterExclude", [])}
    appts = df[mk["appointments"]].copy()
    appts["_by"] = appts["Appointment Set By"].fillna("").astype(str).str.strip()
    setters = []
    for name, g in appts.groupby("_by"):
        if not name or name.lower() in skip:
            continue
        won = g["Approved Milestone Date"].notna() & g["Current Milestone"].isin(rr.MS["sales_count_if_currently"])
        setters.append({"name": name.upper(), "role": "APPT SETTER", "apptsSet": len(g), "sold": int(won.sum()),
                        "soldDollars": round(g.loc[won, "Contract Amount"].fillna(0).sum()),
                        "conversion": round(100 * won.sum() / len(g), 1) if len(g) else 0})
    setters.sort(key=lambda s: -s["soldDollars"])

    if t_sits <= 0:
        dashlib.fail(NAME, "BLOCKED by validation gate", ["team sits is 0"])
    data = {"quarter": {**q, "refreshDate": run_ymd}, "freshness": dashlib.freshness(run_iso), "goals": CONFIG.get("highlightGoals"),
            "openSeats": max(0, CONFIG.get("targetSlots", 0) - len(reps)),
            "team": team, "reps": reps, "setters": setters,
            "source": {"data": "rapidhsg/rr-metrics-data@data", "rules": "rapidhsg/rr-metrics-data@main", "acculynxRun": run_iso}}
    out = dashlib.write(HERE, data)
    print(f"OK {NAME} -> {out}: {len(reps)} reps, {len(setters)} setters, window {lo}..{hi}")


if __name__ == "__main__":
    main()
