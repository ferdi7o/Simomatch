"""Visual-only arena data. No radii, angles, speeds or collision parameters."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EffectStyle:
    trail_colors: tuple = ((.3, .75, 1), (1, .45, .22))
    trail_lifetime: float = .18
    spark_color: tuple = (1, .85, .45)
    flash_color: tuple = (.65, .9, 1)
    spark_count: int = 6


@dataclass(frozen=True)
class ArenaTheme:
    background_color: tuple
    background_image: str
    palette: tuple
    atmosphere_color: tuple
    glow_strength: float = 1.
    effects: EffectStyle = EffectStyle()

    @property
    def image_path(self):
        return Path(__file__).resolve().parents[1] / self.background_image


THEMES = {
    'neon_purple': ArenaTheme(
        (.012, .008, .025, 1), 'assets/backgrounds/neon_purple.png',
        ((.65, .25, 1), (.95, .4, .9), (.45, .4, 1), (.92, .85, 1)),
        (.38, .12, .6), 1.05,
        EffectStyle(((.65, .4, 1), (1, .4, .8)), .18, (.9, .65, 1), (.85, .6, 1))),
    'fire_arena': ArenaTheme(
        (.025, .008, .004, 1), 'assets/backgrounds/fire_arena.png',
        ((1, .15, .04), (1, .42, .06), (1, .82, .18), (1, .95, .65)),
        (.7, .16, .025), 1.15,
        EffectStyle(((1, .4, .08), (1, .8, .2)), .16, (1, .7, .18), (1, .45, .15), 8)),
    'electric_blue': ArenaTheme(
        (.004, .012, .025, 1), 'assets/backgrounds/electric_blue.png',
        ((.06, .4, 1), (.08, .8, 1), (.5, .95, 1), (.9, .98, 1)),
        (.04, .35, .65), 1.1,
        EffectStyle(((.1, .7, 1), (.55, .9, 1)), .20, (.6, .9, 1), (.3, .85, 1))),
    'rainbow_neon': ArenaTheme(
        (.006, .014, .012, 1), 'assets/backgrounds/rainbow_neon.png',
        ((.12, 1, .55), (1, .86, .18), (1, .38, .10), (.12, .6, 1), (.9, .98, 1)),
        (.04, .5, .28)),
    'emerald_arena': ArenaTheme(
        (.004, .02, .012, 1), 'assets/backgrounds/emerald_arena.png',
        ((.06, .8, .3), (.18, 1, .55), (.55, 1, .8), (.9, 1, .95)),
        (.03, .5, .2), .9,
        EffectStyle(((.15, 1, .5), (.6, 1, .85)), .18, (.65, 1, .6), (.4, 1, .75))),
}

# Existing in-memory callers can retain the old labels; no user data migration.
LEGACY_THEMES = {'Neon mor': 'neon_purple', 'Gece yeşili': 'emerald_arena', 'Okyanus': 'electric_blue'}


def theme_id(name):
    key = LEGACY_THEMES.get(name, name)
    if key not in THEMES:
        raise ValueError('Geçersiz arka plan teması.')
    return key


def get_theme(name):
    return THEMES[theme_id(name)]
