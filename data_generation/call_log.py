"""Generate raw/call_log.csv.

This file does two jobs. Mostly it's narrative/structural: it quantifies
the "7 calls a day asking about return windows" problem so the manager
analytics screen has something concrete to show (associate time lost).
return_window_inquiry calls are deliberately the most common reason code
and run longer, since today an associate has to dig through a
back-office system and do manual math to answer them.

But stock_check calls also carry a real payload: which customer asked
about which item/size/color. That's what lets Phase 3's outreach queue
generate a genuinely traceable "wanted item just returned in her size"
alert instead of guessing -- a call log entry plus a later matching
return is real evidence, not a fabricated reason. One such call is
deterministically wired to the same hero ghost-stock item used in
returns.py/inventory.py, a few days before the return happens, so that
story is demoable end to end: she called, we didn't have it, she called
before it existed, now it does.
"""
import pandas as pd

from common.config import DEMO_HERO_RETURN_DAYS_AGO, N_CALL_LOGS, STORE_LOCATIONS, TODAY
from common.rng import rng
from data_generation.catalog import colors_for, sizes_for

REASON_CODES = ["return_window_inquiry", "stock_check", "order_status", "other"]
REASON_WEIGHTS = [0.60, 0.20, 0.12, 0.08]

CALL_LOG_WINDOW_DAYS = 180
DEMO_HERO_CALL_DAYS_AGO = DEMO_HERO_RETURN_DAYS_AGO + 3


def _duration_for(reason_code):
    if reason_code == "return_window_inquiry":
        return round(rng.uniform(4, 12), 1)
    return round(rng.uniform(2, 6), 1)


def _random_timestamp(days_ago=None):
    if days_ago is None:
        days_ago = rng.randint(0, CALL_LOG_WINDOW_DAYS)
    call_date = TODAY - pd.Timedelta(days=days_ago)
    hour = rng.randint(10, 18)
    minute = rng.randint(0, 59)
    return pd.Timestamp(call_date).replace(hour=hour, minute=minute)


def _ref_for(customer):
    return customer["pos_ids"][0] if customer["pos_ids"] else customer["ecom_id"]


def generate_call_log(customer_index, catalog_df, hero_info):
    rows = []

    hero_customer = rng.choice(customer_index)
    rows.append({
        "call_id": "CALL-00001",
        "store_location": hero_info["store"],
        "timestamp": _random_timestamp(DEMO_HERO_CALL_DAYS_AGO).isoformat(sep=" "),
        "reason_code": "stock_check",
        "duration_minutes": _duration_for("stock_check"),
        "source_customer_ref": _ref_for(hero_customer),
        "item_id": hero_info["item_id"],
        "size": hero_info["size"],
        "color": hero_info["color"],
    })

    for i in range(2, N_CALL_LOGS + 1):
        reason_code = rng.choices(REASON_CODES, weights=REASON_WEIGHTS)[0]
        row = {
            "call_id": f"CALL-{i:05d}",
            "store_location": rng.choice(STORE_LOCATIONS),
            "timestamp": _random_timestamp().isoformat(sep=" "),
            "reason_code": reason_code,
            "duration_minutes": _duration_for(reason_code),
            "source_customer_ref": "",
            "item_id": "",
            "size": "",
            "color": "",
        }
        if reason_code == "stock_check":
            cust = rng.choice(customer_index)
            catalog_row = catalog_df.iloc[rng.randrange(len(catalog_df))]
            row["source_customer_ref"] = _ref_for(cust)
            row["item_id"] = catalog_row["item_id"]
            row["size"] = rng.choice(sizes_for(catalog_row))
            row["color"] = rng.choice(colors_for(catalog_row))
        rows.append(row)

    return pd.DataFrame(rows)
