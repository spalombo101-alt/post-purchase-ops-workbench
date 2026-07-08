"""Post-Purchase Operations Workbench -- Streamlit app.

Phase 2 scope: Screen 1 (return lookup) and Screen 2 (true inventory).
Screen 3 (outreach + analytics) and the governance/role-toggle layer are
Phase 3 -- deliberately not here yet.

Run with:  streamlit run app/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from app.data import load_all, search_customers

STATUS_COLOR = {
    "open": "🟢",
    "closing_soon": "🟠",
    "discretionary": "🔵",
    "closed": "⚪",
}
TIER_BADGE = {
    "VIP": "⭐ VIP",
    "watch": "🚩 Watch",
    "new": "🆕 New",
    "regular": "Regular",
}

st.set_page_config(page_title="Post-Purchase Ops Workbench", layout="wide")
data = load_all()


def screen_return_lookup():
    st.header("Return Lookup")
    st.caption("Search by name, phone, email, or order number. Goal: answer any return call in under 15 seconds.")

    query = st.text_input("Search", placeholder="e.g. Kathryn Miller, (243) 660-4084, or ORD-000004")
    if not query:
        return

    matches = search_customers(query, data["customers"], data["return_windows"])
    if matches.empty:
        st.warning("No customer found for that search.")
        return

    for _, cust in matches.iterrows():
        with st.container(border=True):
            top_col1, top_col2 = st.columns([3, 1])
            with top_col1:
                st.subheader(cust["canonical_name"])
                st.write(TIER_BADGE.get(cust["relationship_tier"], cust["relationship_tier"]))
                if int(cust["record_count"]) > 1:
                    st.caption(f"🔗 merged from {int(cust['record_count'])} source records")
            with top_col2:
                st.metric("Lifetime spend", f"${cust['lifetime_spend']:,.2f}")
                st.metric("Return rate", f"{cust['return_rate']:.0%}")

            orders = data["return_windows"][data["return_windows"]["customer_id"] == cust["customer_id"]]
            orders = orders.sort_values("purchase_date", ascending=False)

            if orders.empty:
                st.caption("No purchase history on file.")
                continue

            display = orders[[
                "purchase_date", "style_name", "size", "color", "window_closes_date",
                "days_remaining", "status", "adjustment_reason",
            ]].copy()
            display["status"] = display["status"].map(lambda s: f"{STATUS_COLOR.get(s, '')} {s}")
            display = display.rename(columns={
                "purchase_date": "Purchased", "style_name": "Item", "size": "Size", "color": "Color",
                "window_closes_date": "Window closes", "days_remaining": "Days remaining",
                "status": "Status", "adjustment_reason": "Why",
            })
            st.dataframe(display, hide_index=True, use_container_width=True)


def screen_true_inventory():
    st.header("True Inventory")
    st.caption("Search item + size + color. Shows what the system thinks is in stock vs. what's actually available.")

    catalog = data["catalog"]
    style_name = st.selectbox("Style", sorted(catalog["style_name"].unique()))
    catalog_row = catalog[catalog["style_name"] == style_name].iloc[0]

    col1, col2 = st.columns(2)
    with col1:
        size = st.selectbox("Size", catalog_row["available_sizes"].split(","))
    with col2:
        color = st.selectbox("Color", catalog_row["available_colors"].split(","))

    rows = data["true_inventory"][
        (data["true_inventory"]["item_id"] == catalog_row["item_id"])
        & (data["true_inventory"]["size"].astype(str) == size)
        & (data["true_inventory"]["color"] == color)
    ]

    st.subheader(f"{style_name} — size {size}, {color}")

    store_cols = st.columns(len(rows))
    for col, (_, row) in zip(store_cols, rows.iterrows()):
        with col:
            st.markdown(f"**{row['store_location']}**")
            st.metric("System says", int(row["system_count"]))
            delta = int(row["true_available"]) - int(row["system_count"])
            st.metric("Actually available", int(row["true_available"]), delta=(f"+{delta}" if delta else None))

            if row["pending_sellable_count"] > 0:
                detail = data["pending_detail"][
                    (data["pending_detail"]["store_location"] == row["store_location"])
                    & (data["pending_detail"]["item_id"] == catalog_row["item_id"])
                    & (data["pending_detail"]["size"].astype(str) == size)
                    & (data["pending_detail"]["color"] == color)
                ]
                for _, d in detail.iterrows():
                    st.info(
                        f"1 sellable unit — returned here {d['days_unprocessed']} day(s) ago "
                        f"({d['return_date']}), not yet reshelved."
                    )

            if row["true_available"] > 0:
                if st.button(f"Request transfer from {row['store_location']}", key=f"transfer_{row['store_location']}"):
                    st.success(f"Transfer requested from {row['store_location']}. (mock action — no system connected)")


st.sidebar.title("Post-Purchase Ops Workbench")
screen = st.sidebar.radio("Screen", ["Return Lookup", "True Inventory"])

if screen == "Return Lookup":
    screen_return_lookup()
else:
    screen_true_inventory()
