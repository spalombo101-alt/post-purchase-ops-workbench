"""Single shared random source for the whole generator.

Every data_generation module imports `fake` and `rng` from here instead of
constructing their own, so one call to seed_all() makes the entire dataset
reproducible regardless of which order the generation modules run in.
"""
import random

from faker import Faker

from common.config import RANDOM_SEED

fake = Faker("en_US")
rng = random.Random(RANDOM_SEED)


def seed_all(seed: int = RANDOM_SEED) -> None:
    random.seed(seed)
    rng.seed(seed)
    Faker.seed(seed)
