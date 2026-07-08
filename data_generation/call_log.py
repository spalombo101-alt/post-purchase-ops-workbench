"""Generate raw/call_log.csv.

This file's job is narrative, not structural: it quantifies the "7
calls a day asking about return windows" problem from the brief so the
manager analytics screen has something concrete to show (associate time
lost). return_window_inquiry calls are deliberately the most common
reason code and run longer, since today an associate has to dig through
a back-office system and do manual math to answer them.
"""
import pandas as pd

from common.config import N_CALL_LOGS, STORE_LOCATIONS, TODAY
from common.rng import rng

REASON_CODES = ["return_window_inquiry", "stock_check", "order_status", "other"]
REASON_WEIGHTS = [0.60, 0.20, 0.12, 0.08]

CALL_LOG_WINDOW_DAYS = 180


def _duration_for(reason_code):
    if reason_code == "return_window_inquiry":
        return round(rng.uniform(4, 12), 1)
    return round(rng.uniform(2, 6), 1)


def _random_timestamp():
    days_ago = rng.randint(0, CALL_LOG_WINDOW_DAYS)
    call_date = TODAY - pd.Timedelta(days=days_ago)
    hour = rng.randint(10, 18)
    minute = rng.randint(0, 59)
    return pd.Timestamp(call_date).replace(hour=hour, minute=minute)


def generate_call_log():
    rows = []
    for i in range(1, N_CALL_LOGS + 1):
        reason_code = rng.choices(REASON_CODES, weights=REASON_WEIGHTS)[0]
        rows.append({
            "call_id": f"CALL-{i:05d}",
            "store_location": rng.choice(STORE_LOCATIONS),
            "timestamp": _random_timestamp().isoformat(sep=" "),
            "reason_code": reason_code,
            "duration_minutes": _duration_for(reason_code),
        })
    return pd.DataFrame(rows)
