"""Validated match configuration shared by forms and the simulation."""
from dataclasses import dataclass
from math import isfinite
from config import (DISK_RADIUS, MIN_DISK_RADIUS, MAX_DISK_RADIUS, GOAL_SPEED_DEGREES,
                    MIN_GOAL_SPEED_DEGREES, MAX_GOAL_SPEED_DEGREES,
                    GOAL_SIZE_PERCENT, MIN_GOAL_SIZE_PERCENT, MAX_GOAL_SIZE_PERCENT)
from services.arena_themes import THEMES, theme_id
from services.backgrounds import BACKGROUNDS, DEFAULT_BACKGROUND


@dataclass(frozen=True)
class MatchSettings:
    home: dict
    away: dict
    radii: tuple = (DISK_RADIUS, DISK_RADIUS)
    duration: float = 55.
    theme: str = 'neon_purple'
    background: str = ''
    goal_speed_degrees: float = GOAL_SPEED_DEGREES
    goal_size_percent: float = GOAL_SIZE_PERCENT
    background_id: str = ''  # Empty preserves legacy theme/background behavior.

    def __post_init__(self):
        if self.background_id and self.background_id not in BACKGROUNDS:
            object.__setattr__(self, 'background_id', DEFAULT_BACKGROUND)
        if not isfinite(self.goal_size_percent) or not MIN_GOAL_SIZE_PERCENT <= self.goal_size_percent <= MAX_GOAL_SIZE_PERCENT:
            raise ValueError('Kale boyutu %60–150 arasında olmalıdır.')
        if self.home['id'] == self.away['id'] or self.home['name'] == self.away['name']:
            raise ValueError('Ev sahibi ve deplasman farklı takımlar olmalıdır.')
        if not isfinite(self.duration) or not 10 <= self.duration <= 600:
            raise ValueError('Maç süresi 10–600 saniye arasında olmalıdır.')
        if len(self.radii) != 2 or any(not isfinite(r) or not MIN_DISK_RADIUS <= r <= MAX_DISK_RADIUS for r in self.radii):
            raise ValueError(f'Logo boyutları {MIN_DISK_RADIUS:g}–{MAX_DISK_RADIUS:g} arasında olmalıdır.')
        object.__setattr__(self, 'theme', theme_id(self.theme))
        if not isfinite(self.goal_speed_degrees) or not MIN_GOAL_SPEED_DEGREES <= self.goal_speed_degrees <= MAX_GOAL_SPEED_DEGREES:
            raise ValueError('Kale dönüş hızı 30–180 derece/saniye arasında olmalıdır.')
