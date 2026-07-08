"""Generate raw/orders.csv.

One row per order line (this generator treats "order" and "order line"
as the same thing -- no multi-item baskets). That keeps the later
return_id -> order_id -> item_id chain unambiguous without inventing a
basket concept the brief never asked for.

Deliberate messiness, per the brief:
  - purchase_date appears in three different string formats depending on
    channel/store: ISO for online, US slash for in-store at three of the
    four stores, and day-month text for in-store at Madison Ave (modeled
    as that flagship location still running an older POS terminal).
  - ~5% of in-store orders are missing store_location.

Returns two things:
  - orders_raw_df: exactly the messy columns that belong in raw/orders.csv
  - orders_internal_df: the same orders with clean typed dates/fields,
    used by returns.py and inventory.py so downstream generators don't
    have to re-parse three date formats to figure out what happened.
"""
import pandas as pd

from common.config import DATA_END_DATE, IN_STORE_CHANNEL, ONLINE_CHANNEL, STORE_LOCATIONS
from common.rng import rng
from data_generation.catalog import colors_for, sizes_for

LEGACY_POS_STORE = "Madison Ave"


def _random_date(start, end):
    span = max((end - start).days, 0)
    return start + pd.Timedelta(days=rng.randint(0, span))


def _format_purchase_date(d, channel, store_location):
    if channel == ONLINE_CHANNEL:
        return d.isoformat()
    if store_location == LEGACY_POS_STORE:
        return d.strftime("%d %b %Y")
    return f"{d.month}/{d.day}/{d.year}"


def _order_count_for_customer():
    return max(1, min(25, int(round(rng.gauss(6, 4)))))


def generate_orders(customer_index, pos_df, ecom_df, tokens_df, catalog_df):
    pos_created = pos_df.set_index("pos_record_id")["created_date"].to_dict()
    pos_store = pos_df.set_index("pos_record_id")["store_signed_up"].to_dict()
    ecom_created = ecom_df.set_index("ecom_id")["created_date"].to_dict()
    ref_to_token = tokens_df.set_index("source_customer_ref")["token_id"].to_dict()

    parse = lambda s: pd.Timestamp(s).date()

    raw_rows = []
    internal_rows = []
    order_num = 1

    for cust in customer_index:
        pos_ids = cust["pos_ids"]
        ecom_id = cust["ecom_id"]
        if not pos_ids and not ecom_id:
            continue

        n_orders = _order_count_for_customer()

        for _ in range(n_orders):
            if pos_ids and ecom_id:
                channel = IN_STORE_CHANNEL if rng.random() < 0.55 else ONLINE_CHANNEL
            elif pos_ids:
                channel = IN_STORE_CHANNEL
            else:
                channel = ONLINE_CHANNEL

            if channel == IN_STORE_CHANNEL:
                source_ref = rng.choice(pos_ids)
                lower_bound = parse(pos_created[source_ref])
                store_location = (pos_store[source_ref] if rng.random() < 0.7
                                   else rng.choice(STORE_LOCATIONS))
            else:
                source_ref = ecom_id
                lower_bound = parse(ecom_created[source_ref])
                store_location = None

            purchase_date = _random_date(lower_bound, DATA_END_DATE)

            store_missing = channel == IN_STORE_CHANNEL and rng.random() < 0.05
            recorded_store = "" if store_missing else (store_location or "")

            catalog_row = catalog_df.iloc[rng.randrange(len(catalog_df))]
            size = rng.choice(sizes_for(catalog_row))
            color = rng.choice(colors_for(catalog_row))
            qty = 1 if rng.random() < 0.85 else 2
            sale_flag = rng.random() < 0.2
            unit_price = catalog_row["base_price"]
            if sale_flag:
                unit_price = round(unit_price * rng.uniform(0.6, 0.8), 2)
            price_paid = round(unit_price * qty, 2)

            order_id = f"ORD-{order_num:06d}"
            order_num += 1

            raw_rows.append({
                "order_id": order_id,
                "source_customer_ref": source_ref,
                "channel": channel,
                "store_location": recorded_store,
                "purchase_date": _format_purchase_date(purchase_date, channel, store_location or ""),
                "payment_token": ref_to_token.get(source_ref, ""),
                "item_id": catalog_row["item_id"],
                "size": size,
                "color": color,
                "qty": qty,
                "price_paid": price_paid,
                "sale_flag": sale_flag,
            })

            internal_rows.append({
                "order_id": order_id,
                "true_person_id": cust["true_person_id"],
                "source_customer_ref": source_ref,
                "channel": channel,
                "store_location": store_location or "",
                "purchase_date": purchase_date,
                "item_id": catalog_row["item_id"],
                "style_name": catalog_row["style_name"],
                "size": size,
                "color": color,
                "qty": qty,
                "price_paid": price_paid,
                "sale_flag": sale_flag,
            })

    return pd.DataFrame(raw_rows), pd.DataFrame(internal_rows)
