from datetime import datetime, timedelta
from app.database import db
from app.models import PriceRecord


def compute_rolling_average(
    preset_id: int,
    days: int = 30,
    currency: str = "GBP",
    stops: int | None = None,
) -> float | None:
    """Return mean price over the last `days` days, or None if < 3 records.

    Pass stops=0 for direct-only average, stops=1 for connecting-only average.
    Omit stops (None) to average across all records.
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
