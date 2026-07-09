"""Nickname / diminutive groups.

Same table is used two ways:
  - data_generation: pick a plausible alternate first name for a
    duplicate-record scenario (e.g. a second in-store visit where the
    associate typed "Kate" instead of "Kathryn").
  - pipeline (Phase 2): given two first names, check whether they belong
    to the same nickname group as one signal feeding the Tier 2 fuzzy
    match confidence score.

Groups are deliberately small and common-name-only; this is not meant to
be an exhaustive nickname dictionary, just enough to make the synthetic
messiness realistic and give the matcher something real to key off of.
"""

NICKNAME_GROUPS = [
    {"Katherine", "Kathryn", "Kathy", "Kate", "Katie"},
    {"Robert", "Rob", "Bob", "Bobby"},
    {"William", "Bill", "Will", "Billy"},
    {"Elizabeth", "Liz", "Beth", "Eliza", "Lizzie"},
    {"Michael", "Mike", "Mikey"},
    {"Jennifer", "Jen", "Jenny"},
    {"Christopher", "Chris"},
    {"Alexandra", "Alex", "Sandra", "Sandy"},
    {"Samuel", "Sam", "Sammy"},
    {"Nicholas", "Nick", "Nicky"},
    {"Jonathan", "Jon", "Johnny"},
    {"Daniel", "Dan", "Danny"},
    {"Matthew", "Matt"},
    {"Andrew", "Andy", "Drew"},
    {"Joseph", "Joe", "Joey"},
    {"Margaret", "Maggie", "Meg", "Peggy"},
    {"Patricia", "Pat", "Patty", "Trish"},
    {"Jacqueline", "Jackie"},
    {"Deborah", "Debbie", "Deb"},
    {"Susan", "Sue", "Susie"},
    {"Benjamin", "Ben", "Benny"},
    {"Timothy", "Tim", "Timmy"},
    {"Rebecca", "Becky"},
    {"Victoria", "Vicky", "Tori"},
]

_NAME_TO_GROUP = {}
for _group in NICKNAME_GROUPS:
    for _name in _group:
        _NAME_TO_GROUP[_name.lower()] = _group


def has_nickname_variants(name: str) -> bool:
    return name.lower() in _NAME_TO_GROUP


def variant_for(name: str, rng) -> str:
    """Return a different name from the same nickname group, using rng (a
    random.Random instance) for the pick. Falls back to the input name if
    it isn't in any group."""
    group = _NAME_TO_GROUP.get(name.lower())
    if not group:
        return name
    # sorted(): set iteration order depends on the process's hash seed,
    # which is randomized per run -- without this, rng.choice() picks a
    # deterministic INDEX into a non-deterministically-ordered list, which
    # silently breaks the "fixed seed -> reproducible dataset" guarantee.
    choices = sorted(n for n in group if n.lower() != name.lower())
    return rng.choice(choices) if choices else name


def same_nickname_group(name_a: str, name_b: str) -> bool:
    a, b = name_a.lower(), name_b.lower()
    if a == b:
        return True
    group = _NAME_TO_GROUP.get(a)
    return bool(group) and b in {n.lower() for n in group}
