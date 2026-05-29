import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
_app = None  # set by init_scheduler; avoids pickling the app into the job store


def _run_daily_checks():
    with _app.app_context():
        from app.services.price_checker import run_all_active_presets
        from app.models import AppSetting
        logger.info("Daily price check started at %s UTC", datetime.utcnow())
        summaries = run_all_active_presets()
        AppSetting.set("last_run_at", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        logger.info("Daily price check complete — %d preset(s) checked", len(summaries))


def init_scheduler(app):
    global _app
    _app = app

    hour = int(app.config.get("SEARCH_HOUR", 7))
    scheduler.add_job(
        func=_run_daily_checks,
        trigger=CronTrigger(hour=hour, minute=0),
        id="daily_price_check",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("Scheduler started — daily check at %02d:00 UTC", hour)


def reschedule_daily_job(hour: int):
    job = scheduler.get_job("daily_price_check")
    if job:
        job.reschedule(trigger=CronTrigger(hour=hour, minute=0))
        logger.info("Rescheduled daily job to %02d:00 UTC", hour)
