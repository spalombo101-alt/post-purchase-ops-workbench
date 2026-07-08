"""Pipeline requirement #1: ingest all raw CSVs, normalize date formats
and field names.

Two things this module does that the rest of the pipeline depends on:

1. purchase_date in orders.csv shows up in three different string
   formats (ISO, US slash, day-month text) depending on channel/store.
   parse_purchase_date() auto-detects which one it's looking at and
   returns a real date, so nothing downstream has to think about string
   formats again.

2. pos_customers.csv and ecom_customers.csv have different column names
   for the same concepts (name vs full_name, no store field on ecom,
   etc). build_unified_customer_records() reshapes both into one
   long-format table -- one row per source record, common column names
   -- which is what the entity-resolution spine actually operates on.
"""
import os
from datetime import datetime

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROJECT_ROOT, "raw")

RAW_FILES = [
    "pos_customers.csv", "ecom_customers.csv", "payment_tokens.csv",
    "product_catalog.csv", "orders.csv", "returns.csv", "inventory.csv",
    "call_log.csv", "outreach_log.csv",
]

_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d %b %Y"]


def parse_purchase_date(raw_value: str):
    raw_value = str(raw_value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw_value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date format: {raw_value!r}")


def load_raw() -> dict:
    dfs = {}
    for filename in RAW_FILES:
        key = filename.replace(".csv", "")
        dfs[key] = pd.read_csv(os.path.join(RAW_DIR, filename), keep_default_na=False)
    return dfs


def normalize_orders(orders_raw_df: pd.DataFrame) -> pd.DataFrame:
    df = orders_raw_df.copy()
    df["purchase_date"] = df["purchase_date"].apply(parse_purchase_date)
    df["store_location"] = df["store_location"].replace("", pd.NA)
    return df


def normalize_returns(returns_raw_df: pd.DataFrame) -> pd.DataFrame:
    df = returns_raw_df.copy()
    df["return_date"] = pd.to_datetime(df["return_date"]).dt.date
    df["inventory_processed_date"] = df["inventory_processed_date"].replace("", pd.NA)
    df["inventory_processed_flag"] = df["inventory_processed_flag"].astype(str).str.lower() == "true"
    return df


def build_unified_customer_records(pos_df: pd.DataFrame, ecom_df: pd.DataFrame) -> pd.DataFrame:
    pos_records = pd.DataFrame({
        "ref": pos_df["pos_record_id"],
        "source_type": "pos",
        "name": pos_df["name"],
        "phone": pos_df["phone"].replace("", pd.NA),
        "email": pos_df["email"].replace("", pd.NA),
        "store": pos_df["store_signed_up"].replace("", pd.NA),
        "created_date": pd.to_datetime(pos_df["created_date"]).dt.date,
    })

    ecom_records = pd.DataFrame({
        "ref": ecom_df["ecom_id"],
        "source_type": "ecom",
        "name": ecom_df["full_name"],
        "phone": pd.NA,
        "email": ecom_df["email"].replace("", pd.NA),
        "store": pd.NA,
        "created_date": pd.to_datetime(ecom_df["created_date"]).dt.date,
    })

    unified = pd.concat([pos_records, ecom_records], ignore_index=True)
    name_parts = unified["name"].str.strip().str.split(r"\s+", n=1, expand=True)
    unified["first_name"] = name_parts[0]
    unified["last_name"] = name_parts[1].fillna("")
    return unified
