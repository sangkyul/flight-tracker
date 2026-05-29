from datetime import datetime, timedelta
from app.database import db
from app.models import PriceRecord, AlertLog


def compute_rolling_average(
    preset_id: int,
    days: int = 30,
    currency: str = "GBP",
    stops: int | None = None,
) -> float | None:
    """Return mean price over the last `days` days, or None if < 3 records.

    Pass stops=0 for direct-only average, stops=1 for connecting-only average.
    Omit stops (None) to average across all records (used by alert engine).
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = (
        db.session.query(PriceRecord.price)
        .filter(
            PriceRecord.preset_id == preset_id,
            PriceRecord.checked_at >= cutoff,
            PriceRecord.currency == currency,
        )
    )
    if stops == 0:
        q = q.filter(PriceRecord.stops == 0)
    elif stops is not None:
        q = q.filter(PriceRecord.stops > 0)
    prices = [r.price for r in q.all()]
    if len(prices) < 3:
        return None
    return sum(prices) / len(prices)


def already_alerted_today(preset_id: int) -> bool:
    today = datetime.utcnow().date()
    return (
        db.session.query(AlertLog)
        .filter(
            AlertLog.preset_id == preset_id,
            db.func.date(AlertLog.sent_at) == today,
        )
        .first()
        is not None
    )


def should_alert(
    preset,
    current_price: float,
    rolling_avg_days: int = 30,
    rolling_avg_pct: float = 5.0,
) -> tuple[bool, str, float | None]:
    """Evaluate alert conditions.

    Returns (fire: bool, reason: str, rolling_avg: float | None).
    reason is one of: 'threshold', 'rolling_avg', 'both', ''.
    """
    if already_alerted_today(preset.id):
        return False, "", None

    reasons = []

    if preset.price_threshold and current_price <= preset.price_threshold:
        reasons.append("threshold")

    from app.models import AppSetting
    currency = AppSetting.get("currency", "GBP") or "GBP"
    avg = compute_rolling_average(preset.id, days=rolling_avg_days, currency=currency)
    if avg is not None:
        pct_below = (avg - current_price) / avg * 100
        if pct_below >= rolling_avg_pct:
            reasons.append("rolling_avg")

    if len(reasons) == 2:
        return True, "both", avg
    if reasons:
        return True, reasons[0], avg
    return False, "", avg
