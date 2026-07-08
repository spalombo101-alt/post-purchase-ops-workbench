"""Pipeline requirement #6: true inventory.

inventory.csv's system_count is a stale snapshot that has no idea a
sellable item was just handed back at the counter. true_available adds
back every return that is (a) sellable and (b) not yet processed back
into the system -- regardless of which store it was purchased at,
because what matters for "can I sell this to the person in front of
me" is which store the item is physically sitting in right now, i.e.
return_location.

Returns two tables:
  - true_inventory: one row per store/item/size/color, system_count vs
    true_available.
  - pending_returns_detail: one row per still-unprocessed sellable
    return, so Screen 2 can say exactly where/when/how-long, not just a
    number.
"""
import pandas as pd

from common.config import TODAY


def compute_true_inventory(inventory_df: pd.DataFrame, returns_df: pd.DataFrame, orders_df: pd.DataFrame,
                            catalog_df: pd.DataFrame):
    pending = returns_df[
        (returns_df["item_condition"] == "sellable") & (~returns_df["inventory_processed_flag"])
    ].copy()

    order_lookup = orders_df.set_index("order_id")[["size", "color"]]
    pending = pending.join(order_lookup, on="order_id", rsuffix="_order")
    pending["days_unprocessed"] = pending["return_date"].apply(lambda d: (TODAY - d).days)

    pending_counts = (
        pending.groupby(["return_location", "item_id", "size", "color"])
        .size()
        .rename("pending_sellable_count")
        .reset_index()
    )

    true_inv = inventory_df.merge(
        pending_counts,
        left_on=["store_location", "item_id", "size", "color"],
        right_on=["return_location", "item_id", "size", "color"],
        how="left",
    ).drop(columns=["return_location"])
    true_inv["pending_sellable_count"] = true_inv["pending_sellable_count"].fillna(0).astype(int)
    true_inv["true_available"] = true_inv["system_count"] + true_inv["pending_sellable_count"]

    true_inv = true_inv.merge(catalog_df[["item_id", "style_name", "category"]], on="item_id", how="left")

    pending_detail = pending[[
        "return_id", "order_id", "return_location", "item_id", "size", "color",
        "return_date", "days_unprocessed",
    ]].rename(columns={"return_location": "store_location"})
    pending_detail["return_date"] = pending_detail["return_date"].apply(lambda d: d.isoformat())

    return true_inv, pending_detail
