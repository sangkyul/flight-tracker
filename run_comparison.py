"""One-off comparison script — runs 5 routes through the app's search layer."""
import os, sys
from types import SimpleNamespace
from datetime import date

# Exit non-zero if any route returns SerpAPI errors (mirrors run_checks.py behaviour)
_had_errors = False

os.environ["WERKZEUG_RUN_MAIN"] = "true"
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from app.services.serpapi_client import fetch_all_flights

app = create_app()

ROUTES = [
    ("LHR", "AGP", "2026-06-20", "Málaga"),
    ("LHR", "PMI", "2026-07-04", "Palma"),
    ("LHR", "JFK", "2026-08-07", "New York"),
    ("LHR", "DXB", "2026-10-24", "Dubai"),
    ("LHR", "BKK", "2026-11-28", "Bangkok"),
]

def fmt_dur(mins):
    if not mins: return "—"
    return f"{mins//60}h {mins%60:02d}m"

def fmt_time(t):
    if not t: return "—"
    parts = t.split(" ")
    return parts[-1]

with app.app_context():
    all_results = {}
    for origin, dest, dep_date, name in ROUTES:
        key = f"{origin}->{dest}"
        print(f"\nSearching {key} ({name}) on {dep_date}...", flush=True)
        preset = SimpleNamespace(
            origin=origin, destination=dest,
            depart_date_from=date.fromisoformat(dep_date),
            depart_date_to=date.fromisoformat(dep_date),
            return_date_from=None,
            cabin_class="ECONOMY", adults=1,
            direct_only=False, preferred_airline=None,
        )
        flights, errors = fetch_all_flights(preset)
        if errors:
            print(f"  SerpAPI errors: {errors}")
            _had_errors = True
        direct   = sorted([f for f in flights if f["stops"] == 0], key=lambda x: x["price"])[:5]
        indirect = sorted([f for f in flights if f["stops"] > 0],  key=lambda x: x["price"])[:5]
        all_results[key] = {"name": name, "date": dep_date, "direct": direct, "indirect": indirect, "total": len(flights)}

    print("\n" + "="*70)
    print("APP RESULTS SUMMARY")
    print("="*70)
    for key, r in all_results.items():
        print(f"\n{'─'*70}")
        print(f"  {key}  ({r['name']})  |  {r['date']}  |  {r['total']} offers found")
        print(f"{'─'*70}")
        print(f"  DIRECT (top 5 cheapest)")
        if r["direct"]:
            for i, f in enumerate(r["direct"], 1):
                carrier = f.get("airline") or f.get("carrier") or "—"
                print(f"    {i}. {carrier:30s}  {fmt_time(f.get('dep_time'))} → {fmt_time(f.get('arr_time'))}  {fmt_dur(f.get('duration_minutes')):8s}  £{f['price']:,.0f}")
        else:
            print("    No direct flights found")
        print(f"  INDIRECT (top 5 cheapest)")
        if r["indirect"]:
            for i, f in enumerate(r["indirect"], 1):
                carrier = f.get("airline") or f.get("carrier") or "—"
                stops = f.get("stops", "?")
                print(f"    {i}. {carrier:30s}  {stops} stop{'s' if stops!=1 else ''}  {fmt_dur(f.get('duration_minutes')):8s}  £{f['price']:,.0f}")
        else:
            print("    No indirect flights found")

if _had_errors:
    sys.exit(1)
