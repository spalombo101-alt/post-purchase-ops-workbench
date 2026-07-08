"""Product catalog.

Not one of the raw files named in the project brief, but orders.csv,
returns.csv, and inventory.csv all reference item_id/size/color and need
to agree on what those mean -- and Screen 2 ("true inventory") needs a
real style name to search by, not just an opaque SKU. This is generated
once and treated as a fixed reference table the other generators import.
"""
import pandas as pd

DENIM_SIZES = ["24", "25", "26", "27", "28", "29", "30", "31", "32", "33", "34"]
DENIM_COLORS = ["Indigo", "Black", "White", "Stone Wash", "Raw Denim", "Vintage Blue"]

APPAREL_SIZES = ["XS", "S", "M", "L", "XL"]
APPAREL_COLORS = ["Indigo", "Black", "Stone Wash", "Raw Denim"]

# (style_name, category, base_price)
DENIM_STYLES = [
    ("Skinny", 168.00),
    ("Straight", 178.00),
    ("Bootcut", 178.00),
    ("Wide Leg", 198.00),
    ("Slim Straight", 178.00),
    ("High-Rise Skinny", 188.00),
    ("Mom Jean", 168.00),
    ("Boyfriend", 178.00),
    ("Cropped Straight", 168.00),
    ("Flare", 208.00),
]

APPAREL_STYLES = [
    ("Denim Jacket", "jacket", 228.00),
    ("Chore Jacket", "jacket", 248.00),
    ("Trucker Jacket", "jacket", 218.00),
    ("Denim Shirt", "top", 138.00),
    ("Denim Overalls", "bottom", 208.00),
    ("Denim Skirt", "bottom", 148.00),
]


def build_catalog() -> pd.DataFrame:
    rows = []
    item_num = 1

    for style_name, base_price in DENIM_STYLES:
        rows.append({
            "item_id": f"SKU-{item_num:03d}",
            "style_name": style_name,
            "category": "jean",
            "base_price": base_price,
            "available_sizes": ",".join(DENIM_SIZES),
            "available_colors": ",".join(DENIM_COLORS),
        })
        item_num += 1

    for style_name, category, base_price in APPAREL_STYLES:
        rows.append({
            "item_id": f"SKU-{item_num:03d}",
            "style_name": style_name,
            "category": category,
            "base_price": base_price,
            "available_sizes": ",".join(APPAREL_SIZES),
            "available_colors": ",".join(APPAREL_COLORS),
        })
        item_num += 1

    return pd.DataFrame(rows)


def sizes_for(catalog_row) -> list:
    return catalog_row["available_sizes"].split(",")


def colors_for(catalog_row) -> list:
    return catalog_row["available_colors"].split(",")
