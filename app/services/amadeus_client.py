import json
import logging
import time
from datetime import date, timedelta

import requests
from flask import current_app

logger = logging.getLogger(__name__)
SERPAPI_URL = "https://serpapi.com/search"


def _get_currency() -> str:
    from app.models import AppSetting
    return AppSetting.get("currency", "GBP") or "GBP"


CABIN_CLASS_MAP = {
    "ECONOMY": 1,
    "PREMIUM_ECONOMY": 2,
    "BUSINESS": 3,
    "FIRST": 4,
}



def _fetch_flights_for_date(preset, departure_date: date) -> tuple[list[dict], str | None]:
    """Return (flights, error_or_None) for a single departure date."""
    api_key = current_app.config.get("SERPAPI_KEY", "")
    if not api_key:
        return [], None  # handled upstream

    is_round_trip = bool(preset.return_date_from)
    params = {
        "engine": "google_flights",
        "departure_id": preset.origin,
        "arrival_id": preset.destination,
        "outbound_date": departure_date.isoformat(),
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

    # Log everything except the API key so it's easy to reproduce in a browser/curl
    log_params = {k: v for k, v in params.items() if k != "api_key"}
    logger.info("SerpAPI search: %s", log_params)

    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        logger.debug("SerpAPI response keys: %s", list(data.keys()))
        if "error" in data:
            msg = data["error"]
            logger.warning("SerpAPI error for %s→%s %s (class=%s): %s",
                           preset.origin, preset.destination, departure_date,
                           preset.cabin_class, msg)
            return [], msg
    except Exception as exc:
        logger.error("SerpAPI request failed for %s→%s %s (class=%s): %s",
                     preset.origin, preset.destination, departure_date,
                     preset.cabin_class, exc)
        return [], None

    raw_offers = data.get("best_flights", []) + data.get("other_flights", [])
    results = []

    for offer in raw_offers:
        price = offer.get("price")
        if price is None:
            continue

        segments = offer.get("flights", [])
        layovers = offer.get("layovers", [])
        stops = len(layovers)

        carrier = None
        airline_name = None
        if segments:
            airline_name = segments[0].get("airline", "")
            fn = segments[0].get("flight_number", "")
            carrier = "".join(c for c in fn if c.isalpha())[:2].upper() or None

        dep_time = ""
        arr_time = ""
        if segments:
            dep_time = segments[0].get("departure_airport", {}).get("time", "")
            arr_time = segments[-1].get("arrival_airport", {}).get("time", "")

        duration = offer.get("total_duration", 0)

        results.append({
            "price": float(price),
            "currency": _get_currency(),
            "carrier": carrier,
            "airline": airline_name,
            "stops": stops,
            "outbound_date": departure_date.isoformat(),
            "dep_time": dep_time,
            "arr_time": arr_time,
            "duration_minutes": duration,
            "raw_response": json.dumps(offer),
        })

    return sorted(results, key=lambda f: f["price"]), None


def fetch_all_flights(preset) -> tuple[list[dict], list[str]]:
    """Search every date in the preset's departure window.

    Returns (flights, errors) where errors is a deduplicated list of any
    SerpAPI error messages received across the date range.
    """
    all_results: list[dict] = []
    errors: list[str] = []
    today = date.today()
    d = preset.depart_date_from

    while d <= preset.depart_date_to:
        if d >= today:
            day_results, error = _fetch_flights_for_date(preset, d)
            all_results.extend(day_results)
            if error and error not in errors:
                errors.append(error)
            time.sleep(0.5)
        d += timedelta(days=1)

    return all_results, errors


