"""Dev-time-only tool: grade the spine against ground_truth/customers_ground_truth.csv.

Not part of the pipeline the app depends on -- this only works because
data_generation tagged every synthetic record with which real person it
came from. Real production data has no such answer key; this script
exists purely to check the matching logic before trusting it.

Checks three things:
  1. Every true person whose records SHOULD auto-merge (tier1/tier2 in
     ground truth) actually ends up under one customer_id.
  2. No two DIFFERENT true people ever end up sharing a customer_id
     (a false merge -- the dangerous failure mode).
  3. Every true person whose records are genuinely ambiguous (tier3)
     lands in review_queue.csv instead of being auto-merged.
"""
import os

import pandas as pd

from pipeline.ingest import load_raw, build_unified_customer_records
from pipeline.spine import build_spine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUND_TRUTH_PATH = os.path.join(PROJECT_ROOT, "ground_truth", "customers_ground_truth.csv")


def main():
    dfs = load_raw()
    unified = build_unified_customer_records(dfs["pos_customers"], dfs["ecom_customers"])
    spine_df, review_df, ref_to_customer_id = build_spine(unified, dfs["payment_tokens"])
    gt_df = pd.read_csv(GROUND_TRUTH_PATH, keep_default_na=False)

    review_pairs = set()
    for _, row in review_df.iterrows():
        review_pairs.add(frozenset([row["ref_a"], row["ref_b"]]))

    correctly_merged, wrongly_split = [], []
    correctly_queued, wrongly_not_queued, wrongly_auto_merged = [], [], []

    for _, row in gt_df.iterrows():
        refs = [r for r in row["pos_record_ids"].split(";") if r] + ([row["ecom_id"]] if row["ecom_id"] else [])
        if len(refs) < 2:
            continue

        customer_ids = {ref_to_customer_id.get(ref) for ref in refs}
        expected = row["expected_resolution_tier"]
        who = (row["true_person_id"], row["first_name"], row["last_name"], expected)

        if expected in ("tier1_exact", "tier2_fuzzy"):
            if len(customer_ids) == 1:
                correctly_merged.append(who)
            else:
                wrongly_split.append(who)
        elif expected == "tier3_ambiguous":
            if len(customer_ids) == 1:
                wrongly_auto_merged.append(who)
            else:
                pair_refs = frozenset(refs) if len(refs) == 2 else None
                in_queue = pair_refs in review_pairs if pair_refs else any(
                    frozenset([a, b]) in review_pairs for a in refs for b in refs if a != b
                )
                (correctly_queued if in_queue else wrongly_not_queued).append(who)

    # False-merge check: any customer_id spine cluster containing refs from >1 true person.
    ref_to_true_person = {}
    for _, row in gt_df.iterrows():
        refs = [r for r in row["pos_record_ids"].split(";") if r] + ([row["ecom_id"]] if row["ecom_id"] else [])
        for ref in refs:
            ref_to_true_person[ref] = row["true_person_id"]

    false_merges = []
    for _, srow in spine_df.iterrows():
        refs_in_cluster = [part.split(":")[0] for part in srow["linked_source_records"].split(";")]
        true_people = {ref_to_true_person[r] for r in refs_in_cluster if r in ref_to_true_person}
        if len(true_people) > 1:
            false_merges.append((srow["customer_id"], true_people, refs_in_cluster))

    print(f"Multi-record true people expected to auto-merge (tier1/tier2): "
          f"{len(correctly_merged) + len(wrongly_split)}")
    print(f"  correctly merged: {len(correctly_merged)}")
    print(f"  wrongly left split: {len(wrongly_split)}")
    for w in wrongly_split:
        print(f"    {w}")

    print(f"\nTier 3 (should stay unmerged, should appear in review_queue):")
    print(f"  correctly queued and NOT auto-merged: {len(correctly_queued)}")
    print(f"  left unmerged but missing from review_queue: {len(wrongly_not_queued)}")
    for w in wrongly_not_queued:
        print(f"    {w}")
    print(f"  WRONGLY auto-merged (false positive, should never happen): {len(wrongly_auto_merged)}")
    for w in wrongly_auto_merged:
        print(f"    {w}")

    print(f"\nFalse merges across different true people (should be 0): {len(false_merges)}")
    for fm in false_merges:
        print(f"    {fm}")

    print(f"\nSpine clusters: {len(spine_df)}  |  true people: {len(gt_df)}  |  review queue rows: {len(review_df)}")


if __name__ == "__main__":
    main()
