"""Generate raw/inventory.csv.

One row per store x item x size x color combination that the catalog
defines -- i.e. a full stock table, the way a real inventory system
would track it (including combos that are simply out of stock).

The core messiness the brief calls out: system_count is a snapshot that
does NOT know about sellable returns sitting unprocessed in a back room.
Phase 2's pipeline is what joins returns back in to compute
true_available; this file, on its own, deliberately undercounts.

The hero combo picked by returns.py (see returns.py's module docstring)
is force-set to 0 at Bleecker here, so system_count says "none left"
for the exact item that a sellable, unprocessed return just made
available again.
"""
import pandas as pd

from common.config import STORE_LOCATIONS, TODAY
from common.rng import rng
from data_generation.catalog import colors_for, sizes_for

MAX_LAST_UPDATED_AGE_DAYS = 14


def generate_inventory(catalog_df, hero_info):
    rows = []
    for store in STORE_LOCATIONS:
        for _, catalog_row in catalog_df.iterrows():
            for size in sizes_for(catalog_row):
                for color in colors_for(catalog_row):
                    is_hero = (
                        store == hero_info["store"]
                        and catalog_row["item_id"] == hero_info["item_id"]
                        and size == hero_info["size"]
                        and color == hero_info["color"]
                    )
                    system_count = 0 if is_hero else max(0, int(round(rng.gauss(3, 3))))
                    last_updated = TODAY - pd.Timedelta(days=rng.randint(0, MAX_LAST_UPDATED_AGE_DAYS))

                    rows.append({
                        "store_location": store,
                        "item_id": catalog_row["item_id"],
                        "size": size,
                        "color": color,
                        "system_count": system_count,
                        "last_updated": last_updated.isoformat(),
                    })

    return pd.DataFrame(rows)
