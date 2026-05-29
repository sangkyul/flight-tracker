import os
import logging
from sqlalchemy import text
from app import create_app
from app.database import db
from app.scheduler import init_scheduler, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = create_app()


def seed_default_settings():
    from app.models import AppSetting
    defaults = {
        "search_hour": "7",
        "rolling_avg_days": "30",
        "rolling_avg_pct": "5",
        "alert_email": app.config.get("ALERT_EMAIL", ""),
        "currency": "GBP",
        "last_run_at": "Never",
        "next_run_at": "Unknown",
    }
    for key, value in defaults.items():
        if db.session.get(AppSetting, key) is None:
            db.session.add(AppSetting(key=key, value=value))
    # Force rolling_avg_pct to 5 if it's still at the old 20 default
    row = db.session.get(AppSetting, "rolling_avg_pct")
    if row and row.value == "20":
        row.value = "5"
    db.session.commit()


with app.app_context():
    os.makedirs(os.path.join(os.path.dirname(__file__), "instance"), exist_ok=True)
    db.create_all()
    seed_default_settings()
    # Add sort_order column if upgrading from an older DB
    try:
        db.session.execute(text("ALTER TABLE search_preset ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"))
        db.session.commit()
        logging.info("DB migration: added sort_order column to search_preset")
    except Exception as exc:
        db.session.rollback()
        if "duplicate column" not in str(exc).lower() and "already exists" not in str(exc).lower():
            logging.warning("DB migration warning: %s", exc)

# Scheduler is disabled in production (GitHub Actions handles scheduling).
# Set ENABLE_SCHEDULER=true to run the built-in scheduler locally.
_enable_scheduler = os.environ.get("ENABLE_SCHEDULER", "false").lower() == "true"
if _enable_scheduler and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    init_scheduler(app)

if __name__ == "__main__":
    try:
        app.run(debug=True, use_reloader=False, host="0.0.0.0", port=5000)
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
