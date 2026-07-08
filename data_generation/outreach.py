"""Generate raw/outreach_log.csv -- "the old world," the baseline the
new reason-driven outreach queue (Phase 3) has to beat.

Deliberately dumb by design: sends are time-triggered only (day_7 /
day_30 since signup), blasted at whatever raw source record exists with
no entity resolution behind it, with no awareness of return status, VIP
tier, or restocked inventory. Low open/reply/conversion rates are the
point -- they're the evidence for why reason-driven outreach is needed.
"""
import pandas as pd

from common.config import DATA_END_DATE, DATA_START_DATE, N_OUTREACH
from common.rng import rng

TRIGGERS = ["day_7", "day_30"]
TRIGGER_WEIGHTS = [0.45, 0.55]

TEMPLATES = {
    "day_7": ["TPL_DAY7_THANKYOU", "TPL_DAY7_STYLING_TIPS"],
    "day_30": ["TPL_DAY30_WINBACK", "TPL_DAY30_RESTOCK_TEASER"],
}

OPEN_RATE = 0.34
REPLY_RATE_IF_OPENED = 0.09
PURCHASE_CONVERSION_RATE = 0.03


def _random_send_date():
    span = (DATA_END_DATE - DATA_START_DATE).days
    return DATA_START_DATE + pd.Timedelta(days=rng.randint(0, span))


def generate_outreach(all_contactable_refs):
    rows = []
    for i in range(1, N_OUTREACH + 1):
        ref = rng.choice(all_contactable_refs)
        trigger = rng.choices(TRIGGERS, weights=TRIGGER_WEIGHTS)[0]
        template_id = rng.choice(TEMPLATES[trigger])

        opened = rng.random() < OPEN_RATE
        replied = opened and rng.random() < REPLY_RATE_IF_OPENED
        purchased_within_30d = rng.random() < PURCHASE_CONVERSION_RATE

        rows.append({
            "send_id": f"SEND-{i:05d}",
            "source_customer_ref": ref,
            "template_id": template_id,
            "trigger": trigger,
            "send_date": _random_send_date().isoformat(),
            "opened_flag": opened,
            "replied_flag": replied,
            "purchased_within_30d_flag": purchased_within_30d,
        })
    return pd.DataFrame(rows)
