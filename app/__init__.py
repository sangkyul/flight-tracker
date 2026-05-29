from flask import Flask
from app.database import db

CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€"}


def create_app(config_object="config.Config"):
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    db.init_app(app)

    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.presets import bp as presets_bp
    from app.routes.history import bp as history_bp
    from app.routes.settings import bp as settings_bp
    from app.routes.api import bp as api_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(presets_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_currency():
        from app.models import AppSetting
        try:
            cur = AppSetting.get("currency", "GBP") or "GBP"
        except Exception:
            cur = "GBP"
        return {
            "current_currency": cur,
            "current_currency_symbol": CURRENCY_SYMBOLS.get(cur, "£"),
        }

    @app.template_filter("currency_sym")
    def currency_sym_filter(code):
        return CURRENCY_SYMBOLS.get(code, code or "£")

    @app.template_filter("fmt_price")
    def fmt_price_filter(value):
        if value is None:
            return "—"
        return f"{value:,.0f}"

    @app.template_filter("as_date_str")
    def as_date_str_filter(value):
        if not value:
            return ""
        if isinstance(value, str):
            return value
        return value.isoformat()

    return app
