from datetime import date, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from app.database import db
from app.models import SearchPreset, PriceRecord

bp = Blueprint("presets", __name__)

CABIN_CLASSES = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"]


def _parse_date(val: str) -> date | None:
    if not val:
        return None
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        return None


def _validate_preset(form) -> list[str]:
    errors = []
    origin = form.get("origin", "").strip().upper()
    destination = form.get("destination", "").strip().upper()

    if len(origin) != 3 or not origin.isalpha():
        errors.append("Origin must be a 3-letter IATA code (e.g. JFK).")
    if len(destination) != 3 or not destination.isalpha():
        errors.append("Destination must be a 3-letter IATA code (e.g. LHR).")
    if origin and destination and origin == destination:
        errors.append("Origin and destination must be different.")

    df = _parse_date(form.get("depart_date_from"))
    dt = _parse_date(form.get("depart_date_to"))
    if not df:
        errors.append("Departure start date is required.")
    if df:
        if df < date.today():
            errors.append("Departure start date must be today or later.")
        if dt:
            if dt < df:
                errors.append("Departure end date must be on or after start date.")
            elif (dt - df).days > 14:
                errors.append("Departure window cannot exceed 14 days (API quota limit).")

    rf = _parse_date(form.get("return_date_from"))
    rt = _parse_date(form.get("return_date_to"))
    if rf:
        if df and rf <= df:
            errors.append("Return date must be after the departure date.")
        if rt and rt < rf:
            errors.append("Return end date must be on or after return start date.")

    cabin = form.get("cabin_class", "ECONOMY")
    if cabin not in CABIN_CLASSES:
        errors.append("Invalid cabin class.")

    airline = form.get("preferred_airline", "").strip().upper()
    if airline and (len(airline) != 2 or not airline.isalpha()):
        errors.append("Preferred airline must be a 2-letter IATA carrier code (e.g. BA).")

    threshold = form.get("price_threshold", "").strip()
    if threshold:
        try:
            v = float(threshold)
            if v <= 0:
                errors.append("Price threshold must be a positive number.")
        except ValueError:
            errors.append("Price threshold must be a number.")

    return errors


def _build_preset_from_form(form) -> dict:
    threshold = form.get("price_threshold", "").strip()
    airline = form.get("preferred_airline", "").strip().upper()
    return {
        "label": form.get("label", "").strip() or f"{form.get('origin','').upper()}→{form.get('destination','').upper()}",
        "origin": form.get("origin", "").strip().upper(),
        "destination": form.get("destination", "").strip().upper(),
        "depart_date_from": _parse_date(form.get("depart_date_from")),
        "depart_date_to": _parse_date(form.get("depart_date_to")) or _parse_date(form.get("depart_date_from")),
        "return_date_from": _parse_date(form.get("return_date_from")) or None,
        "return_date_to": _parse_date(form.get("return_date_to")) or _parse_date(form.get("return_date_from")) or None,
        "cabin_class": form.get("cabin_class", "ECONOMY"),
        "adults": max(1, int(form.get("adults", 1) or 1)),
        "direct_only": bool(form.get("direct_only")),
        "preferred_airline": airline if airline else None,
        "price_threshold": float(threshold) if threshold else None,
    }


@bp.get("/presets/new")
def new_form():
    return render_template("preset_form.html", preset=None, cabin_classes=CABIN_CLASSES, errors=[])


@bp.post("/presets/new")
def create():
    errors = _validate_preset(request.form)
    if errors:
        return render_template("preset_form.html", preset=None, cabin_classes=CABIN_CLASSES,
                               errors=errors, form=request.form)
    data = _build_preset_from_form(request.form)
    preset = SearchPreset(**data)
    db.session.add(preset)
    db.session.commit()
    flash(f"Route '{preset.label}' added — running first search now.", "success")
    return redirect(url_for("dashboard.index", autorun=1))


@bp.get("/presets/<int:preset_id>/edit")
def edit_form(preset_id):
    preset = db.get_or_404(SearchPreset, preset_id)
    return render_template("preset_form.html", preset=preset, cabin_classes=CABIN_CLASSES, errors=[])


@bp.post("/presets/<int:preset_id>/edit")
def update(preset_id):
    preset = db.get_or_404(SearchPreset, preset_id)
    errors = _validate_preset(request.form)
    if errors:
        return render_template("preset_form.html", preset=preset, cabin_classes=CABIN_CLASSES,
                               errors=errors, form=request.form)
    data = _build_preset_from_form(request.form)
    # If the label was the old auto-generated "ORIGIN→DESTINATION", update it
    old_auto_label = f"{preset.origin}→{preset.destination}"
    if data["label"] == old_auto_label or not data["label"]:
        new_origin = request.form.get("origin", "").strip().upper()
        new_dest = request.form.get("destination", "").strip().upper()
        data["label"] = f"{new_origin}→{new_dest}"
    for key, val in data.items():
        setattr(preset, key, val)
    # Clear history and reset tracking start date
    PriceRecord.query.filter_by(preset_id=preset_id).delete()
    preset.created_at = datetime.utcnow()
    db.session.commit()
    flash(f"Route '{preset.label}' updated — history cleared, running fresh search now.", "success")
    return redirect(url_for("dashboard.index", autorun=1))


@bp.post("/presets/<int:preset_id>/delete")
def delete(preset_id):
    preset = db.get_or_404(SearchPreset, preset_id)
    label = preset.label
    db.session.delete(preset)
    db.session.commit()
    flash(f"Preset '{label}' deleted.", "info")
    return redirect(url_for("dashboard.index"))


@bp.post("/presets/<int:preset_id>/toggle")
def toggle(preset_id):
    preset = db.get_or_404(SearchPreset, preset_id)
    preset.active = not preset.active
    db.session.commit()
    return jsonify({"active": preset.active})
