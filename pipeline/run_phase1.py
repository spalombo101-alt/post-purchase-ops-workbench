"""Phase 1 orchestrator: ingest raw/ -> build the spine -> write clean/.

Run with:  python3 -m pipeline.run_phase1
"""
import os

import pandas as pd

from pipeline.ingest import load_raw, build_unified_customer_records
from pipeline.spine import build_spine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(PROJECT_ROOT, "clean")


def main():
    os.makedirs(CLEAN_DIR, exist_ok=True)

    print("Loading raw CSVs...")
    dfs = load_raw()

    print("Normalizing pos_customers + ecom_customers into a unified record set...")
    unified = build_unified_customer_records(dfs["pos_customers"], dfs["ecom_customers"])
    print(f"  {len(unified)} total source records "
          f"({(unified.source_type == 'pos').sum()} pos, {(unified.source_type == 'ecom').sum()} ecom)")

    print("Building the spine (three-tier entity resolution)...")
    spine_df, review_df, ref_to_customer_id = build_spine(unified, dfs["payment_tokens"])

    spine_path = os.path.join(CLEAN_DIR, "customers_spine.csv")
    review_path = os.path.join(CLEAN_DIR, "review_queue.csv")
    spine_df.to_csv(spine_path, index=False)
    review_df.to_csv(review_path, index=False)

    print(f"  wrote {spine_path}  ({len(spine_df)} resolved customers)")
    print(f"  wrote {review_path}  ({len(review_df)} pending human review)")
    print(spine_df["resolution_tier"].value_counts().to_string())

    return spine_df, review_df, ref_to_customer_id, unified


if __name__ == "__main__":
    main()
