from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from app.models import AppSetting

bp = Blueprint("settings", __name__)

SETTING_KEYS = ["search_hour", "rolling_avg_days"]

DEFAULTS = {
    "search_hour": "7",
    "rolling_avg_days": "30",
}


@bp.get("/settings")
def view():
    settings = {k: AppSetting.get(k, DEFAULTS.get(k, "")) for k in SETTING_KEYS}
    serpapi_key = current_app.config.get("SERPAPI_KEY", "")
    masked_key = (serpapi_key[:4] + "****" + serpapi_key[-4:]) if len(serpapi_key) >= 8 else "Not configured"
    return render_template("settings.html", settings=settings, masked_key=masked_key)


@bp.post("/settings")
def save():
    errors = []

    hour = request.form.get("search_hour", "7").strip()
    try:
        h = int(hour)
        if not 0 <= h <= 23:
            raise ValueError
    except ValueError:
        errors.append("Search hour must be a number between 0 and 23.")

    days = request.form.get("rolling_avg_days", "30").strip()
    try:
        d = int(days)
        if d < 1:
            raise ValueError
    except ValueError:
        errors.append("Rolling average window must be a positive integer.")

    if errors:
        settings = {k: request.form.get(k, DEFAULTS.get(k, "")) for k in SETTING_KEYS}
        masked_key = "****"
        for err in errors:
            flash(err, "danger")
        return render_template("settings.html", settings=settings, masked_key=masked_key)

    AppSetting.set("search_hour", hour)
    AppSetting.set("rolling_avg_days", days)

    try:
        from app.scheduler import reschedule_daily_job
        reschedule_daily_job(int(hour))
    except Exception:
        pass

    flash("Settings saved.", "success")
    return redirect(url_for("settings.view"))
