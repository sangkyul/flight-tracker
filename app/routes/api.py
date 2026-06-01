from datetime import datetime, date, timedelta
from urllib.parse import urlencode
import requests as req_lib
from flask import Blueprint, jsonify, request, current_app
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


@bp.get("/api/debug-search/<int:preset_id>")
def debug_search(preset_id):
    """Fire a raw SerpAPI call for the preset's first future date and return
    exactly what was sent and what came back. Use this to diagnose 'no results'
    issues without digging through server logs."""
    from app.services.amadeus_client import CABIN_CLASS_MAP, CITY_TO_AIRPORT, SERPAPI_URL, _get_currency

    preset = db.get_or_404(SearchPreset, preset_id)
    api_key = current_app.config.get("SERPAPI_KEY", "")
    if not api_key:
        return jsonify({"error": "SERPAPI_KEY is not configured"}), 500

    # Find the first date in the window that is today or later
    today = date.today()
    d = preset.depart_date_from
    while d < today and d <= preset.depart_date_to:
        d += timedelta(days=1)

    if d > preset.depart_date_to:
        return jsonify({
            "error": "All departure dates in this preset are in the past.",
            "depart_date_from": preset.depart_date_from.isoformat(),
            "depart_date_to": preset.depart_date_to.isoformat(),
        }), 400

    # Apply same city-code resolution as the real search
    origin_id = CITY_TO_AIRPORT.get(preset.origin, preset.origin)
    destination_id = CITY_TO_AIRPORT.get(preset.destination, preset.destination)

    is_round_trip = bool(preset.return_date_from)
    params = {
        "engine": "google_flights",
        "departure_id": origin_id,
        "arrival_id": destination_id,
        "outbound_date": d.isoformat(),
        "type": 1 if is_round_trip else 2,
        "travel_class": CABIN_CLASS_MAP.get(preset.cabin_class, 1),
        "adults": preset.adults,
        "currency": _get_currency(),
        "api_key": api_key,
    }
    if is_round_trip:
        params["return_date"] = preset.return_date_from.isoformat()
    if preset.direct_only:
        params["stops"] = 1
    if preset.preferred_airline:
        params["include_airlines"] = preset.preferred_airline.upper()

    # Params without the API key — safe to log / display
    safe_params = {k: v for k, v in params.items() if k != "api_key"}

    try:
        resp = req_lib.get(SERPAPI_URL, params=params, timeout=30)
        data = resp.json()
    except Exception as exc:
        return jsonify({"params_sent": safe_params, "error": str(exc)}), 500

    best  = data.get("best_flights", [])
    other = data.get("other_flights", [])
    all_flights = best + other

    substitutions = {}
    if origin_id != preset.origin:
        substitutions[preset.origin] = origin_id
    if destination_id != preset.destination:
        substitutions[preset.destination] = destination_id

    return jsonify({
        "preset": {
            "id": preset.id,
            "label": preset.label,
            "route": f"{preset.origin} → {preset.destination}",
            "cabin_class": preset.cabin_class,
            "travel_class_code": CABIN_CLASS_MAP.get(preset.cabin_class, 1),
            "direct_only": preset.direct_only,
            "preferred_airline": preset.preferred_airline,
        },
        "city_code_substitutions": substitutions,
        "date_searched": d.isoformat(),
        "params_sent": safe_params,
        "serpapi_response": {
            "http_status": resp.status_code,
            "top_level_keys": list(data.keys()),
            "serpapi_error": data.get("error"),
            "best_flights_count": len(best),
            "other_flights_count": len(other),
            "total_offers": len(all_flights),
            "sample_prices": sorted(set(f["price"] for f in all_flights if "price" in f))[:5],
        },
        # Paste this into your browser to test the same query in the SerpAPI playground
        "playground_url": f"https://serpapi.com/playground?{urlencode(safe_params)}",
    })


@bp.get("/api/status")
def status():
    last_run = AppSetting.get("last_run_at", "Never")
    next_run = AppSetting.get("next_run_at", "Unknown")

    job = scheduler.get_job("daily_price_check")
    if job and job.next_run_time:
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M UTC")
        AppSetting.set("next_run_at", next_run)

    return jsonify({"last_run": last_run, "next_run": next_run})
