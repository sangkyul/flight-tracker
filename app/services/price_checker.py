import logging
from datetime import datetime, date
from flask import current_app

from app.database import db
from app.models import SearchPreset, PriceRecord, AlertLog, AppSetting
from app.services.amadeus_client import fetch_all_flights
from app.services.alert_engine import should_alert
from app.services.email_service import send_alert

logger = logging.getLogger(__name__)


def _get_setting(key, default):
    val = AppSetting.get(key)
    if val is None:
        return default
    try:
        return type(default)(val)
    except (ValueError, TypeError):
        return default


def _clean(flight: dict) -> dict:
    """Strip raw_response from a flight dict for JSON serialisation."""
    return {k: v for k, v in flight.items() if k != "raw_response"}


def check_preset(preset) -> dict:
    """Run one search cycle for a preset.

    Saves the cheapest price to the DB, fires an alert if warranted,
    and returns a display-ready summary including top-5 direct and
    top-5 non-direct flights.
    """
    base = {
        "preset_id": preset.id,
        "preset_label": preset.label,
        "preset_route": f"{preset.origin} → {preset.destination}",
        "direct": [],
        "indirect": [],
        "checked": 0,
        "alerted": False,
    }

    if not current_app.config.get("SERPAPI_KEY", ""):
        base["error"] = (
            "SERPAPI_KEY is not configured. "
            "Add SERPAPI_KEY=your_key to your .env file and restart the server."
        )
        return base

    all_flights, api_errors = fetch_all_flights(preset)

    if not all_flights:
        if api_errors:
            # SerpAPI returned explicit error messages — surface them instead of "no results"
            base["error"] = "SerpAPI returned no results: " + " | ".join(api_errors)
        elif preset.depart_date_to < date.today():
            base["error"] = (
                "All departure dates are in the past — edit the route to use future dates."
            )
        return base

    now = datetime.utcnow()
    directs   = [f for f in all_flights if f["stops"] == 0]
    indirects = [f for f in all_flights if f["stops"] > 0]
    cheapest_direct   = min(directs,   key=lambda f: f["price"]) if directs   else None
    cheapest_indirect = min(indirects, key=lambda f: f["price"]) if indirects else None
    cheapest = min(all_flights, key=lambda f: f["price"])

    def _make_record(flight):
        outbound_date = None
        raw = flight.get("outbound_date")
        if raw:
            try:
                outbound_date = date.fromisoformat(raw)
            except ValueError:
                pass
        raw_response = flight.get("raw_response")
        if raw_response and len(raw_response) > 2000:
            raw_response = raw_response[:2000]
        return PriceRecord(
            preset_id=preset.id,
            checked_at=now,
            price=flight["price"],
            currency=flight.get("currency", "GBP"),
            carrier=flight.get("carrier"),
            outbound_date=outbound_date,
            stops=flight.get("stops", 0),
            raw_response=raw_response,
        )

    # Save cheapest direct and cheapest indirect separately for charting
    direct_record = None
    indirect_record = None
    for flight in filter(None, [cheapest_direct, cheapest_indirect]):
        r = _make_record(flight)
        db.session.add(r)
        if flight is cheapest_direct:
            direct_record = r
        else:
            indirect_record = r
    db.session.flush()

    # Alert record matches whichever flight is the overall cheapest
    if cheapest is cheapest_direct:
        alert_record = direct_record
    elif cheapest is cheapest_indirect:
        alert_record = indirect_record
    else:
        alert_record = direct_record or indirect_record

    # --- Alert logic (based on overall cheapest price) ---
    rolling_avg_days = _get_setting("rolling_avg_days", 30)
    rolling_avg_pct  = _get_setting("rolling_avg_pct", 5.0)
    alert_email = AppSetting.get("alert_email") or current_app.config["ALERT_EMAIL"]

    fire, reason, avg = should_alert(
        preset, cheapest["price"],
        rolling_avg_days=rolling_avg_days,
        rolling_avg_pct=rolling_avg_pct,
    )

    alerted = False
    if fire and alert_record:
        success = send_alert(preset, alert_record, reason, avg)
        if success:
            db.session.add(AlertLog(
                preset_id=preset.id,
                price_record_id=alert_record.id,
                sent_at=datetime.utcnow(),
                trigger_reason=reason,
                email_recipient=alert_email,
            ))
            alerted = True

    db.session.commit()

    # --- Build display lists ---
    direct = sorted(
        [f for f in all_flights if f["stops"] == 0], key=lambda f: f["price"]
    )[:5]
    indirect = sorted(
        [f for f in all_flights if f["stops"] > 0], key=lambda f: f["price"]
    )[:5]

    return {
        **base,
        "checked": len(all_flights),
        "alerted": alerted,
        "direct": [_clean(f) for f in direct],
        "indirect": [_clean(f) for f in indirect],
    }


def run_all_active_presets() -> list[dict]:
    """Called by the scheduler and the manual trigger endpoint."""
    presets = SearchPreset.query.filter_by(active=True).all()
    summaries = []
    for preset in presets:
        try:
            summary = check_preset(preset)
            summaries.append(summary)
        except Exception as exc:
            logger.error("Error checking preset %d: %s", preset.id, exc)
            db.session.rollback()
            summaries.append({
                "preset_id": preset.id,
                "preset_label": getattr(preset, "label", ""),
                "preset_route": f"{preset.origin} → {preset.destination}",
                "error": str(exc),
                "direct": [],
                "indirect": [],
                "checked": 0,
                "alerted": False,
            })
    return summaries
