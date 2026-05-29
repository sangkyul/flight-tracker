import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import current_app, render_template

logger = logging.getLogger(__name__)

CURRENCY_SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€"}


def send_alert(preset, price_record, reason: str, rolling_avg: float | None) -> bool:
    """Send an HTML alert email. Returns True on success, False on failure."""
    gmail_address = current_app.config["GMAIL_ADDRESS"]
    gmail_password = current_app.config["GMAIL_APP_PASSWORD"]
    recipient = current_app.config["ALERT_EMAIL"] or gmail_address

    if not gmail_address or not gmail_password:
        logger.warning("Alert skipped — GMAIL_ADDRESS or GMAIL_APP_PASSWORD not configured")
        return False

    sym = CURRENCY_SYMBOLS.get(price_record.currency, price_record.currency)
    price_str = f"{sym}{price_record.price:,.0f} {price_record.currency}"
    subject = (
        f"Flight Deal: {preset.origin} → {preset.destination} — {price_str}"
    )

    html_body = render_template(
        "email/alert.html",
        preset=preset,
        record=price_record,
        reason=reason,
        rolling_avg=rolling_avg,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_password)
            server.send_message(msg)
        logger.info("Alert email sent to %s for %s→%s", recipient, preset.origin, preset.destination)
        return True
    except Exception as exc:
        logger.error("Failed to send alert email to %s: %s", recipient, exc)
        return False
