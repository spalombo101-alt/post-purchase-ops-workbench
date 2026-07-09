"""Governance requirement: every customer lookup recorded (who, whom,
when), viewable in manager mode. A real audit log has to survive past
the current session, so this appends to a CSV file on disk rather than
just holding it in Streamlit's session state.
"""
import csv
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIT_LOG_PATH = os.path.join(LOGS_DIR, "audit_log.csv")

FIELDS = ["timestamp", "associate_name", "customer_id", "customer_name"]


def log_lookup(associate_name: str, customer_id: str, customer_name: str) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    is_new = not os.path.exists(AUDIT_LOG_PATH)
    with open(AUDIT_LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "associate_name": associate_name or "(unnamed)",
            "customer_id": customer_id,
            "customer_name": customer_name,
        })


def load_audit_log():
    import pandas as pd
    if not os.path.exists(AUDIT_LOG_PATH):
        return pd.DataFrame(columns=FIELDS)
    return pd.read_csv(AUDIT_LOG_PATH, keep_default_na=False)
