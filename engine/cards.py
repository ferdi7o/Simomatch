"""Visual/statistical cards, generated with a dedicated RNG, never physics RNG."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CardEvent:
    kind: str
    team: str
    minute: int


def create_card_schedule(rng, teams):
    yellow = rng.randint(0, 5)
    kinds = ['yellow_card']*yellow + (['red_card'] if rng.random() < .08 else [])
    rng.shuffle(kinds)
    count = len(kinds)
    if not count:
        return []
    if count == 1:
        return [CardEvent(kinds[0], rng.choice(teams), rng.randint(5, 86))]
    # Stratified jitter spreads events across the match, with >=8 minutes
    # between slots even when all six possible cards are drawn.
    width = 82/count
    return [CardEvent(kind, rng.choice(teams), round(4+(i+.5+rng.uniform(-.2, .2))*width))
            for i, kind in enumerate(kinds)]
