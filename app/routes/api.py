from datetime import datetime
from flask import Blueprint, jsonify, request
from app.models import AppSetting, SearchPreset
from app.database import db
from app.scheduler import scheduler

bp = Blueprint("api", __name__)

SUPPORTED_CURRENCIES = {"GBP", "USD", "EUR"}


@bp.post("/api/currency")
def set_currency():
    cur = (request.json or {}).get("currency", "GBP").upper()
    if cur not in SUPPORTED_CURRENCIES:
        return jsonify({"error": "Unsupported currency"}), 400
    AppSetting.set("currency", cur)
    return jsonify({"currency": cur})


@bp.post("/api/reorder")
def reorder_presets():
    order = (request.json or {}).get("order", [])
    for position, preset_id in enumerate(order):
        preset = db.session.get(SearchPreset, preset_id)
        if preset:
            preset.sort_order = position
    db.session.commit()
    return jsonify({"status": "ok"})


@bp.post("/api/trigger")
def manual_trigger():
    last_run = AppSetting.get("last_run_at", "Never")
    if last_run and last_run != "Never":
        try:
            from datetime import timezone
            last_dt = datetime.strptime(last_run, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            if elapsed < 300:
                remaining = int(300 - elapsed)
                return jsonify({"status": "error", "message": f"Please wait {remaining}s before running again."}), 429
        except ValueError:
            pass

    try:
        from app.services.price_checker import run_all_active_presets
        summaries = run_all_active_presets()
        AppSetting.set("last_run_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        return jsonify({"status": "ok", "results": summaries})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500


@bp.get("/api/status")
def status():
    last_run = AppSetting.get("last_run_at", "Never")
    next_run = AppSetting.get("next_run_at", "Unknown")

    job = scheduler.get_job("daily_price_check")
    if job and job.next_run_time:
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
        AppSetting.set("next_run_at", next_run)

    return jsonify({"last_run": last_run, "next_run": next_run})
