"""Manager analytics (Screen 3): three views the brief asks for.

1. Associate time lost to return calls -- turns call_log.csv into a
   concrete "hours per week" number for the problem statement.
2. Return-reason clustering by product -- which styles are getting
   returned for the same reason disproportionately often (the "this
   style runs small" insight retail teams actually act on: resize the
   fit guide, not just process the return).
3. Reason-driven vs. time-blast outreach. This is NOT a fabricated A/B
   test -- the new queue (outreach_queue.csv) hasn't been sent to
   anyone yet, so it has no real conversion number. What's honest to
   show: the old system's actual historical performance as a baseline,
   and the new queue's composition/volume as what's about to replace it.
"""
import pandas as pd

CALL_LOG_WINDOW_DAYS = 180
RUNS_SMALL_LARGE_THRESHOLD = 0.40
MIN_RETURNS_FOR_STYLE_INSIGHT = 5


def time_lost_analytics(call_log_df: pd.DataFrame) -> dict:
    inquiry_calls = call_log_df[call_log_df["reason_code"] == "return_window_inquiry"]
    total_minutes = inquiry_calls["duration_minutes"].sum()
    weeks = CALL_LOG_WINDOW_DAYS / 7

    by_store = (
        inquiry_calls.groupby("store_location")["duration_minutes"]
        .agg(["sum", "count"])
        .rename(columns={"sum": "total_minutes", "count": "call_count"})
        .reset_index()
    )
    by_store["minutes_per_week"] = (by_store["total_minutes"] / weeks).round(1)

    return {
        "total_calls": int(len(inquiry_calls)),
        "total_hours": round(total_minutes / 60, 1),
        "hours_per_week": round(total_minutes / 60 / weeks, 1),
        "share_of_all_calls": round(len(inquiry_calls) / len(call_log_df), 3),
        "by_store": by_store,
    }


def return_reason_clustering(returns_df: pd.DataFrame, catalog_df: pd.DataFrame) -> pd.DataFrame:
    merged = returns_df.merge(catalog_df[["item_id", "style_name"]], on="item_id", how="left")

    counts = merged.groupby(["style_name", "return_reason"]).size().unstack(fill_value=0)
    counts["total_returns"] = counts.sum(axis=1)
    for reason in ["fit_large", "fit_small", "changed_mind", "quality"]:
        if reason not in counts.columns:
            counts[reason] = 0
        counts[f"{reason}_share"] = (counts[reason] / counts["total_returns"]).round(2)

    def insight(row):
        if row["total_returns"] < MIN_RETURNS_FOR_STYLE_INSIGHT:
            return ""
        if row["fit_small_share"] >= RUNS_SMALL_LARGE_THRESHOLD:
            return "Runs small"
        if row["fit_large_share"] >= RUNS_SMALL_LARGE_THRESHOLD:
            return "Runs large"
        if row["quality_share"] >= RUNS_SMALL_LARGE_THRESHOLD:
            return "Quality concern"
        return ""

    counts["insight"] = counts.apply(insight, axis=1)
    return counts.reset_index().sort_values("total_returns", ascending=False)


def outreach_comparison(outreach_log_df: pd.DataFrame, outreach_queue_df: pd.DataFrame) -> dict:
    old = {
        "total_sent": int(len(outreach_log_df)),
        "open_rate": round(outreach_log_df["opened_flag"].astype(str).eq("True").mean(), 3),
        "reply_rate": round(outreach_log_df["replied_flag"].astype(str).eq("True").mean(), 3),
        "purchase_conversion_rate": round(
            outreach_log_df["purchased_within_30d_flag"].astype(str).eq("True").mean(), 3
        ),
    }
    new = {
        "total_queued": int(len(outreach_queue_df)),
        "by_trigger_type": (
            outreach_queue_df["trigger_reason"].str.extract(r"^(Return window|VIP customer|Called asking)")[0]
            .value_counts().to_dict()
        ),
        "note": "No conversion data yet -- this queue hasn't been sent. Shown here is volume and targeting "
                "logic, not a real performance comparison. Conversion should be tracked once it goes live.",
    }
    return {"old_time_blast": old, "new_reason_driven": new}
