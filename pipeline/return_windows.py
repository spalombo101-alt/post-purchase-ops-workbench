"""Pipeline requirement #5: compute a return window for every order.

Not a fixed rule -- the same 30-day policy applies to everyone by
default, but a customer's relationship_tier (computed from their whole
purchase/return history, not just this one order) can strictly enforce
it or extend it. This is deliberately simple, threshold-based logic
(per the brief's "rules must be simple and visible in code") rather
than a scoring model, so an associate or manager could recite the rule
from memory.

  - watch tier:   exactly the base window, no extension, no discretion
                   past the deadline.
  - VIP tier:     base window + a documented extension, and even after
                   that a further "discretionary" grace period where a
                   manager could still choose to honor it case by case.
  - new / regular: base window, no adjustment.

status is one of: open, closing_soon, closed, discretionary.
"""
import pandas as pd

from common.config import TODAY

BASE_WINDOW_DAYS = 30
VIP_EXTENSION_DAYS = 30
VIP_DISCRETIONARY_BUFFER_DAYS = 14
CLOSING_SOON_THRESHOLD_DAYS = 5


def _window_for_tier(tier: str):
    """Returns (adjusted_window_days, reason)."""
    if tier == "watch":
        return BASE_WINDOW_DAYS, (
            f"Watch-listed customer — standard {BASE_WINDOW_DAYS}-day return window applied strictly, "
            f"no extensions."
        )
    if tier == "VIP":
        total = BASE_WINDOW_DAYS + VIP_EXTENSION_DAYS
        return total, (
            f"VIP customer — standard {BASE_WINDOW_DAYS}-day window extended by {VIP_EXTENSION_DAYS} days "
            f"to {total} days."
        )
    return BASE_WINDOW_DAYS, f"Standard {BASE_WINDOW_DAYS}-day return window."


def _status_for(days_remaining: int, tier: str):
    if days_remaining > CLOSING_SOON_THRESHOLD_DAYS:
        return "open", ""
    if days_remaining >= 0:
        return "closing_soon", ""
    if tier == "VIP" and days_remaining >= -VIP_DISCRETIONARY_BUFFER_DAYS:
        return "discretionary", (
            f" Past the window, but VIP status allows manager discretion for up to "
            f"{VIP_DISCRETIONARY_BUFFER_DAYS} more days."
        )
    return "closed", ""


def compute_return_windows(orders_df: pd.DataFrame, customers_enriched_df: pd.DataFrame) -> pd.DataFrame:
    tier_by_customer = customers_enriched_df.set_index("customer_id")["relationship_tier"].to_dict()

    rows = []
    for _, order in orders_df.iterrows():
        customer_id = order["customer_id"]
        tier = tier_by_customer.get(customer_id, "regular")

        adjusted_window_days, reason = _window_for_tier(tier)
        window_closes_date = order["purchase_date"] + pd.Timedelta(days=adjusted_window_days)
        days_remaining = (window_closes_date - TODAY).days
        status, status_note = _status_for(days_remaining, tier)

        rows.append({
            "order_id": order["order_id"],
            "customer_id": customer_id,
            "item_id": order["item_id"],
            "style_name": order["style_name"],
            "size": order["size"],
            "color": order["color"],
            "purchase_date": order["purchase_date"].isoformat(),
            "relationship_tier": tier,
            "base_window_days": BASE_WINDOW_DAYS,
            "adjusted_window_days": adjusted_window_days,
            "window_closes_date": window_closes_date.isoformat(),
            "days_remaining": days_remaining,
            "status": status,
            "adjustment_reason": reason + status_note,
        })

    return pd.DataFrame(rows)
