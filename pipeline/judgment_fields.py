"""Pipeline requirement #4: derive judgment fields.

The brief is explicit that these rules must be simple and visible in
code -- no black-box scoring. Plain threshold logic, in priority order:
fraud watch beats VIP beats new beats regular (a customer never gets
silently mislabeled "VIP" if they're also flagged for a heavy return
pattern -- and per the brief's governance principle, these flags INFORM
an associate, they never auto-block a return).

Thresholds were picked by eyeballing the generated dataset's actual
spend/order distribution (see pipeline/customer_history.py output) and
rounding to the nearest clean number, landing VIP at roughly the top
15% of customers by spend or order count.
"""
import pandas as pd

from common.config import TODAY

VIP_SPEND_THRESHOLD = 2000.00
VIP_ORDER_COUNT_THRESHOLD = 10

FRAUD_RETURN_RATE_THRESHOLD = 0.50
FRAUD_MIN_ORDERS = 4

NEW_CUSTOMER_MAX_ORDERS = 1
NEW_CUSTOMER_MAX_DAYS_SINCE_FIRST_PURCHASE = 60


def add_judgment_fields(history_df: pd.DataFrame) -> pd.DataFrame:
    df = history_df.copy()

    df["vip_flag"] = (
        (df["lifetime_spend"] >= VIP_SPEND_THRESHOLD) | (df["total_orders"] >= VIP_ORDER_COUNT_THRESHOLD)
    )
    df["fraud_watch_flag"] = (
        (df["return_rate"] >= FRAUD_RETURN_RATE_THRESHOLD) & (df["total_orders"] >= FRAUD_MIN_ORDERS)
    )

    days_since_first_purchase = df["first_purchase_date"].apply(lambda d: (TODAY - d).days)
    is_new = (df["total_orders"] <= NEW_CUSTOMER_MAX_ORDERS) | (
        days_since_first_purchase <= NEW_CUSTOMER_MAX_DAYS_SINCE_FIRST_PURCHASE
    )

    def tier_for(row_is_fraud, row_is_vip, row_is_new):
        if row_is_fraud:
            return "watch"
        if row_is_vip:
            return "VIP"
        if row_is_new:
            return "new"
        return "regular"

    df["relationship_tier"] = [
        tier_for(f, v, n) for f, v, n in zip(df["fraud_watch_flag"], df["vip_flag"], is_new)
    ]

    return df
