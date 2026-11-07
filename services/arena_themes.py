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
    ambient_rate: float = 0.
    ambient_flash: bool = False
    ambient_particle_rate: float = 0.


@dataclass(frozen=True)
class SpriteLayer:
    """Optional transparent full-ring atlas, read left-to-right, top-to-bottom.

    Artistic flames/lightning must come from actual assets, not colored lines.
    Layer scales only control visual thickness; the physical arena is unchanged.
    """
    image: str
    columns: int = 1
    rows: int = 1
    frames: int = 1
    fps: float = 16.
    inner_scale: float = .86
    outer_scale: float = 1.14
    opacity: float = .85
    rotation_degrees: float = 0.
    source_radius_pixels: float = 0.
    source_center_pixels: tuple = ()  # Source image pixels, origin at top-left.
    pulse_depth: float = 0.
    pulse_hz: float = 1.


@dataclass(frozen=True)
class ArenaTheme:
    background_color: tuple
    background_image: str
    palette: tuple
    atmosphere_color: tuple
    glow_strength: float = 1.
    effects: EffectStyle = EffectStyle()
    background_fallbacks: tuple = ()
    decorative_speed_degrees: float = 22.
    pulse_hz: float = .8
    layers: tuple = ()

    @property
    def image_path(self):
        return Path(__file__).resolve().parents[1] / self.background_image

    @property
    def image_paths(self):
        root = Path(__file__).resolve().parents[1]
        return tuple(root / path for path in (self.background_image, *self.background_fallbacks))


THEMES = {
    'neon_purple': ArenaTheme(
        (.012, .008, .025, 1), 'assets/background1.png',
        ((.65, .25, 1), (.95, .4, .9), (.45, .4, 1), (.92, .85, 1)),
        (.38, .12, .6), 1.05,
        EffectStyle(((.65, .4, 1), (1, .4, .8)), .18, (.9, .65, 1), (.85, .6, 1)),
        background_fallbacks=('assets/backgraund1.png', 'assets/backgrounds/neon_purple.png'),
        layers=(SpriteLayer('assets/effects/neon_purple/ring.png'),)),
    'fire_arena': ArenaTheme(
        (.025, .008, .004, 1), 'assets/backgrounds/fire_arena.png',
        ((1, .15, .04), (1, .42, .06), (1, .82, .18), (1, .95, .65)),
        (.7, .16, .025), 1.15,
        EffectStyle(((1, .4, .08), (1, .8, .2)), .16, (1, .7, .18), (1, .45, .15), 8, ambient_rate=3.),
        decorative_speed_degrees=16., pulse_hz=2.3,
        layers=(SpriteLayer('assets/arena_effects/fire_arena.png', inner_scale=.72, outer_scale=1.30,
                            opacity=.90, rotation_degrees=20, source_radius_pixels=445.25, source_center_pixels=(613.58, 627.79),
                            pulse_depth=.08, pulse_hz=1.2),)),
    'electric_blue': ArenaTheme(
        (.004, .012, .025, 1), 'assets/backgrounds/electric_blue.png',
        ((.06, .4, 1), (.08, .8, 1), (.5, .95, 1), (.9, .98, 1)),
        (.04, .35, .65), 1.1,
        EffectStyle(((.1, .7, 1), (.55, .9, 1)), .20, (.6, .9, 1), (.3, .85, 1),
                    ambient_rate=.7, ambient_flash=True, ambient_particle_rate=2.),
        decorative_speed_degrees=-28., pulse_hz=3.5,
        layers=(SpriteLayer('assets/arena_effects/electric_blue.png', inner_scale=.68, outer_scale=1.25,
                            opacity=.90, rotation_degrees=-30, source_radius_pixels=479.31, source_center_pixels=(619.52, 639.60),
                            pulse_depth=.03, pulse_hz=.7),)),
    'rainbow_neon': ArenaTheme(
        (.006, .014, .012, 1), 'assets/backgrounds/rainbow_neon.png',
        ((.12, 1, .55), (1, .86, .18), (1, .38, .10), (.12, .6, 1), (.9, .98, 1)),
        (.04, .5, .28), decorative_speed_degrees=35.,
        layers=(SpriteLayer('assets/arena_effects/rainbow_neon.png', inner_scale=.72, outer_scale=1.22,
                            opacity=.88, rotation_degrees=6, source_radius_pixels=494.68,
                            source_center_pixels=(615.16, 632.47), pulse_depth=.04, pulse_hz=.5),)),
    'emerald_arena': ArenaTheme(
        (.004, .02, .012, 1), 'assets/backgrounds/emerald_arena.png',
        ((.06, .8, .3), (.18, 1, .55), (.55, 1, .8), (.9, 1, .95)),
        (.03, .5, .2), .9,
        EffectStyle(((.15, 1, .5), (.6, 1, .85)), .18, (.65, 1, .6), (.4, 1, .75), ambient_rate=2.),
        decorative_speed_degrees=12., pulse_hz=.6,
        layers=(SpriteLayer('assets/effects/emerald_arena/energy.webp', columns=8, frames=8, fps=16),)),
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
