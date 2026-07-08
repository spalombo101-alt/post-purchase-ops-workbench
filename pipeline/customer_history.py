"""Pipeline requirement #3: per-customer history fields, computed by
joining orders.csv and returns.csv back to the spine via customer_id
(one real person can own several source records, so this rolls up
spending/order/return activity across all of them -- not just one).
"""
import pandas as pd

from common.config import TODAY


def compute_customer_history(orders_df: pd.DataFrame, returns_df: pd.DataFrame, ref_to_customer_id: dict) -> pd.DataFrame:
    orders = orders_df.copy()
    orders["customer_id"] = orders["source_customer_ref"].map(ref_to_customer_id)

    returns_with_customer = returns_df.merge(
        orders[["order_id", "customer_id"]], on="order_id", how="left"
    )
    returns_per_customer = returns_with_customer.groupby("customer_id").size()

    grouped = orders.groupby("customer_id")
    history = grouped.agg(
        total_orders=("order_id", "count"),
        lifetime_spend=("price_paid", "sum"),
        first_purchase_date=("purchase_date", "min"),
        last_purchase_date=("purchase_date", "max"),
    ).reset_index()

    history["total_returns"] = history["customer_id"].map(returns_per_customer).fillna(0).astype(int)
    history["return_rate"] = (history["total_returns"] / history["total_orders"]).round(3)
    history["days_since_last_purchase"] = history["last_purchase_date"].apply(lambda d: (TODAY - d).days)
    history["lifetime_spend"] = history["lifetime_spend"].round(2)

    return history[[
        "customer_id", "lifetime_spend", "total_orders", "total_returns", "return_rate",
        "first_purchase_date", "last_purchase_date", "days_since_last_purchase",
    ]]
