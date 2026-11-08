"""Independent background catalog, bounded textures and owned preferences.

TeamStore/arena theme data is never written here. Android picker staging paths
are copied into private storage, and only relative owned paths are persisted.
"""
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
import json
import shutil
import hashlib
from services.image_format import image_format
from services.media import load_texture

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKGROUND = 'neon_stadium'
FALLBACK_COLOR = (.016, .012, .032, 1)


@dataclass(frozen=True)
class Background:
    title: str
    image: str


LEGACY_BACKGROUNDS = {
    'neon_stadium': Background('Neon Stadium', 'assets/background/backgraund1.png'),
    'stadium_night': Background('Stadium Night', 'assets/background/stadium_night.png'),
    'stadium_rain': Background('Rainy Stadium', 'assets/background/stadium_rain.png'),
    'retro_pitch': Background('Classic Football', 'assets/background/retro_pitch.png'),
    'cosmic_stadium': Background('Cosmic Arena', 'assets/background/cosmic_stadium.png'),
    "gs_stad": Background("GS Stad ", "assets/background/gs_stad.png"),
    'besiktas_stad': Background(
        'Beşiktaş Stadı',
        'assets/background/besiktas_stad.png'
    ),
    'fenerbahce_stad': Background(
        'Fenerbahçe Stadı',
        'assets/background/fenerbahce_stad.png'
    ),
    'trabzonspor_stad': Background(
        'Trabzonspor Stadı',
        'assets/background/trabzonspor_stad.png'
    ),
    'corum_fk_stad': Background(
        'Çorum FK Stadı',
        'assets/background/corum_fk_stad.png'
    ),
    'kasimpasa_stad': Background(
        'Kasımpaşa Stadı',
        'assets/background/kasimpasa_stad.png'
    ),
    'goztepe_stad': Background(
        'Göztepe Stadı',
        'assets/background/goztepe_stad.png'
    ),
    'konyaspor_stad': Background(
        'Konyaspor Stadı',
        'assets/background/konyaspor_stad.png'
    ),
}
BACKGROUNDS = dict(LEGACY_BACKGROUNDS)


def discover_backgrounds(root=ROOT, validator=load_texture):
    """Read-only scan: stable IDs, deterministic order and legacy-key support."""
    root = Path(root).resolve()
    result = dict(LEGACY_BACKGROUNDS)
    directory = root/'assets/background'
    if not directory.is_dir():
        directory = root/'assets/backgrounds'  # Older packaged-resource layout.
    try:
        if not directory.resolve().is_relative_to(root):
            return result
        paths = sorted(directory.iterdir(), key=lambda p: (p.name.casefold(), p.name))
    except OSError:
        return result
    seen = {(root/item.image).resolve() for item in result.values()}
    known_names = {Path(item.image).name.casefold(): key for key, item in result.items()}
    for path in paths:
        try:
            resolved = path.resolve()
            if (not path.is_file() or not resolved.is_relative_to(directory.resolve())
                    or path.suffix.lower() not in ('.png', '.jpg', '.jpeg') or resolved in seen):
                continue
            if path.stat().st_size > 32*1024*1024 or image_format(path) not in ('png', 'jpeg') or validator(path) is None:
                continue
            relative = path.relative_to(root).as_posix()
            known = known_names.get(path.name.casefold())
            # Folder rename must not invalidate previously saved asset IDs.
            canonical = relative.replace('assets/background/', 'assets/backgrounds/', 1)
            key = known or 'asset_'+hashlib.sha256(canonical.encode('utf-8')).hexdigest()
            title = LEGACY_BACKGROUNDS[known].title if known else path.stem.replace('_', ' ').replace('-', ' ').title()
            result[key] = Background(title, relative)
            seen.add(resolved)
        except (OSError, ValueError):
            continue
    return result


def refresh_background_catalog(root=ROOT, validator=load_texture):
    found = discover_backgrounds(root, validator)
    BACKGROUNDS.clear()
    BACKGROUNDS.update(found)
    return BACKGROUNDS


class BackgroundTextures:
    """At most two full images and eight <=144x256 aspect-fit thumbnails."""
    def __init__(self, root=ROOT, loader=load_texture):
        self.root, self.loader = Path(root), loader
        self.full, self.previews = OrderedDict(), OrderedDict()
        self.preview_fallbacks = {}

    @staticmethod
    def _key(path):
        try:
            path = Path(path).resolve()
            stat = path.stat()
            return str(path), stat.st_mtime_ns, stat.st_size
        except (OSError, ValueError):
            return str(path), 0, 0

    def forget(self, path):
        resolved = str(Path(path).resolve())
        for cache in (self.full, self.previews):
            for key in list(cache):
                if key[0] == resolved:
                    cache.pop(key)

    def texture(self, path):
        if not path:
            return None
        key = self._key(path)
        if key not in self.full:
            texture = self.loader(path)
            if texture is None:
                return None
            self.full[key] = texture
        self.full.move_to_end(key)
        while len(self.full) > 2:
            self.full.popitem(last=False)
        return self.full[key]

    def candidates(self, key):
        key = key if key in BACKGROUNDS else DEFAULT_BACKGROUND
        return tuple(dict.fromkeys((self.root/BACKGROUNDS[key].image,
                                    self.root/'assets/background'/Path(BACKGROUNDS[key].image).name,
                                    self.root/'assets/backgrounds'/Path(BACKGROUNDS[key].image).name,
                                    self.root/'assets/backgraund'/Path(BACKGROUNDS[key].image).name,
                                    self.root/BACKGROUNDS[DEFAULT_BACKGROUND].image,
                                    self.root/'assets/background1.png',
                                    self.root/'assets/backgraund1.png',
                                    self.root/'assets/background/backgraund1.png',
                                    self.root/'assets/backgraund/backgraund1.png')))

    def preset(self, key):
        for path in self.candidates(key):
            texture = self.texture(path)
            if texture is not None:
                return texture
        return None

    def thumbnail(self, path):
        if not path:
            return None
        key = self._key(path)
        if key not in self.previews:
            # Do not retain a full-size texture for every gallery item.
            source = self.loader(path)
            texture = None
            if source is not None:
                from kivy.graphics import Fbo, Color, Rectangle
                scale = min(1., 144/source.width, 256/source.height)
                size = (max(1, round(source.width*scale)), max(1, round(source.height*scale)))
                fbo = Fbo(size=size)
                with fbo:
                    Color(1, 1, 1, 1)
                    Rectangle(texture=source, size=size)
                fbo.draw()
                texture = fbo.texture
            self.previews[key] = texture
        self.previews.move_to_end(key)
        while len(self.previews) > 8:
            self.previews.popitem(last=False)
        return self.previews[key]

    def preview(self, key):
        key = key if key in BACKGROUNDS else DEFAULT_BACKGROUND
        for path in self.candidates(key):
            texture = self.thumbnail(path)
            if texture is not None:
                self.preview_fallbacks[key] = path.name != Path(BACKGROUNDS[key].image).name
                return texture
        self.preview_fallbacks[key] = True
        return None


TEXTURES = BackgroundTextures()


class BackgroundPreferences:
    def __init__(self, data_dir):
        self.root = Path(data_dir).resolve() if data_dir else None
        self.path = self.root/'match_preferences.json' if self.root else None
        self.warning = ''
        try:
            data = json.loads(self.path.read_text(encoding='utf-8')) if self.path else {}
            self.data = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.data = {}
        for key in ('arena_theme', 'background_id', 'custom_background', 'custom_background_id'):
            if key in self.data and not isinstance(self.data[key], str):
                self.data.pop(key)

    def custom_path(self):
        relative = self.data.get('custom_background', '')
        if not self.root or not isinstance(relative, str) or not relative:
            return ''
        try:
            path = (self.root/relative).resolve()
        except (OSError, ValueError):
            return ''
        # Never restore external/desktop paths or unrelated team media.
        if not any(path.is_relative_to(self.root/folder) for folder in ('backgrounds', 'custom_backgrounds')):
            return ''
        return str(path) if path.is_file() else ''

    def save(self, theme, background_id, custom_path='', use_custom=False, custom_id=''):
        from services.arena_themes import THEMES
        if theme not in THEMES or background_id not in BACKGROUNDS:
            return False
        relative = ''
        if self.root and custom_path:
            path = Path(custom_path).resolve()
            if any(path.is_relative_to(self.root/folder) for folder in ('backgrounds', 'custom_backgrounds')):
                relative = path.relative_to(self.root).as_posix()
        self.data.update(arena_theme=theme, background_id=background_id,
                         custom_background=relative, use_custom=bool(use_custom and relative),
                         custom_background_id=custom_id)
        if not self.path:
            return True
        temporary = self.root/f'.background_preferences_{uuid4().hex}.tmp'
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
            self.warning = ''
            return True
        except OSError:
            self.warning = 'Arka plan tercihi kaydedilemedi; bu maçta kullanılabilir.'
            return False
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def import_image(self, source):
        source = Path(source)
        if not self.root:
            raise ValueError('Kalıcı uygulama veri dizini bulunamadı.')
        if (source.suffix.lower() not in ('.png', '.jpg', '.jpeg')
                or image_format(source) not in ('png', 'jpeg') or load_texture(source) is None):
            raise ValueError('Arka plan okunamadı. PNG/JPG görsel seçin.')
        directory = self.root/'backgrounds'
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory/f'custom_{uuid4().hex}{source.suffix.lower()}'
        try:
            shutil.copyfile(source, destination)
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        return str(destination)
