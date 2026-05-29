import json
from collections import defaultdict
from flask import Blueprint, render_template
from app.models import SearchPreset, AppSetting, PriceRecord

bp = Blueprint("dashboard", __name__)


def _latest_direct_indirect(preset_id, currency):
    """Return the most recent direct and indirect PriceRecord for a preset."""
    base = PriceRecord.query.filter(
        PriceRecord.preset_id == preset_id,
        PriceRecord.currency == currency,
    )
    direct = base.filter(PriceRecord.stops == 0).order_by(PriceRecord.checked_at.desc()).first()
    indirect = base.filter(PriceRecord.stops > 0).order_by(PriceRecord.checked_at.desc()).first()
    return {"direct": direct, "indirect": indirect}


def _preset_chart_data(preset, currency: str):
    records = (
        PriceRecord.query
        .filter_by(preset_id=preset.id, currency=currency)
        .filter(PriceRecord.checked_at >= preset.created_at)
        .order_by(PriceRecord.checked_at)
        .all()
    )
    if not records:
        return None

    by_date = defaultdict(lambda: {"direct": None, "indirect": None, "sort_key": None})
    for r in records:
        day = r.checked_at.strftime("%Y-%m-%d")
        if by_date[day]["sort_key"] is None:
            by_date[day]["sort_key"] = r.checked_at.date()
        if r.stops == 0:
            if by_date[day]["direct"] is None or r.price < by_date[day]["direct"]:
                by_date[day]["direct"] = r.price
        else:
            if by_date[day]["indirect"] is None or r.price < by_date[day]["indirect"]:
                by_date[day]["indirect"] = r.price

    labels = sorted(by_date.keys(), key=lambda d: by_date[d]["sort_key"])
    return {
        "labels": labels,
        "direct":   [by_date[d]["direct"]   for d in labels],
        "indirect": [by_date[d]["indirect"] for d in labels],
    }


@bp.get("/")
def index():
    presets = SearchPreset.query.order_by(SearchPreset.sort_order, SearchPreset.created_at.desc()).all()
    last_run = AppSetting.get("last_run_at", "Never")
    next_run = AppSetting.get("next_run_at", "Unknown")
    currency = AppSetting.get("currency", "GBP") or "GBP"
    chart_data = {p.id: _preset_chart_data(p, currency) for p in presets}
    tile_prices = {p.id: _latest_direct_indirect(p.id, currency) for p in presets}
    return render_template(
        "dashboard.html",
        presets=presets,
        last_run=last_run,
        next_run=next_run,
        chart_data_json=json.dumps(chart_data),
        tile_prices=tile_prices,
    )
