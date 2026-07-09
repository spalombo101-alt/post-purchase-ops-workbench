"""Post-Purchase Operations Workbench -- Streamlit app.

Three screens: Return Lookup and True Inventory (associate-facing),
Outreach + Analytics (manager-only). Governance is built in, not
bolted on: a role toggle controls what an associate can see, every
customer lookup is written to an audit log, and the outreach queue and
review queue are visible to managers so nothing resolves silently.

Run with:  streamlit run app/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from app.audit import load_audit_log, log_lookup
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

st.sidebar.title("Post-Purchase Ops Workbench")
role = st.sidebar.radio("Role", ["Associate", "Manager"])
associate_name = st.sidebar.text_input("Your name (for the audit log)", value="")
is_manager = role == "Manager"

screen_options = ["Return Lookup", "True Inventory"]
if is_manager:
    screen_options.append("Outreach + Analytics")
screen = st.sidebar.radio("Screen", screen_options)

if not is_manager:
    st.sidebar.caption(
        "Associate view: exact spend, contact details, and flag logic are hidden. "
        "Switch to Manager to see them."
    )


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

    last_logged = st.session_state.get("last_logged_query")
    if last_logged != query:
        for _, cust in matches.iterrows():
            log_lookup(associate_name, cust["customer_id"], cust["canonical_name"])
        st.session_state["last_logged_query"] = query

    for _, cust in matches.iterrows():
        with st.container(border=True):
            top_col1, top_col2 = st.columns([3, 1])
            with top_col1:
                st.subheader(cust["canonical_name"])
                st.write(TIER_BADGE.get(cust["relationship_tier"], cust["relationship_tier"]))
                if int(cust["record_count"]) > 1:
                    st.caption(f"🔗 merged from {int(cust['record_count'])} source records")
            with top_col2:
                if is_manager:
                    st.metric("Lifetime spend", f"${cust['lifetime_spend']:,.2f}")
                    st.metric("Return rate", f"{cust['return_rate']:.0%}")
                    st.caption(f"{cust['canonical_email']}  {cust['canonical_phone']}")
                    if cust["fraud_watch_flag"] in (True, "True"):
                        st.caption("🚩 Fraud-watch flag is informational only — it never blocks a return.")

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


def screen_outreach_analytics():
    st.header("Outreach + Analytics")
    st.caption("Manager view.")

    st.subheader("Reason-driven outreach queue")
    queue = data["outreach_queue"].copy()
    display = queue[[
        "canonical_name", "relationship_tier", "trigger_reason", "priority_score",
        "canonical_email", "canonical_phone",
    ]].rename(columns={
        "canonical_name": "Customer", "relationship_tier": "Tier", "trigger_reason": "Why",
        "priority_score": "Priority", "canonical_email": "Email", "canonical_phone": "Phone",
    })
    st.dataframe(display, hide_index=True, use_container_width=True)
    st.caption(
        f"{len(queue)} customers queued. "
        f"{data['analytics_summary']['excluded_no_consent']} more matched a trigger but were excluded — "
        f"no email on file, so no consented marketing channel."
    )

    st.divider()
    st.subheader("Associate time lost to return-window calls")
    tl = data["analytics_summary"]["time_lost"]
    m1, m2, m3 = st.columns(3)
    m1.metric("Hours / week", tl["hours_per_week"])
    m2.metric("Share of all calls", f"{tl['share_of_all_calls']:.0%}")
    m3.metric("Total calls logged", tl["total_calls"])
    by_store = pd.DataFrame(data["analytics_summary"]["time_lost_by_store"])
    st.dataframe(
        by_store.rename(columns={
            "store_location": "Store", "total_minutes": "Total minutes", "call_count": "Calls",
            "minutes_per_week": "Minutes / week",
        }),
        hide_index=True, use_container_width=True,
    )

    st.divider()
    st.subheader("Return-reason clustering by style")
    rc = data["reason_clustering"]
    flagged = rc[rc["insight"] != ""]
    if not flagged.empty:
        for _, r in flagged.iterrows():
            st.warning(f"**{r['style_name']}** — {r['insight']} "
                       f"({r['total_returns']} returns, {r['fit_small_share']:.0%} fit-small / "
                       f"{r['fit_large_share']:.0%} fit-large / {r['quality_share']:.0%} quality)")
    st.dataframe(
        rc[["style_name", "total_returns", "fit_large_share", "fit_small_share", "changed_mind_share",
            "quality_share", "insight"]],
        hide_index=True, use_container_width=True,
    )

    st.divider()
    st.subheader("Reason-driven vs. time-blast outreach")
    cmp = data["analytics_summary"]["outreach_comparison"]
    old_col, new_col = st.columns(2)
    with old_col:
        st.markdown("**Old system — time-blast (day_7 / day_30)**")
        st.metric("Purchase conversion", f"{cmp['old_time_blast']['purchase_conversion_rate']:.1%}")
        st.caption(f"{cmp['old_time_blast']['total_sent']} sent · "
                   f"{cmp['old_time_blast']['open_rate']:.0%} opened · "
                   f"{cmp['old_time_blast']['reply_rate']:.0%} replied")
    with new_col:
        st.markdown("**New system — reason-driven**")
        st.metric("Queued this cycle", cmp["new_reason_driven"]["total_queued"])
        st.caption(", ".join(f"{k}: {v}" for k, v in cmp["new_reason_driven"]["by_trigger_type"].items()))
    st.info(cmp["new_reason_driven"]["note"])

    st.divider()
    st.subheader("Governance")
    gov_col1, gov_col2 = st.columns(2)
    with gov_col1:
        st.markdown(f"**Entity-resolution review queue** — {len(data['review_queue'])} pending")
        st.caption("Ambiguous matches never auto-merge; they wait here for a human to confirm.")
        st.dataframe(
            data["review_queue"][["name_a", "name_b", "confidence_score", "reason"]],
            hide_index=True, use_container_width=True, height=200,
        )
    with gov_col2:
        audit = load_audit_log()
        st.markdown(f"**Audit log** — {len(audit)} lookups recorded")
        st.caption("Every customer lookup on the Return Lookup screen, who looked up whom, when.")
        st.dataframe(audit.tail(20).iloc[::-1], hide_index=True, use_container_width=True, height=200)


if screen == "Return Lookup":
    screen_return_lookup()
elif screen == "True Inventory":
    screen_true_inventory()
else:
    screen_outreach_analytics()
