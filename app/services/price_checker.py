import logging
from datetime import datetime, date
from flask import current_app

from app.database import db
from app.models import SearchPreset, PriceRecord
from app.services.amadeus_client import fetch_all_flights

logger = logging.getLogger(__name__)


def _clean(flight: dict) -> dict:
    """Strip raw_response from a flight dict for JSON serialisation."""
    return {k: v for k, v in flight.items() if k != "raw_response"}


def check_preset(preset) -> dict:
    """Run one search cycle for a preset.

    Saves the cheapest direct and cheapest indirect price to the DB and
    returns a display-ready summary including top-5 direct and top-5
    indirect flights.
    """
    base = {
        "preset_id": preset.id,
        "preset_label": preset.label,
        "preset_route": f"{preset.origin} → {preset.destination}",
        "direct": [],
        "indirect": [],
        "checked": 0,
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
            base["error"] = (
                "SerpAPI returned no results: " + " | ".join(api_errors)
                + f" — visit /api/debug-search/{preset.id} to inspect the raw query and response."
            )
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
    for flight in filter(None, [cheapest_direct, cheapest_indirect]):
        db.session.add(_make_record(flight))

    db.session.commit()

    # Build display lists (top 5 cheapest of each type)
    direct = sorted(directs,   key=lambda f: f["price"])[:5]
    indirect = sorted(indirects, key=lambda f: f["price"])[:5]

    return {
        **base,
        "checked": len(all_flights),
        "direct":   [_clean(f) for f in direct],
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
            })
    return summaries
