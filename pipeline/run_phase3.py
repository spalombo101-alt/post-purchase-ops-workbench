"""Phase 3 orchestrator: outreach queue + analytics. Reads raw/ and
Phase 1/2's clean/ outputs; writes the rest of clean/.

Run with:  python3 -m pipeline.run_phase3
"""
import json
import os

import pandas as pd

from pipeline.ingest import load_raw, normalize_orders, normalize_returns, build_unified_customer_records
from pipeline.spine import ref_to_customer_id_map
from pipeline.outreach_queue import compute_outreach_queue
from pipeline.analytics import time_lost_analytics, return_reason_clustering, outreach_comparison

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(PROJECT_ROOT, "clean")


def main():
    print("Loading raw + Phase 1/2 outputs...")
    dfs = load_raw()
    customers = pd.read_csv(os.path.join(CLEAN_DIR, "customers_enriched.csv"), keep_default_na=False)
    return_windows = pd.read_csv(os.path.join(CLEAN_DIR, "return_windows.csv"), keep_default_na=False)
    pending_detail = pd.read_csv(os.path.join(CLEAN_DIR, "pending_returns_detail.csv"), keep_default_na=False)
    spine_df = pd.read_csv(os.path.join(CLEAN_DIR, "customers_spine.csv"), keep_default_na=False)
    ref_map = ref_to_customer_id_map(spine_df)
    unified = build_unified_customer_records(dfs["pos_customers"], dfs["ecom_customers"])

    print("Computing outreach queue...")
    outreach_queue, excluded_no_consent = compute_outreach_queue(
        customers, return_windows, dfs["call_log"], pending_detail, dfs["product_catalog"], unified, ref_map
    )

    print("Computing analytics...")
    time_lost = time_lost_analytics(dfs["call_log"])
    reason_clustering = return_reason_clustering(dfs["returns"], dfs["product_catalog"])
    outreach_cmp = outreach_comparison(dfs["outreach_log"], outreach_queue)

    outreach_queue.to_csv(os.path.join(CLEAN_DIR, "outreach_queue.csv"), index=False)
    reason_clustering.to_csv(os.path.join(CLEAN_DIR, "return_reason_clustering.csv"), index=False)

    summary = {
        "excluded_no_consent": excluded_no_consent,
        "time_lost": {k: v for k, v in time_lost.items() if k != "by_store"},
        "time_lost_by_store": time_lost["by_store"].to_dict(orient="records"),
        "outreach_comparison": outreach_cmp,
    }
    with open(os.path.join(CLEAN_DIR, "analytics_summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"  wrote clean/outreach_queue.csv  ({len(outreach_queue)} rows, "
          f"{excluded_no_consent} excluded for no consented contact channel)")
    print(f"  wrote clean/return_reason_clustering.csv  ({len(reason_clustering)} styles)")
    print(f"  wrote clean/analytics_summary.json")
    print(f"\nAssociate time lost to return-window calls: {time_lost['hours_per_week']} hrs/week "
          f"({time_lost['share_of_all_calls']:.0%} of all calls)")

    return outreach_queue, reason_clustering, summary


if __name__ == "__main__":
    main()
