"""Phase 2 orchestrator: customer history + judgment fields, return
windows, true inventory. Reads clean/customers_spine.csv from Phase 1
and raw/*.csv; writes the rest of clean/.

Run with:  python3 -m pipeline.run_phase2
"""
import os

import pandas as pd

from pipeline.ingest import load_raw, normalize_orders, normalize_returns
from pipeline.spine import ref_to_customer_id_map
from pipeline.customer_history import compute_customer_history
from pipeline.judgment_fields import add_judgment_fields
from pipeline.return_windows import compute_return_windows
from pipeline.true_inventory import compute_true_inventory

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(PROJECT_ROOT, "clean")


def main():
    os.makedirs(CLEAN_DIR, exist_ok=True)

    print("Loading raw + Phase 1 spine...")
    dfs = load_raw()
    orders = normalize_orders(dfs["orders"])
    returns = normalize_returns(dfs["returns"])
    spine_df = pd.read_csv(os.path.join(CLEAN_DIR, "customers_spine.csv"), keep_default_na=False)
    ref_map = ref_to_customer_id_map(spine_df)
    orders["customer_id"] = orders["source_customer_ref"].map(ref_map)

    print("Computing customer history + judgment fields...")
    history = compute_customer_history(orders, returns, ref_map)
    enriched_history = add_judgment_fields(history)
    customers_enriched = spine_df.merge(enriched_history, on="customer_id", how="left")
    # Customers with zero orders (both of a split pair's orders happened
    # to land on the sibling ref) get no history -- that's a legitimate
    # zero-activity profile, not a bug, so default them to "new" rather
    # than leaving nulls the app would have to special-case everywhere.
    customers_enriched["relationship_tier"] = customers_enriched["relationship_tier"].fillna("new")
    for col in ["lifetime_spend", "total_orders", "total_returns", "return_rate"]:
        customers_enriched[col] = customers_enriched[col].fillna(0)
    # Sentinel, not 0: 0 would misleadingly read as "bought something
    # today." These customers have no order history at all (vip_flag is
    # always False for them, so the sentinel can never trigger a VIP
    # dormant outreach by accident).
    customers_enriched["days_since_last_purchase"] = customers_enriched["days_since_last_purchase"].fillna(99999).astype(int)
    customers_enriched["vip_flag"] = customers_enriched["vip_flag"].map(lambda x: x is True)
    customers_enriched["fraud_watch_flag"] = customers_enriched["fraud_watch_flag"].map(lambda x: x is True)

    print("Computing return windows...")
    orders_with_style = orders.merge(dfs["product_catalog"][["item_id", "style_name"]], on="item_id", how="left")
    return_windows = compute_return_windows(orders_with_style, customers_enriched)

    print("Computing true inventory...")
    true_inventory, pending_returns_detail = compute_true_inventory(
        dfs["inventory"], returns, orders, dfs["product_catalog"]
    )

    outputs = {
        "customers_enriched.csv": customers_enriched,
        "return_windows.csv": return_windows,
        "true_inventory.csv": true_inventory,
        "pending_returns_detail.csv": pending_returns_detail,
    }
    for filename, df in outputs.items():
        path = os.path.join(CLEAN_DIR, filename)
        df.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(df)} rows)")

    ghost = true_inventory[true_inventory["pending_sellable_count"] > 0]
    print(f"\n{len(ghost)} store/item/size/color combos have sellable stock the system doesn't know about.")

    return customers_enriched, return_windows, true_inventory, pending_returns_detail


if __name__ == "__main__":
    main()
