"""Shared constants for data generation and, later, the pipeline.

Keeping these in one place means the entity-resolution logic (Phase 1's
"spine") and the data generator agree on what a store name looks like,
what "today" is, etc.
"""
from datetime import date, timedelta

RANDOM_SEED = 42

STORE_LOCATIONS = ["Madison Ave", "Bleecker", "SoHo", "Flatiron"]
ONLINE_CHANNEL = "online"
IN_STORE_CHANNEL = "in_store"

# Fixed "as of" date the whole synthetic dataset is generated relative to.
# Anchoring to a fixed date (rather than the real today) keeps the dataset
# reproducible run over run.
TODAY = date(2026, 7, 6)

DATA_START_DATE = date(2025, 1, 6)  # ~18 months of purchase history
DATA_END_DATE = TODAY - timedelta(days=1)

# Target volumes from the project brief.
N_CUSTOMERS = 500
N_ORDERS = 3000
N_RETURNS = 450
N_CALL_LOGS = 600
N_OUTREACH = 1200

# The brief's "ghost stock" demo moment: a specific item returned at
# Bleecker, sellable, not yet reshelved, while the system says 0 in stock.
# Returns and inventory generation both read this so the two files agree.
DEMO_HERO_STORE = "Bleecker"
DEMO_HERO_RETURN_DAYS_AGO = 2
