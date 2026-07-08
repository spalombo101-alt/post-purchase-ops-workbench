"""Loads clean/ + raw/ data for the Streamlit app and builds a search
index so Screen 1 can find a customer by any of their linked records'
name/phone/email, not just their canonical one -- a customer merged
from a messy POS record and a separate ecom record should be findable
by either.
"""
import os

import pandas as pd
import streamlit as st

from pipeline.ingest import build_unified_customer_records, load_raw
from pipeline.spine import ref_to_customer_id_map

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(PROJECT_ROOT, "clean")


@st.cache_data
def load_all():
    dfs = load_raw()

    customers = pd.read_csv(os.path.join(CLEAN_DIR, "customers_enriched.csv"), keep_default_na=False)
    return_windows = pd.read_csv(os.path.join(CLEAN_DIR, "return_windows.csv"), keep_default_na=False)
    true_inventory = pd.read_csv(os.path.join(CLEAN_DIR, "true_inventory.csv"), keep_default_na=False)
    pending_detail = pd.read_csv(os.path.join(CLEAN_DIR, "pending_returns_detail.csv"), keep_default_na=False)

    unified = build_unified_customer_records(dfs["pos_customers"], dfs["ecom_customers"])
    ref_map = ref_to_customer_id_map(pd.read_csv(os.path.join(CLEAN_DIR, "customers_spine.csv"), keep_default_na=False))
    unified["customer_id"] = unified["ref"].map(ref_map)

    def blob_for(group):
        parts = []
        for _, row in group.iterrows():
            parts.append(str(row["name"]).lower())
            if pd.notna(row["phone"]) and row["phone"]:
                parts.append(str(row["phone"]))
            if pd.notna(row["email"]) and row["email"]:
                parts.append(str(row["email"]).lower())
        return " | ".join(parts)

    search_index = (
        unified.groupby("customer_id").apply(blob_for, include_groups=False).rename("search_blob").reset_index()
    )
    customers = customers.merge(search_index, on="customer_id", how="left")
    customers["search_blob"] = customers["search_blob"].fillna("")

    return {
        "customers": customers,
        "return_windows": return_windows,
        "true_inventory": true_inventory,
        "pending_detail": pending_detail,
        "catalog": dfs["product_catalog"],
    }


def search_customers(query: str, customers: pd.DataFrame, return_windows: pd.DataFrame) -> pd.DataFrame:
    query = query.strip().lower()
    if not query:
        return customers.iloc[0:0]

    order_hit_customer_ids = set(
        return_windows.loc[return_windows["order_id"].str.lower() == query, "customer_id"]
    )
    name_hits = customers[customers["search_blob"].str.contains(query, regex=False)]

    if order_hit_customer_ids:
        return customers[customers["customer_id"].isin(order_hit_customer_ids) | customers["customer_id"].isin(name_hits["customer_id"])]
    return name_hits
