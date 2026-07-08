What we did tonight

1. Built a fake but realistic dataset for a denim retailer. Since there's no real company data, we generated 500 fake customers, ~3,000 orders, 450 returns, plus inventory, call logs, and marketing outreach records — all with the kind of messiness real retail systems actually have: inconsistent date formats, missing store info, customers who show up as multiple disconnected records because a different cashier typed their info differently each visit, etc.

2. Built the "spine" — the thing that untangles duplicate customers. The core problem this whole project solves is: the same customer can look like 2-3 different people across different systems (in-store checkout, online store, loyalty card). We built a three-tier detective system:
- Tier 1: if two records share an exact email, phone, or card, auto-link them — certain match.
- Tier 2: if two records have a matching-ish name (like "Kathryn" vs "Kate") plus supporting evidence (same store, plausible timing), auto-link with a confidence score.
- Tier 3: if it's genuinely unclear, don't guess — flag it for a human to check by hand.

3. Graded our own work instead of just eyeballing it. Because we secretly tracked which fake records belonged to the same fake person while generating the data, we could check the spine's homework. Final score: it correctly reunited all 136 customers it should have, correctly left all 29 ambiguous cases for human review, and never once wrongly merged two different people into one profile. Along the way we caught and fixed two real bugs (a name-matching approach that would've confused "Michael" with "Michele," and a data-generation glitch that made some test cases accidentally too easy).

4. Put it on GitHub. It's saved, versioned, and live at your repo so it's not just sitting in this chat session.

How much is left

The brief splits this into 3 weekends. We finished weekend 1 (Phase 1) tonight: data + spine. Two more chunks remain:

Phase 2 — next up:
- Add customer stats (lifetime spend, return rate, etc.) and judgment calls (VIP / fraud-watch / relationship tier)
- Calculate each order's actual return window (not a fixed rule — adjusted by customer tier)
- Calculate true inventory (official count + sellable items sitting unprocessed from returns) — this is the "ghost stock" moment that's the centerpiece demo
- Build the first two screens of the actual app: return lookup, and true inventory search

Phase 3 — after that:
- Outreach queue (who to contact and why, replacing generic blast emails)
- Manager analytics screen (time lost to calls, return patterns, etc.)
- Governance layer (associate vs. manager view, audit log, consent rules)
- README, a 1–2 page memo, and a 3-minute walkthrough video

Roughly: we're about a third of the way through the full build, and it's the least visually interesting third — Phase 2 is where it starts looking like an actual usable tool.
