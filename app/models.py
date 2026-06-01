from datetime import datetime
from app.database import db


class SearchPreset(db.Model):
    __tablename__ = "search_preset"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), nullable=False)
    origin = db.Column(db.String(3), nullable=False)
    destination = db.Column(db.String(3), nullable=False)
    depart_date_from = db.Column(db.Date, nullable=False)
    depart_date_to = db.Column(db.Date, nullable=False)
    return_date_from = db.Column(db.Date, nullable=True)
    return_date_to = db.Column(db.Date, nullable=True)
    cabin_class = db.Column(db.String(20), nullable=False, default="ECONOMY")
    adults = db.Column(db.Integer, nullable=False, default=1)
    direct_only = db.Column(db.Boolean, nullable=False, default=False)
    preferred_airline = db.Column(db.String(2), nullable=True)
    price_threshold = db.Column(db.Float, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    price_records = db.relationship(
        "PriceRecord", backref="preset", cascade="all, delete-orphan", lazy="select"
    )

    @property
    def latest_price(self):
        return (
            db.session.query(PriceRecord)
            .filter(PriceRecord.preset_id == self.id)
            .order_by(PriceRecord.checked_at.desc())
            .first()
        )

    @property
    def is_round_trip(self):
        return self.return_date_from is not None


class PriceRecord(db.Model):
    __tablename__ = "price_record"

    id = db.Column(db.Integer, primary_key=True)
    preset_id = db.Column(
        db.Integer, db.ForeignKey("search_preset.id", ondelete="CASCADE"), nullable=False
    )
    checked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    price = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="USD")
    carrier = db.Column(db.String(2), nullable=True)
    outbound_date = db.Column(db.Date, nullable=True)
    return_date = db.Column(db.Date, nullable=True)
    stops = db.Column(db.Integer, nullable=False, default=0)
    raw_response = db.Column(db.Text, nullable=True)

class AppSetting(db.Model):
    __tablename__ = "app_settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=False)

    @classmethod
    def get(cls, key, default=None):
        row = db.session.get(cls, key)
        return row.value if row else default

    @classmethod
    def set(cls, key, value):
        row = db.session.get(cls, key)
        if row:
            row.value = str(value)
        else:
            db.session.add(cls(key=key, value=str(value)))
        db.session.commit()
