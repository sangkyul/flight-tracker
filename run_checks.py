#!/usr/bin/env python3
"""Standalone price-check runner — called by GitHub Actions daily cron."""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from app import create_app
from app.database import db
from app.services.price_checker import run_all_active_presets

app = create_app()

with app.app_context():
    db.create_all()  # no-op if tables already exist
    logger.info("Starting scheduled price checks...")
    results = run_all_active_presets()

    errors = 0
    for r in results:
        if r.get("error"):
            logger.error("Preset '%s' failed: %s", r.get("preset_label"), r.get("error"))
            errors += 1
        else:
            logger.info(
                "Preset '%s': %d flights found",
                r.get("preset_label"), r.get("checked", 0),
            )

    logger.info("Done. %d preset(s) checked, %d error(s).", len(results), errors)
    if errors:
        sys.exit(1)
