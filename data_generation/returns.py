"""Generate raw/returns.csv -- this is the core "messy story" file.

Two mechanisms both push toward the same demo moment (an item the
official system says is out of stock but is actually sitting sellable
in a back room):

  1. Cross-store returns (~40% of returns happen at a different store
     than the item was purchased at) -- inventory silently moves stores.
  2. Processing lag (0-7 days, varies by store) plus a ~10% permanent
     "ghost stock" carve-out on sellable returns -- inventory silently
     goes stale even at the right store.

A specific hand-picked "hero" return is manufactured deterministically:
purchased at SoHo, returned at Bleecker 2 days before the dataset's
"today", sellable, still unprocessed. inventory.py reads the returned
hero item_id/size/color back out of this module so it can zero out the
matching system_count at Bleecker -- guaranteeing the Screen 2 demo
("official count says 0, tool says 1 sellable unit") always works.
"""
from datetime import timedelta

import pandas as pd

from common.config import DEMO_HERO_RETURN_DAYS_AGO, DEMO_HERO_STORE, STORE_LOCATIONS, TODAY
from common.rng import rng

RETURN_REASONS = ["fit_large", "fit_small", "changed_mind", "quality"]
RETURN_REASON_WEIGHTS = [0.30, 0.25, 0.30, 0.15]

REFUND_TYPES = ["original_payment", "store_credit", "exchange"]
REFUND_TYPE_WEIGHTS = [0.55, 0.30, 0.15]

# (min_days, max_days) processing lag by store -- flavor text for the
# "some stores are worse than others" narrative.
PROCESSING_LAG_BY_STORE = {
    "Madison Ave": (0, 3),
    "SoHo": (0, 4),
    "Flatiron": (1, 6),
    "Bleecker": (1, 7),
}

GHOST_STOCK_RATE = 0.10
MIN_RETURN_OFFSET_DAYS = 3
MAX_RETURN_OFFSET_DAYS = 60
MIN_PURCHASE_AGE_FOR_RETURN = 3


def _random_return_offset():
    return rng.randint(MIN_RETURN_OFFSET_DAYS, MAX_RETURN_OFFSET_DAYS)


def _pick_return_location(purchase_store):
    if not purchase_store:
        return rng.choice(STORE_LOCATIONS)
    if rng.random() < 0.40:
        others = [s for s in STORE_LOCATIONS if s != purchase_store]
        return rng.choice(others)
    return purchase_store


def _build_return_row(return_id, order_row, return_date, return_location,
                       force_sellable_unprocessed=False):
    return_reason = rng.choices(RETURN_REASONS, weights=RETURN_REASON_WEIGHTS)[0]
    refund_type = rng.choices(REFUND_TYPES, weights=REFUND_TYPE_WEIGHTS)[0]
    item_condition = "sellable" if force_sellable_unprocessed or rng.random() < 0.90 else "damaged"

    inventory_processed_flag = False
    inventory_processed_date = ""

    if not force_sellable_unprocessed:
        permanently_stuck = item_condition == "sellable" and rng.random() < GHOST_STOCK_RATE
        if not permanently_stuck:
            lag_min, lag_max = PROCESSING_LAG_BY_STORE[return_location]
            candidate = return_date + timedelta(days=rng.randint(lag_min, lag_max))
            if candidate <= TODAY:
                inventory_processed_flag = True
                inventory_processed_date = candidate.isoformat()

    return {
        "return_id": return_id,
        "order_id": order_row["order_id"],
        "item_id": order_row["item_id"],
        "return_date": return_date.isoformat(),
        "return_location": return_location,
        "return_reason": return_reason,
        "refund_type": refund_type,
        "item_condition": item_condition,
        "inventory_processed_flag": inventory_processed_flag,
        "inventory_processed_date": inventory_processed_date,
    }


def _pick_hero_order(orders_internal_df):
    eligible = orders_internal_df[
        (orders_internal_df["category"] == "jean")
        & (orders_internal_df["channel"] == "in_store")
        & (orders_internal_df["store_location"] != DEMO_HERO_STORE)
        & (orders_internal_df["purchase_date"] <= TODAY - timedelta(days=30))
    ]
    return eligible.iloc[rng.randrange(len(eligible))]


def generate_returns(orders_internal_df, catalog_df):
    item_category = catalog_df.set_index("item_id")["category"].to_dict()
    orders_internal_df = orders_internal_df.assign(
        category=orders_internal_df["item_id"].map(item_category)
    )

    hero_order = _pick_hero_order(orders_internal_df)
    hero_return_date = TODAY - timedelta(days=DEMO_HERO_RETURN_DAYS_AGO)

    n_general = 450 - 1
    candidates = orders_internal_df[
        (orders_internal_df["purchase_date"] <= TODAY - timedelta(days=MIN_PURCHASE_AGE_FOR_RETURN))
        & (orders_internal_df["order_id"] != hero_order["order_id"])
    ]
    sampled_idx = rng.sample(list(candidates.index), min(n_general, len(candidates)))
    general_orders = candidates.loc[sampled_idx]

    rows = []
    return_num = 1

    hero_row = _build_return_row(
        f"RET-{return_num:05d}", hero_order, hero_return_date, DEMO_HERO_STORE,
        force_sellable_unprocessed=True,
    )
    rows.append(hero_row)
    return_num += 1

    for _, order_row in general_orders.iterrows():
        max_offset = min(MAX_RETURN_OFFSET_DAYS, (TODAY - order_row["purchase_date"]).days)
        offset = rng.randint(MIN_RETURN_OFFSET_DAYS, max(MIN_RETURN_OFFSET_DAYS, max_offset))
        return_date = order_row["purchase_date"] + timedelta(days=offset)
        return_location = _pick_return_location(order_row["store_location"])

        rows.append(_build_return_row(f"RET-{return_num:05d}", order_row, return_date, return_location))
        return_num += 1

    returns_df = pd.DataFrame(rows)

    hero_info = {
        "item_id": hero_order["item_id"],
        "size": hero_order["size"],
        "color": hero_order["color"],
        "store": DEMO_HERO_STORE,
        "style_name": hero_order["style_name"],
        "return_date": hero_return_date,
    }
    return returns_df, hero_info
