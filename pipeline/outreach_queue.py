"""Pipeline requirement #7: the reason-driven outreach queue -- the
thing meant to replace the blind day_7/day_30 blast in outreach_log.csv.

Three trigger types, each tied to a real, traceable signal rather than
a fixed schedule:

  - window_closing: their return window is about to shut. Useful to
    THEM (avoid missing it), not just a sales trigger.
  - vip_dormant: a high-value customer hasn't bought anything in a
    while.
  - wanted_item_returned: they called asking whether an item/size/color
    was in stock, we said no, and a sellable return just made it
    available again -- the flip side of Phase 2's ghost-stock story.

Consent-aware per the brief's governance section: outreach requires
explicitly shared contact info. In this dataset a bare phone number is
what an associate captures for a receipt/service purpose; email is the
channel outreach_log.csv actually sends to. So "no consented marketing
channel" = no email on ANY of a customer's linked source records --
computed here, not asserted, so it actually excludes real customers
rather than being a no-op.

A customer can qualify for more than one trigger; only their single
highest-priority reason is kept, since an associate should call someone
once; a plain priority_score ranks the queue.
"""
import pandas as pd

from common.config import TODAY

WINDOW_CLOSING_BASE_SCORE = 60
VIP_DORMANT_BASE_SCORE = 50
VIP_DORMANT_MIN_DAYS = 90
VIP_DORMANT_CAP_DAYS = 270
WANTED_ITEM_BASE_SCORE = 90
WANTED_ITEM_CALL_RECENCY_DAYS = 45
VIP_PRIORITY_BONUS = 10


def _customers_with_email(unified_df: pd.DataFrame, ref_map: dict) -> set:
    with_email = unified_df[unified_df["email"].notna() & (unified_df["email"] != "")]
    return set(with_email["ref"].map(ref_map).dropna())


def _window_closing_candidates(return_windows_df: pd.DataFrame) -> pd.DataFrame:
    closing = return_windows_df[return_windows_df["status"] == "closing_soon"].copy()
    closing["priority_score"] = WINDOW_CLOSING_BASE_SCORE + (5 - closing["days_remaining"]) * 8
    closing["trigger_reason"] = closing.apply(
        lambda r: f"Return window closes in {r['days_remaining']} day(s) — "
                  f"{r['style_name']} ({r['size']}, {r['color']})",
        axis=1,
    )
    return closing[["customer_id", "trigger_reason", "priority_score"]]


def _vip_dormant_candidates(customers_df: pd.DataFrame) -> pd.DataFrame:
    dormant = customers_df[
        (customers_df["relationship_tier"] == "VIP")
        & (customers_df["days_since_last_purchase"] >= VIP_DORMANT_MIN_DAYS)
    ].copy()
    capped_days = dormant["days_since_last_purchase"].clip(upper=VIP_DORMANT_CAP_DAYS)
    dormant["priority_score"] = (
        VIP_DORMANT_BASE_SCORE + (capped_days - VIP_DORMANT_MIN_DAYS) / (VIP_DORMANT_CAP_DAYS - VIP_DORMANT_MIN_DAYS) * 30
    )
    dormant["trigger_reason"] = dormant["days_since_last_purchase"].apply(
        lambda d: f"VIP customer, dormant {int(d)} days"
    )
    return dormant[["customer_id", "trigger_reason", "priority_score"]]


def _wanted_item_returned_candidates(call_log_df: pd.DataFrame, pending_detail_df: pd.DataFrame,
                                       catalog_df: pd.DataFrame, ref_map: dict) -> pd.DataFrame:
    calls = call_log_df[call_log_df["reason_code"] == "stock_check"].copy()
    calls = calls[calls["source_customer_ref"] != ""]
    calls["call_date"] = pd.to_datetime(calls["timestamp"]).dt.date
    calls = calls[calls["call_date"].apply(lambda d: (TODAY - d).days) <= WANTED_ITEM_CALL_RECENCY_DAYS]

    matches = calls.merge(
        pending_detail_df, on=["item_id", "size", "color"], how="inner", suffixes=("_call", "_return")
    )
    if matches.empty:
        return pd.DataFrame(columns=["customer_id", "trigger_reason", "priority_score"])

    matches["customer_id"] = matches["source_customer_ref"].map(ref_map)
    matches = matches.merge(catalog_df[["item_id", "style_name"]], on="item_id", how="left")
    matches["priority_score"] = WANTED_ITEM_BASE_SCORE
    matches["trigger_reason"] = matches.apply(
        lambda r: f"Called asking about {r['style_name']} ({r['size']}, {r['color']}) — now available, "
                  f"returned at {r['store_location_return']} {r['days_unprocessed']} day(s) ago",
        axis=1,
    )
    # one customer might have called about several now-returned items; keep their strongest lead
    matches = matches.sort_values("priority_score", ascending=False).drop_duplicates("customer_id")
    return matches[["customer_id", "trigger_reason", "priority_score"]]


def compute_outreach_queue(customers_df: pd.DataFrame, return_windows_df: pd.DataFrame, call_log_df: pd.DataFrame,
                             pending_detail_df: pd.DataFrame, catalog_df: pd.DataFrame, unified_df: pd.DataFrame,
                             ref_map: dict) -> pd.DataFrame:
    return_windows_df = return_windows_df.merge(
        customers_df[["customer_id", "relationship_tier"]], on="customer_id", how="left", suffixes=("", "_c")
    )

    candidates = pd.concat([
        _window_closing_candidates(return_windows_df),
        _vip_dormant_candidates(customers_df),
        _wanted_item_returned_candidates(call_log_df, pending_detail_df, catalog_df, ref_map),
    ], ignore_index=True)

    tier_by_customer = customers_df.set_index("customer_id")["relationship_tier"].to_dict()
    candidates["priority_score"] = candidates.apply(
        lambda r: r["priority_score"] + (VIP_PRIORITY_BONUS if tier_by_customer.get(r["customer_id"]) == "VIP" else 0),
        axis=1,
    )

    consented = _customers_with_email(unified_df, ref_map)
    excluded_count = candidates[~candidates["customer_id"].isin(consented)]["customer_id"].nunique()
    candidates = candidates[candidates["customer_id"].isin(consented)]

    # one reason per customer: keep their single highest-priority trigger
    candidates = candidates.sort_values("priority_score", ascending=False).drop_duplicates("customer_id")

    candidates = candidates.merge(
        customers_df[["customer_id", "canonical_name", "canonical_email", "canonical_phone", "relationship_tier"]],
        on="customer_id", how="left",
    )
    candidates = candidates.sort_values("priority_score", ascending=False).reset_index(drop=True)
    candidates.insert(0, "queue_id", [f"OUT-{i:05d}" for i in range(1, len(candidates) + 1)])
    candidates["priority_score"] = candidates["priority_score"].round(1)

    return candidates, excluded_count
