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
        "currency": "GBP",
        "last_run_at": "Never",
        "next_run_at": "Unknown",
    }
    for key, value in defaults.items():
        if db.session.get(AppSetting, key) is None:
            db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


with app.app_context():
    # instance/ dir only needed for local SQLite. Decide from the resolved DB URI
    # (not just the env var) and never let a read-only serverless filesystem
    # (e.g. Vercel's /var/task) crash startup.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        try:
            os.makedirs(os.path.join(os.path.dirname(__file__), "instance"), exist_ok=True)
        except OSError as exc:
            logging.warning("Could not create instance dir (read-only FS?): %s", exc)
    db.create_all()
    # Note: the `alert_log` table may still exist in the database from earlier
    # versions. It is intentionally unused — the AlertLog model and all alert
    # logic were removed. The table can be dropped manually if desired:
    #   DROP TABLE IF EXISTS alert_log;
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
