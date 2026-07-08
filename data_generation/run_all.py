"""Entry point: generates every raw/*.csv plus the ground-truth answer
key, in dependency order, from a single fixed seed.

Run with:  python3 -m data_generation.run_all
"""
import os

from common.rng import seed_all
from data_generation.catalog import build_catalog
from data_generation.customers import generate_customers
from data_generation.orders import generate_orders
from data_generation.returns import generate_returns
from data_generation.inventory import generate_inventory
from data_generation.call_log import generate_call_log
from data_generation.outreach import generate_outreach

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROJECT_ROOT, "raw")
GROUND_TRUTH_DIR = os.path.join(PROJECT_ROOT, "ground_truth")


def main():
    seed_all()
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(GROUND_TRUTH_DIR, exist_ok=True)

    print("Generating product catalog...")
    catalog_df = build_catalog()

    print("Generating customers (pos, ecom, payment tokens, ground truth)...")
    pos_df, ecom_df, tokens_df, ground_truth_df, customer_index = generate_customers()

    print("Generating orders...")
    orders_raw_df, orders_internal_df = generate_orders(customer_index, pos_df, ecom_df, tokens_df, catalog_df)

    print("Generating returns...")
    returns_df, hero_info = generate_returns(orders_internal_df, catalog_df)

    print("Generating inventory...")
    inventory_df = generate_inventory(catalog_df, hero_info)

    print("Generating call log...")
    call_log_df = generate_call_log()

    print("Generating outreach log...")
    all_refs = pos_df["pos_record_id"].tolist() + ecom_df["ecom_id"].tolist()
    outreach_df = generate_outreach(all_refs)

    outputs = {
        "pos_customers.csv": pos_df,
        "ecom_customers.csv": ecom_df,
        "payment_tokens.csv": tokens_df,
        "product_catalog.csv": catalog_df,
        "orders.csv": orders_raw_df,
        "returns.csv": returns_df,
        "inventory.csv": inventory_df,
        "call_log.csv": call_log_df,
        "outreach_log.csv": outreach_df,
    }
    for filename, df in outputs.items():
        path = os.path.join(RAW_DIR, filename)
        df.to_csv(path, index=False)
        print(f"  wrote {path}  ({len(df)} rows)")

    gt_path = os.path.join(GROUND_TRUTH_DIR, "customers_ground_truth.csv")
    ground_truth_df.to_csv(gt_path, index=False)
    print(f"  wrote {gt_path}  ({len(ground_truth_df)} rows)")

    print("\nHero ghost-stock demo scenario:")
    print(f"  {hero_info['style_name']} ({hero_info['item_id']}), "
          f"size {hero_info['size']}, {hero_info['color']}")
    print(f"  returned at {hero_info['store']} on {hero_info['return_date']}, "
          f"sellable, unprocessed -> system_count is 0 there.")

    print("\nDone.")


if __name__ == "__main__":
    main()
