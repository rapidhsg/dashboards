"""Shared plumbing for every dashboard builder in this repo.

Every number on every dashboard comes from the ONE shared source, rapidhsg/rr-metrics-data:
  data  = branch "data" (AccuLynx scheduled sends, refreshed every 15 min)
  rules = branch "main" (rules/rr_metrics.py + settings.json, locked by Joe)

This file never defines a metric. It only finds the rules and data, checks the data is fresh and
complete, emails an alert when something breaks, and writes each dashboard's data.json.

Env:
  RRM_RULES       folder with rr_metrics.py (the rules/ folder of rr-metrics-data main)
  RRM_DATA        folder with job_export_raw_latest.csv, status.json, ... (the data/ folder of the data branch)
  GH_TOKEN        read-only token for rapidhsg/rr-metrics-data, used only when RRM_RULES/RRM_DATA are not set
                  (local runs). Needed once rr-metrics-data is private.
  RESEND_API_KEY  failure alerts by email (optional)
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "shared" / "config.json").read_text())
ET = ZoneInfo("America/New_York")
METRICS_REPO = "rapidhsg/rr-metrics-data"
REQUIRED_COLUMNS = ["Initial Appointment Date", "Primary Estimate Total", "Approved Milestone Date",
                    "Completed Milestone Date", "Lead Milestone Date", "Prospect Milestone Date",
                    "Contract Amount", "Primary Salesperson", "Appointment Set By"]


def alert(subject, lines):
    print(f"FAIL: {subject}\n - " + "\n - ".join(lines), file=sys.stderr)
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        return
    html = f"<h2>{subject}</h2><ul>" + "".join(f"<li>{l}</li>" for l in lines) + \
           "</ul><p style='color:#888'>The dashboards are still showing the last good numbers.</p>"
    body = json.dumps({"from": "Rapid Roofing Dashboards <alerts@updates.mycoresystem.com>",
                       "to": CONFIG["alertRecipients"], "subject": subject, "html": html}).encode()
    req = urllib.request.Request("https://api.resend.com/emails", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
    except Exception as e:  # alert failure must never hide the real failure
        print(f"[alert] send failed: {e}", file=sys.stderr)


def fail(dashboard, subject, lines):
    alert(f"{dashboard} refresh {subject}", lines)
    sys.exit(1)


def _clone(branch, dest):
    tok = os.environ.get("GH_TOKEN")
    url = f"https://x-access-token:{tok}@github.com/{METRICS_REPO}.git" if tok else f"https://github.com/{METRICS_REPO}.git"
    subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", branch, url, str(dest)], check=True)


def sources():
    """(rules_dir, data_dir). Uses RRM_RULES / RRM_DATA, or clones rr-metrics-data for a local run."""
    rules, data = os.environ.get("RRM_RULES"), os.environ.get("RRM_DATA")
    tmp = None
    if not rules or not data:
        tmp = Path(tempfile.mkdtemp(prefix="rr-metrics-"))
    if not rules:
        _clone("main", tmp / "main")
        rules = tmp / "main" / "rules"
    if not data:
        _clone("data", tmp / "data")
        data = tmp / "data" / "data"
    return Path(rules), Path(data)


def load(dashboard):
    """Load the locked rules and the shared data, and stop (with an alert) if the data is stale or incomplete.

    Returns (rr, df, data_dir, run_iso, run_dt_et): the rr_metrics module, the job export, where the data
    lives, the AccuLynx run timestamp, and that run time in Eastern.
    """
    rules_dir, data_dir = sources()
    sys.path.insert(0, str(rules_dir))
    try:
        import rr_metrics as rr
    except Exception as e:
        fail(dashboard, "failed: could not load the rr-metrics rules", [repr(e)])

    try:
        status = json.loads((data_dir / "status.json").read_text())
        run_iso = status["job_export_raw"]["runDate"]
        df = rr.load(str(data_dir / "job_export_raw_latest.csv"))
    except Exception as e:
        fail(dashboard, "failed: could not read the rr-metrics data", [repr(e)])

    errors = []
    run_dt = datetime.fromisoformat(run_iso[:19]).replace(tzinfo=ZoneInfo("UTC")).astimezone(ET)
    if datetime.now(ET) - run_dt > timedelta(days=2):
        errors.append(f"job export is stale (last AccuLynx run {run_iso})")
    if len(df) < 1000:
        errors.append(f"job export has only {len(df)} rows")
    errors += [f'job export is missing column "{c}"' for c in REQUIRED_COLUMNS if c not in df.columns]
    if errors:
        fail(dashboard, "BLOCKED by validation gate", errors)
    return rr, df, data_dir, run_iso, run_dt


def report_day(run_dt):
    """The day the dashboards report as of: the AccuLynx run day, unless shared/config.json pins asOfDate."""
    if CONFIG.get("asOfDate"):
        return datetime.fromisoformat(CONFIG["asOfDate"]).date()
    return run_dt.date()


def quarter_for(d):
    q = (d.month - 1) // 3 + 1
    start = d.replace(month=(q - 1) * 3 + 1, day=1)
    end = (start.replace(month=start.month + 2, day=28) + timedelta(days=4))
    end = end - timedelta(days=end.day)
    return {"label": f"Q{q} {d.year}", "startDate": start.isoformat(), "endDate": end.isoformat()}


def schedule_et(day=None):
    """AccuLynx send times (shared/config.json acculynxScheduleUTC) as Eastern "HH:MM" for the given day.

    AccuLynx sends at fixed UTC times, so in Eastern they move an hour with daylight saving."""
    day = day or datetime.now(ET).date()
    out = []
    for hm in CONFIG.get("acculynxScheduleUTC", []):
        h, m = (int(x) for x in hm.split(":"))
        out.append(datetime(day.year, day.month, day.day, h, m, tzinfo=ZoneInfo("UTC")).astimezone(ET).strftime("%H:%M"))
    return sorted(out)


def freshness(run_iso):
    """The freshness chip shown on the Thermometer and Sales Scoreboard."""
    return {"acculynxRun": run_iso, "scheduleET": schedule_et(),
            "lagMinutes": CONFIG.get("refreshLagMinutes", 20), "builtAt": datetime.now(ZoneInfo("UTC")).isoformat()}


def write(folder, obj):
    """Write a dashboard's data.json next to its index.html (OUTPUT_DIR overrides, for testing)."""
    out = Path(os.environ["OUTPUT_DIR"]) / Path(folder).name if os.environ.get("OUTPUT_DIR") else Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    (out / "data.json").write_text(json.dumps(obj, indent=2) + "\n")
    return out / "data.json"
