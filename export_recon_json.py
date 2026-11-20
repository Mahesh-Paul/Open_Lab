"""
Exports reconciliation data and dataset samples to JSON for the interactive web dashboard.
"""
import json
from datetime import datetime
from recon_engine import ReconciliationEngine

def json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def export_json():
    engine = ReconciliationEngine("platform_transactions.csv", "bank_settlements.csv", month_str="2026-10")
    metrics = engine.reconcile()
    
    # Clean datetime objects for JSON
    def clean_records(records):
        cleaned = []
        for r in records:
            item = dict(r)
            if "dt" in item:
                del item["dt"]
            cleaned.append(item)
        return cleaned

    payload = {
        "metrics": metrics,
        "timing_gaps": engine.timing_gaps,
        "duplicate_entries": engine.duplicate_platform_entries,
        "rounding_gaps": engine.rounding_gaps,
        "orphan_refunds": engine.orphan_refunds,
        "matched_sample": engine.matched[:30],
        "platform_sample": clean_records(engine.platform_records[:20]),
        "bank_sample": clean_records(engine.bank_records[:20])
    }
    
    with open("recon_data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
        
    print("Successfully exported recon_data.json")

if __name__ == "__main__":
    export_json()
