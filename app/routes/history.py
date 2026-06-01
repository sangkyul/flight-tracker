import json
from collections import defaultdict
from datetime import datetime
from flask import Blueprint, render_template
from app.database import db
from app.models import SearchPreset, PriceRecord, AppSetting
from app.services.analytics import compute_rolling_average

bp = Blueprint("history", __name__)


@bp.get("/history/<int:preset_id>")
def view(preset_id):
    preset = db.get_or_404(SearchPreset, preset_id)
    current_currency = AppSetting.get("currency", "GBP") or "GBP"
    records = (
        PriceRecord.query
        .filter_by(preset_id=preset_id, currency=current_currency)
        .order_by(PriceRecord.checked_at.desc())
        .all()
    )

    prices = [r.price for r in records]
    record_currency = records[0].currency if records else None
    lowest_price          = min(prices) if prices else None
    rolling_avg_direct    = compute_rolling_average(preset_id, currency=current_currency, stops=0)
    rolling_avg_indirect  = compute_rolling_average(preset_id, currency=current_currency, stops=1)

    # Latest price: most recent direct, fallback to most recent indirect
    latest_direct   = next((r for r in records if r.stops == 0), None)
    latest_indirect = next((r for r in records if r.stops > 0),  None)
    latest_price = (latest_direct or latest_indirect).price if (latest_direct or latest_indirect) else None

    # Group records by check timestamp (direct + connecting side-by-side)
    by_check: dict = {}
    for r in records:  # already ordered desc
        key = r.checked_at.replace(microsecond=0)
        if key not in by_check:
            by_check[key] = {"checked_at": r.checked_at, "direct": None, "indirect": None}
        if r.stops == 0:
            by_check[key]["direct"] = r
        else:
            by_check[key]["indirect"] = r
    grouped_records = list(by_check.values())

    # Build chart series: one point per day, cheapest direct + cheapest indirect
    by_date = defaultdict(lambda: {"direct": None, "indirect": None})
    for r in records:
        day = r.checked_at.strftime("%Y-%m-%d")
        if r.stops == 0:
            if by_date[day]["direct"] is None or r.price < by_date[day]["direct"]:
                by_date[day]["direct"] = r.price
        else:
            if by_date[day]["indirect"] is None or r.price < by_date[day]["indirect"]:
                by_date[day]["indirect"] = r.price

    chart_days     = sorted(by_date.keys())
    chart_labels   = [datetime.strptime(d, "%Y-%m-%d").strftime("%b %d") for d in chart_days]
    chart_direct   = [by_date[d]["direct"]   for d in chart_days]
    chart_indirect = [by_date[d]["indirect"] for d in chart_days]

    return render_template(
        "history.html",
        preset=preset,
        records=records,
        grouped_records=grouped_records,
        latest_price=latest_price,
        record_currency=record_currency,
        lowest_price=lowest_price,
        rolling_avg_direct=rolling_avg_direct,
        rolling_avg_indirect=rolling_avg_indirect,
        chart_labels=json.dumps(chart_labels),
        chart_direct=json.dumps(chart_direct),
        chart_indirect=json.dumps(chart_indirect),
    )
