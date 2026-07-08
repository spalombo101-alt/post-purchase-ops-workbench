"""The entity-resolution "spine": build customers_spine.csv (one row per
real person, permanent customer_id) from the messy unified customer
records, plus review_queue.csv for anything too ambiguous to auto-merge.

Three tiers, most confident first:

  Tier 1 -- exact match on email, phone, or payment token. Treated as a
  graph: if A-B share an email and B-C share a phone, all three resolve
  to one person via union-find, even though A and C share nothing
  directly.

  Tier 2 -- candidacy requires same last name AND a first-name match
  that is exact or a known nickname-group variant (Kathryn/Kate, not
  generic spelling similarity -- see the note in _name_strength() on
  why raw edit-distance was tried and deliberately dropped). That alone
  isn't enough to link automatically: a confidence score is then
  computed from supporting context (same store, plausible gap between
  record dates). Score >= AUTO_LINK_THRESHOLD -> auto-link. Below it ->
  Tier 3.

  Tier 3 -- same-name candidates whose context is weak or contradictory
  never get merged. They're written to review_queue.csv with the
  evidence, for a human to confirm or reject.

Everything gets a confidence-scored trail back to source records --
nothing merges silently.
"""
import pandas as pd

from common.nicknames import same_nickname_group

AUTO_LINK_THRESHOLD = 0.75
DATE_PLAUSIBLE_DAYS = 180
DATE_IMPLAUSIBLE_DAYS = 500


class UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1

    def clusters(self):
        groups = {}
        for item in self.parent:
            groups.setdefault(self.find(item), []).append(item)
        return list(groups.values())


def _date_plausibility(gap_days: int) -> float:
    if gap_days <= DATE_PLAUSIBLE_DAYS:
        return 1.0
    if gap_days >= DATE_IMPLAUSIBLE_DAYS:
        return 0.0
    span = DATE_IMPLAUSIBLE_DAYS - DATE_PLAUSIBLE_DAYS
    return 1.0 - (gap_days - DATE_PLAUSIBLE_DAYS) / span


def _name_strength(first_a: str, first_b: str):
    """Returns (strength, human-readable note) or (None, None) if the two
    first names show no meaningful similarity at all -- i.e. not even a
    Tier 2 candidate.

    Deliberately does NOT fall back to generic string-similarity
    (e.g. difflib ratio) for anything outside the nickname table. Tried
    it first; it doesn't work: "Kathryn"/"Kathyrn" (a real transposition
    typo) and "Daniel"/"Danielle" (two different people's names) score
    the identical 0.857 ratio. No threshold separates "same name,
    typo" from "different name, coincidentally similar" -- so any floor
    either lets both through (false merges of different people) or
    blocks both (defeats the point). The brief's own Tier 2 spec is
    "nickname variants," not generic spelling similarity, so this
    sticks to that rather than a threshold that can't be made safe.
    """
    a, b = first_a.strip(), first_b.strip()
    if a.lower() == b.lower():
        return 1.0, f"same first name ({a})"
    if same_nickname_group(a, b):
        return 0.85, f"nickname variants ({a} / {b})"
    return None, None


def _context_score(rec_a, rec_b):
    gap_days = abs((rec_a["created_date"] - rec_b["created_date"]).days)
    dp = _date_plausibility(gap_days)
    has_store = pd.notna(rec_a["store"]) and pd.notna(rec_b["store"])
    if has_store:
        same_store = rec_a["store"] == rec_b["store"]
        score = 0.5 * (1.0 if same_store else 0.0) + 0.5 * dp
        store_note = (f"same store ({rec_a['store']})" if same_store
                       else f"different store ({rec_a['store']} vs {rec_b['store']})")
    else:
        score = dp
        store_note = "store not comparable (online record involved)"
    return score, gap_days, store_note


def _exact_match_edges(unified_df, tokens_df):
    edges = []
    for field in ("email", "phone"):
        for _, group in unified_df.dropna(subset=[field]).groupby(field):
            refs = group["ref"].tolist()
            for i in range(1, len(refs)):
                edges.append((refs[0], refs[i], 1, 1.0, f"shared {field}"))

    for _, group in tokens_df.groupby("token_id"):
        refs = group["source_customer_ref"].unique().tolist()
        for i in range(1, len(refs)):
            edges.append((refs[0], refs[i], 1, 1.0, "shared payment token"))
    return edges


def _fuzzy_candidate_edges(unified_df):
    auto_link_edges = []
    review_candidates = []

    by_last_name = unified_df[unified_df["last_name"] != ""].groupby("last_name")
    for last_name, group in by_last_name:
        if len(group) < 2:
            continue
        records = group.to_dict("records")
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                rec_a, rec_b = records[i], records[j]
                strength, name_note = _name_strength(rec_a["first_name"], rec_b["first_name"])
                if strength is None:
                    continue
                context, gap_days, store_note = _context_score(rec_a, rec_b)
                confidence = round(0.4 * strength + 0.6 * context, 3)
                reason = f"{name_note}; same last name ({last_name}); {store_note}; {gap_days} days apart"

                if confidence >= AUTO_LINK_THRESHOLD:
                    auto_link_edges.append((rec_a["ref"], rec_b["ref"], 2, confidence, reason))
                else:
                    review_candidates.append({
                        "ref_a": rec_a["ref"], "ref_b": rec_b["ref"],
                        "name_a": f"{rec_a['first_name']} {rec_a['last_name']}",
                        "name_b": f"{rec_b['first_name']} {rec_b['last_name']}",
                        "confidence_score": confidence,
                        "reason": reason,
                    })
    return auto_link_edges, review_candidates


def build_spine(unified_df, tokens_df):
    uf = UnionFind(unified_df["ref"].tolist())

    tier1_edges = _exact_match_edges(unified_df, tokens_df)
    for a, b, _, _, _ in tier1_edges:
        uf.union(a, b)

    tier2_edges, review_candidates = _fuzzy_candidate_edges(unified_df)
    for a, b, _, _, _ in tier2_edges:
        uf.union(a, b)

    all_edges = tier1_edges + tier2_edges
    best_edge_for_ref = {}
    for a, b, tier, confidence, reason in all_edges:
        for this_ref, other_ref in ((a, b), (b, a)):
            current = best_edge_for_ref.get(this_ref)
            if current is None or confidence > current[1]:
                best_edge_for_ref[this_ref] = (tier, confidence, reason, other_ref)

    records_by_ref = unified_df.set_index("ref").to_dict("index")

    spine_rows = []
    for cluster_num, cluster in enumerate(sorted(uf.clusters(), key=lambda c: min(c)), start=1):
        customer_id = f"CUST-{cluster_num:05d}"
        member_records = [records_by_ref[ref] for ref in cluster]

        # Canonical identity: prefer the most complete / earliest record.
        anchor = min(
            member_records,
            key=lambda r: (-(pd.notna(r["phone"]) + pd.notna(r["email"])), r["created_date"]),
        )

        linked_parts = []
        max_tier_seen = 0
        for ref in cluster:
            edge = best_edge_for_ref.get(ref)
            if edge:
                tier, confidence, reason, other_ref = edge
                max_tier_seen = max(max_tier_seen, tier)
                linked_parts.append(f"{ref}:tier{tier}:conf={confidence:.2f}:via={other_ref}")
            else:
                linked_parts.append(f"{ref}:anchor")

        spine_rows.append({
            "customer_id": customer_id,
            "canonical_name": f"{anchor['first_name']} {anchor['last_name']}",
            "canonical_email": anchor["email"] if pd.notna(anchor["email"]) else "",
            "canonical_phone": anchor["phone"] if pd.notna(anchor["phone"]) else "",
            "record_count": len(cluster),
            "resolution_tier": f"tier{max_tier_seen}" if max_tier_seen else "single_record",
            "linked_source_records": ";".join(linked_parts),
        })

    spine_df = pd.DataFrame(spine_rows)

    review_rows = []
    for i, cand in enumerate(review_candidates, start=1):
        cand["review_id"] = f"REV-{i:05d}"
        cand["status"] = "pending"
        review_rows.append(cand)
    review_df = pd.DataFrame(review_rows, columns=[
        "review_id", "ref_a", "name_a", "ref_b", "name_b", "confidence_score", "reason", "status",
    ])

    ref_to_customer_id = {}
    for row in spine_rows:
        for part in row["linked_source_records"].split(";"):
            ref = part.split(":")[0]
            ref_to_customer_id[ref] = row["customer_id"]

    return spine_df, review_df, ref_to_customer_id
