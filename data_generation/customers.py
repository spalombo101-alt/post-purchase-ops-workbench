"""Generate the messy customer source data: pos_customers.csv,
ecom_customers.csv, and payment_tokens.csv -- plus a ground-truth answer
key that Phase 2's entity-resolution spine will be graded against.

The core idea: generate 500 real ("true") people first, in a layer the
pipeline never sees, then fan each one out into one or more messy source
records according to the brief's spec. Because we know which records
came from the same true person, we can later check whether the spine
actually reunites them -- rather than just eyeballing plausibility.

Population layout (500 true people):
  - 275 pos_only     - only ever shopped in-store
  - 125 both         - shopped in-store and online
  - 100 ecom_only    - only ever shopped online

Of the 400 people with a POS presence, 60 (~15%) get two disconnected
POS records from separate visits, with zero overlapping contact fields
-- the "same person, two strangers on paper" case the brief calls out.
Of those 60:
  - 12 (~20%) share a payment token across both records -> Tier 1 exact
  - 34 have supporting context (same store, plausible gap) -> Tier 2
  - 14 have contradicting context (different store, big date gap) ->
    should land in the Tier 3 review queue

Of the 125 "both" people, the POS/ecom link is:
  - 75 via exact email match -> Tier 1
  - 35 via name-only fuzzy match with supporting context -> Tier 2
  - 15 via name-only fuzzy match with weak/contradicting context -> Tier 3
"""
import pandas as pd

from common.config import DATA_END_DATE, DATA_START_DATE, N_CUSTOMERS, STORE_LOCATIONS
from common.nicknames import has_nickname_variants, variant_for
from common.rng import fake, rng

N_POS_ONLY = 275
N_BOTH = 125
N_ECOM_ONLY = N_CUSTOMERS - N_POS_ONLY - N_BOTH  # 100

N_POS_DUP = 60
N_DUP_TOKEN_LINKED = 12
N_DUP_FUZZY_HARD = 14
# remainder of N_POS_DUP is fuzzy_easy

N_ECOM_FUZZY_HARD = 15
# remainder of (N_BOTH - exact_email) is fuzzy_easy


def _random_date(start, end):
    span = (end - start).days
    return start + pd.Timedelta(days=rng.randint(0, span))


def _offset_date_preserving_gap(anchor, gap_days, floor, ceiling):
    """anchor +/- gap_days, keeping the FULL gap wherever possible.

    A plain min(anchor + gap, ceiling) silently shrinks the gap whenever
    anchor is close to the ceiling -- which quietly turned some
    intended-to-be-hard (large gap) Tier 2/3 test cases into easy ones
    whenever the anchor date happened to land late in the data window.
    Falling back to the "before" direction keeps the intended gap size
    honest regardless of where the anchor falls.
    """
    after = anchor + pd.Timedelta(days=gap_days)
    if after <= ceiling:
        return after
    before = anchor - pd.Timedelta(days=gap_days)
    if before >= floor:
        return before
    return ceiling if (ceiling - anchor).days >= (anchor - floor).days else floor


def _random_phone():
    return f"({rng.randint(201, 989)}) {rng.randint(200, 999)}-{rng.randint(1000, 9999)}"


def _pick_contact_pattern():
    r = rng.random()
    if r < 0.35:
        return "phone_only"
    elif r < 0.65:
        return "email_only"
    return "all_three"


def _build_true_people():
    groups = (
        ["pos_only"] * N_POS_ONLY
        + ["both"] * N_BOTH
        + ["ecom_only"] * N_ECOM_ONLY
    )
    rng.shuffle(groups)

    people = []
    for i, group in enumerate(groups):
        people.append({
            "true_person_id": i,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "group": group,
            "home_store": rng.choice(STORE_LOCATIONS),
            "pos_dup": False,
            "pos_subtier": None,
            "ecom_link_type": None,
        })

    has_pos_idx = [p["true_person_id"] for p in people if p["group"] in ("pos_only", "both")]
    rng.shuffle(has_pos_idx)
    dup_idx = set(has_pos_idx[:N_POS_DUP])
    dup_idx_ordered = has_pos_idx[:N_POS_DUP]
    token_linked = set(dup_idx_ordered[:N_DUP_TOKEN_LINKED])
    fuzzy_hard = set(dup_idx_ordered[N_DUP_TOKEN_LINKED:N_DUP_TOKEN_LINKED + N_DUP_FUZZY_HARD])
    fuzzy_easy = set(dup_idx_ordered[N_DUP_TOKEN_LINKED + N_DUP_FUZZY_HARD:])

    both_idx = [p["true_person_id"] for p in people if p["group"] == "both"]
    rng.shuffle(both_idx)
    exact_email_idx = set(both_idx[:75])
    remaining_both = both_idx[75:]
    ecom_fuzzy_hard = set(remaining_both[:N_ECOM_FUZZY_HARD])
    ecom_fuzzy_easy = set(remaining_both[N_ECOM_FUZZY_HARD:])

    for p in people:
        tpid = p["true_person_id"]
        if tpid in dup_idx:
            p["pos_dup"] = True
            if tpid in token_linked:
                p["pos_subtier"] = "token_linked"
            elif tpid in fuzzy_hard:
                p["pos_subtier"] = "fuzzy_hard"
            else:
                p["pos_subtier"] = "fuzzy_easy"
        if p["group"] == "both":
            if tpid in exact_email_idx:
                p["ecom_link_type"] = "exact_email"
            elif tpid in ecom_fuzzy_hard:
                p["ecom_link_type"] = "fuzzy_hard"
            else:
                p["ecom_link_type"] = "fuzzy_easy"

    return people


def _inject_kathryn_kate_scenario(people):
    """Force one deterministic, human-checkable Tier 2 case: the exact
    Kathryn Miller / Kate Miller scenario named in the project brief as
    the Phase 1 checkpoint. We pick the first person already randomly
    assigned to the pos_only + fuzzy_easy dup bucket and overwrite their
    name, so bucket counts stay consistent."""
    for p in people:
        if p["group"] == "pos_only" and p["pos_subtier"] == "fuzzy_easy":
            p["first_name"] = "Kathryn"
            p["last_name"] = "Miller"
            return p["true_person_id"]
    raise RuntimeError("no fuzzy_easy pos_only candidate found for Kathryn/Kate scenario")


def generate_customers():
    people = _build_true_people()
    kathryn_id = _inject_kathryn_kate_scenario(people)

    pos_rows = []
    ecom_rows = []
    token_rows = []
    ground_truth_rows = []

    pos_counter = 1
    ecom_counter = 1
    token_counter = 1
    used_emails = set()
    used_phones = set()

    def fresh_email():
        while True:
            e = fake.free_email()
            if e not in used_emails:
                used_emails.add(e)
                return e

    def fresh_phone():
        while True:
            ph = _random_phone()
            if ph not in used_phones:
                used_phones.add(ph)
                return ph

    for p in people:
        tpid = p["true_person_id"]
        pos_ids_for_person = []
        ecom_id_for_person = None

        if p["group"] in ("pos_only", "both"):
            n_records = 2 if p["pos_dup"] else 1
            record1_created = _random_date(
                DATA_START_DATE - pd.Timedelta(days=365), DATA_END_DATE - pd.Timedelta(days=14)
            )

            force_email_r1 = p["group"] == "both" and p["ecom_link_type"] == "exact_email"
            pattern1 = (rng.choice(["email_only", "all_three"]) if force_email_r1
                        else _pick_contact_pattern())
            name1 = p["first_name"]
            record1_email = fresh_email() if pattern1 in ("email_only", "all_three") else ""
            record1_phone = fresh_phone() if pattern1 in ("phone_only", "all_three") else ""

            pos_id_1 = f"POS-{pos_counter:05d}"
            pos_counter += 1
            pos_rows.append({
                "pos_record_id": pos_id_1,
                "name": f"{name1} {p['last_name']}",
                "phone": record1_phone,
                "email": record1_email,
                "store_signed_up": p["home_store"],
                "created_date": record1_created.isoformat(),
            })
            pos_ids_for_person.append(pos_id_1)

            if n_records == 2:
                if p["pos_subtier"] == "fuzzy_hard":
                    gap_days = rng.randint(300, 500)
                    other_stores = [s for s in STORE_LOCATIONS if s != p["home_store"]]
                    store2 = rng.choice(other_stores)
                else:
                    gap_days = rng.randint(30, 180)
                    store2 = p["home_store"]
                record2_created = _offset_date_preserving_gap(
                    record1_created, gap_days,
                    floor=DATA_START_DATE - pd.Timedelta(days=365), ceiling=DATA_END_DATE - pd.Timedelta(days=1),
                )

                if tpid == kathryn_id:
                    name2 = "Kate"  # the literal brief example, not just any nickname variant
                else:
                    name2 = (variant_for(name1, rng) if has_nickname_variants(name1) and rng.random() < 0.8
                              else name1)

                pattern2 = _pick_contact_pattern()
                record2_email = fresh_email() if pattern2 in ("email_only", "all_three") else ""
                record2_phone = fresh_phone() if pattern2 in ("phone_only", "all_three") else ""

                pos_id_2 = f"POS-{pos_counter:05d}"
                pos_counter += 1
                pos_rows.append({
                    "pos_record_id": pos_id_2,
                    "name": f"{name2} {p['last_name']}",
                    "phone": record2_phone,
                    "email": record2_email,
                    "store_signed_up": store2,
                    "created_date": record2_created.isoformat(),
                })
                pos_ids_for_person.append(pos_id_2)

                if p["pos_subtier"] == "token_linked":
                    token_id = f"TOK-{token_counter:05d}"
                    token_counter += 1
                    for pid, created in ((pos_id_1, record1_created), (pos_id_2, record2_created)):
                        token_rows.append({
                            "token_id": token_id,
                            "source_customer_ref": pid,
                            "first_seen": created.isoformat(),
                            "last_seen": min(
                                created + pd.Timedelta(days=rng.randint(0, 60)), DATA_END_DATE
                            ).isoformat(),
                        })

        if p["group"] in ("both", "ecom_only"):
            if p["group"] == "both" and p["ecom_link_type"] == "exact_email":
                ecom_name = f"{p['first_name']} {p['last_name']}"
                ecom_email = record1_email if record1_email else fresh_email()
                ecom_created = min(
                    record1_created + pd.Timedelta(days=rng.randint(0, 120)), DATA_END_DATE - pd.Timedelta(days=1)
                )
            elif p["group"] == "both":
                gap_days = rng.randint(400, 550) if p["ecom_link_type"] == "fuzzy_hard" else rng.randint(20, 180)
                fname = (variant_for(p["first_name"], rng) if has_nickname_variants(p["first_name"]) and rng.random() < 0.7
                          else p["first_name"])
                ecom_name = f"{fname} {p['last_name']}"
                ecom_email = fresh_email()
                # Anchor off the MOST RECENT pos record (not always record1):
                # if this person also has a pos_dup, record2 is the record
                # whose timing would otherwise "bridge" pos1 and pos2 back
                # together through ecom regardless of how far ecom is from
                # record1 -- so the intended gap has to hold against both.
                ecom_anchor = record2_created if n_records == 2 else record1_created
                ecom_created = _offset_date_preserving_gap(
                    ecom_anchor, gap_days,
                    floor=DATA_START_DATE - pd.Timedelta(days=365), ceiling=DATA_END_DATE - pd.Timedelta(days=1),
                )
            else:
                ecom_name = f"{p['first_name']} {p['last_name']}"
                ecom_email = fresh_email()
                ecom_created = _random_date(DATA_START_DATE - pd.Timedelta(days=365), DATA_END_DATE - pd.Timedelta(days=14))

            ecom_id = f"ECOM-{ecom_counter:05d}"
            ecom_counter += 1
            ecom_rows.append({
                "ecom_id": ecom_id,
                "full_name": ecom_name,
                "email": ecom_email,
                "created_date": ecom_created.isoformat(),
            })
            ecom_id_for_person = ecom_id

        pos_dup_tier = {
            "token_linked": "tier1_exact", "fuzzy_easy": "tier2_fuzzy", "fuzzy_hard": "tier3_ambiguous",
        }.get(p["pos_subtier"], "n/a")
        ecom_link_tier = {
            "exact_email": "tier1_exact", "fuzzy_easy": "tier2_fuzzy", "fuzzy_hard": "tier3_ambiguous",
        }.get(p["ecom_link_type"], "n/a")

        tier_rank = {"tier3_ambiguous": 3, "tier2_fuzzy": 2, "tier1_exact": 1, "n/a": 0}
        expected_tier = max([pos_dup_tier, ecom_link_tier], key=lambda t: tier_rank[t])
        if expected_tier == "n/a":
            expected_tier = "single_record"

        ground_truth_rows.append({
            "true_person_id": tpid,
            "first_name": p["first_name"],
            "last_name": p["last_name"],
            "group": p["group"],
            "pos_record_ids": ";".join(pos_ids_for_person),
            "ecom_id": ecom_id_for_person or "",
            "pos_dup_expected_tier": pos_dup_tier,
            "ecom_link_expected_tier": ecom_link_tier,
            "expected_resolution_tier": expected_tier,
            "home_store": p["home_store"],
        })

    # Noise tokens: give a modest random slice of remaining source
    # records a solo payment token (realistic card-payment exhaust that
    # is NOT needed for resolution, since it never repeats across a
    # second ref). Keeps the file from looking suspiciously sparse.
    already_tokened = {r["source_customer_ref"] for r in token_rows}
    all_refs = [r["pos_record_id"] for r in pos_rows] + [r["ecom_id"] for r in ecom_rows]
    noise_candidates = [r for r in all_refs if r not in already_tokened]
    rng.shuffle(noise_candidates)
    for ref in noise_candidates[: int(len(noise_candidates) * 0.25)]:
        token_rows.append({
            "token_id": f"TOK-{token_counter:05d}",
            "source_customer_ref": ref,
            "first_seen": _random_date(DATA_START_DATE, DATA_END_DATE).isoformat(),
            "last_seen": _random_date(DATA_START_DATE, DATA_END_DATE).isoformat(),
        })
        token_counter += 1

    pos_df = pd.DataFrame(pos_rows)
    ecom_df = pd.DataFrame(ecom_rows)
    tokens_df = pd.DataFrame(token_rows)
    ground_truth_df = pd.DataFrame(ground_truth_rows)

    customer_index = []
    for _, row in ground_truth_df.iterrows():
        customer_index.append({
            "true_person_id": row["true_person_id"],
            "pos_ids": row["pos_record_ids"].split(";") if row["pos_record_ids"] else [],
            "ecom_id": row["ecom_id"] or None,
            "home_store": row["home_store"],
        })

    print(f"  Kathryn/Kate checkpoint: true_person_id={kathryn_id}")
    return pos_df, ecom_df, tokens_df, ground_truth_df, customer_index
