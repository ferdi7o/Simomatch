"""Independent visual settings, owned imports and GPU previews; no user data."""
from dataclasses import asdict
from pathlib import Path
import json
import shutil
import struct
import zlib
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from kivy.graphics.texture import Texture
import screens.setup_screen as setup_ui
import screens.match_screen as match_module
from screens.router import AppRouter
from screens.match_visuals import cover_coordinates
from services.backgrounds import (BACKGROUNDS, BackgroundTextures, BackgroundPreferences,
                                  DEFAULT_BACKGROUND, FALLBACK_COLOR)
from services.match_settings import MatchSettings
from services.team_store import TeamStore


class Picker:
    selected = None
    def pick(self, kind, callback):
        assert kind == 'image'
        callback(self.selected, '')


@pytest.fixture
def fixture(tmp_path, png_file, monkeypatch):
    EventLoop.ensure_window()
    asset_root = tmp_path/'package'
    for item in BACKGROUNDS.values():
        path = asset_root/item.image
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(png_file, path)
    textures = BackgroundTextures(asset_root)
    monkeypatch.setattr(setup_ui, 'TEXTURES', textures)
    monkeypatch.setattr(match_module, 'TEXTURES', textures)
    root = AppRouter(TeamStore(tmp_path/'data'), Picker(), size=(450, 800))
    teams = [root.store.save('Ev'), root.store.save('Deplasman')]
    root.go('setup')
    form = root.get_screen('setup')
    for i, team in enumerate(teams):
        form.choose_team(i, team['name'])
    yield root, form, textures
    root.dispose()


@pytest.mark.parametrize('theme,background', [('fire_arena', 'stadium_night'),
                                            ('electric_blue', 'stadium_rain'),
                                            ('rainbow_neon', 'cosmic_stadium')])
def test_independent_combinations_reach_match_with_correct_layers(fixture, theme, background):
    root, form, textures = fixture
    before = root.store.path.read_bytes()
    form.theme_tiles[theme].dispatch('on_release')
    form.background_tiles[background].dispatch('on_release')
    assert form.theme.text == theme and form.background_choice.text == background
    form.start_match()
    for _ in range(4):
        Clock.tick()
    view = root.match_view
    assert view.settings.theme == theme and view.settings.background_id == background
    assert view.background.texture is textures.preset(background)
    assert view.engine.arena.radius == 400
    assert view.radius == 450*.37 and view.center_arena == (225, 392)
    children = list(view.canvas.children)
    assert children.index(view.disk_shapes[0].image) < children.index(view.net[0])
    assert children.index(view.net[0]) < children.index(view.posts[0])
    assert children.index(view.posts[0]) < children.index(view.header_logos[0].image)
    assert children.index(view.posts[0]) < children.index(view.score.canvas)
    assert root.store.path.read_bytes() == before


def test_preferences_restore_theme_and_background_separately(fixture):
    root, form, _ = fixture
    form.select_background('stadium_night')
    form.theme.text = 'electric_blue'
    assert form.background_choice.text == 'stadium_night'
    form.select_background('cosmic_stadium')
    assert form.theme.text == 'electric_blue'
    prefs = json.loads((root.store.root/'match_preferences.json').read_text(encoding='utf-8'))
    assert prefs['arena_theme'] == 'electric_blue' and prefs['background_id'] == 'cosmic_stadium'
    reopened = AppRouter(TeamStore(root.store.root), Picker())
    try:
        setup = reopened.get_screen('setup')
        assert setup.theme.text == 'electric_blue'
        assert setup.background_choice.text == 'cosmic_stadium'
        assert setup.background_tiles['cosmic_stadium'].selected
    finally:
        reopened.dispose()


def test_custom_is_copied_restored_and_preset_can_disable_without_deleting(fixture, png_file):
    root, form, _ = fixture
    form.select_background('retro_pitch')
    root.picker.selected = str(png_file)
    form.pick_background()
    custom = Path(form.background_path)
    assert custom != png_file and custom.read_bytes() == png_file.read_bytes()
    assert custom.parent == root.store.root/'custom_backgrounds'
    assert form.background_choice.text == 'retro_pitch'
    form.theme.text = 'fire_arena'
    assert form.background_path == str(custom)
    restored = setup_ui.SetupScreen(root)
    assert restored.background_path == str(custom)
    assert restored.theme.text == 'fire_arena' and restored.background_choice.text == 'retro_pitch'
    preferences = BackgroundPreferences(root.store.root)
    assert preferences.data['custom_background'].startswith('custom_backgrounds/')
    assert not Path(preferences.data['custom_background']).is_absolute()
    form.select_background('stadium_night')
    assert form.background_path == '' and form.custom_background_path == str(custom)
    assert custom.exists() and png_file.exists()
    assert form.background_tiles['stadium_night'].selected
    form.clear_background()
    assert form.background_choice.text == 'stadium_night'
    assert form.custom_background_path == '' and custom.exists()
    assert form.background_preview.texture is None


def test_missing_and_broken_custom_fall_back_without_changing_preset(fixture, tmp_path):
    root, form, _ = fixture
    form.select_background('stadium_rain')
    broken = tmp_path/'bad.png'
    broken.write_bytes(b'invalid')
    root.picker.selected = str(broken)
    form.pick_background()
    assert not form.background_path and 'okunamadı' in form.status.text
    form.background_path = str(tmp_path/'missing.png')
    form.start_match()
    assert root.current == 'match'
    assert root.match_view.settings.background_id == 'stadium_rain'
    assert root.match_view.background_texture is not None


def test_missing_presets_use_default_then_dark_fallback(tmp_path, png_file, monkeypatch):
    EventLoop.ensure_window()
    default = tmp_path/BACKGROUNDS[DEFAULT_BACKGROUND].image
    default.parent.mkdir(parents=True)
    shutil.copyfile(png_file, default)
    textures = BackgroundTextures(tmp_path)
    assert textures.preset('stadium_rain') is textures.preset(DEFAULT_BACKGROUND)
    missing = BackgroundTextures(tmp_path/'empty')
    monkeypatch.setattr(match_module, 'TEXTURES', missing)
    settings = MatchSettings({'id': 'a', 'name': 'A', 'logo': ''},
                             {'id': 'b', 'name': 'B', 'logo': ''},
                             theme='fire_arena', background_id='stadium_rain')
    view = match_module.MatchScreen(settings=settings)
    try:
        assert view.background_texture is None
        assert view.background_color.rgba == pytest.approx(FALLBACK_COLOR)
    finally:
        view.dispose()


@pytest.mark.parametrize('raw', ['broken json', '[]', '{"arena_theme":[],"background_id":{},"custom_background":42}'])
def test_corrupt_preferences_are_safe(tmp_path, raw):
    (tmp_path/'match_preferences.json').write_text(raw, encoding='utf-8')
    root = AppRouter(TeamStore(tmp_path), None)
    try:
        form = root.get_screen('setup')
        assert form.theme.text == 'neon_purple' and form.background_choice.text == DEFAULT_BACKGROUND
    finally:
        root.dispose()


def test_legacy_settings_and_external_path_compatibility(fixture, png_file):
    _, form, _ = fixture
    old = asdict(MatchSettings({'id': 'a', 'name': 'A', 'logo': ''},
                              {'id': 'b', 'name': 'B', 'logo': ''}, background=str(png_file)))
    old.pop('background_id')
    settings = MatchSettings(**old)
    assert settings.background_id == ''
    view = match_module.MatchScreen(settings=settings)
    try:
        assert view.background_texture is not None
    finally:
        view.dispose()
    prefs = BackgroundPreferences(form.router.store.root)
    prefs.data['custom_background'] = '../not-owned.png'
    assert prefs.custom_path() == ''


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280), (1080, 1920), (360, 800)])
def test_portrait_cover_and_gallery_layout(fixture, size):
    root, form, _ = fixture
    root.size = size
    for _ in range(4):
        Clock.tick()
    texture = Texture.create(size=(1080, 1920))
    uv = cover_coordinates(texture, size)
    u, v = abs(uv[2]-uv[0]), abs(uv[7]-uv[1])
    assert u*1080/(v*1920) == pytest.approx(size[0]/size[1])
    assert max(u, v) == pytest.approx(1)
    assert (uv[0]+uv[2])/2 == pytest.approx(.5)
    assert (uv[1]+uv[7])/2 == pytest.approx(.5)
    order = list(reversed(form.content.children))
    assert order.index(form.background_scroll) > order.index(form.theme_scroll)
    assert order.index(form.custom_background_card) > order.index(form.background_scroll)
    assert form.background_scroll.do_scroll_x and not form.background_scroll.do_scroll_y
    assert sum(t.selected for t in form.background_tiles.values()) == 1
    assert form.start_button.y >= 16 and form.start_button.top < form.scroll.y
    assert all(tile.preview.fit_mode == 'contain' for tile in form.background_tiles.values())


def test_thumbnail_size_cache_and_no_reload_during_render(tmp_path):
    EventLoop.ensure_window()
    def chunk(kind, data):
        return struct.pack('!I', len(data))+kind+data+struct.pack('!I', zlib.crc32(kind+data)&0xffffffff)
    path = tmp_path/'portrait.png'
    data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!2I5B', 1080, 1920, 8, 6, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress((b'\0'+bytes([80, 120, 240, 255])*1080)*1920))+chunk(b'IEND', b'')
    path.write_bytes(data)
    calls = []
    from services.media import load_texture
    def loader(path):
        calls.append(path)
        return load_texture(path)
    textures = BackgroundTextures(loader=loader)
    thumbnail = textures.thumbnail(path)
    assert thumbnail.size == (144, 256)
    assert textures.thumbnail(path) is thumbnail
    assert len(calls) == 1
    full = textures.texture(path)
    assert textures.texture(path) is full and full.size == (1080, 1920)
    assert len(calls) == 2
    assert len(textures.full) <= 2 and len(textures.previews) <= 8


def test_theme_changes_and_match_render_do_not_reload_backgrounds(fixture):
    root, form, textures = fixture
    calls = []
    original = textures.loader
    def tracked(path):
        calls.append(path)
        return original(path)
    textures.loader = tracked
    for theme in ('fire_arena', 'electric_blue', 'rainbow_neon'):
        form.theme.text = theme
    assert not calls
    form.select_background('stadium_night')
    form.start_match()
    view = root.match_view
    loaded = len(calls)
    assert loaded > 0
    for _ in range(30):
        view.update(1/60)
    assert len(calls) == loaded


def test_custom_copy_still_works_when_source_disappears(fixture, png_file):
    root, form, _ = fixture
    root.picker.selected = str(png_file)
    form.pick_background()
    owned = Path(form.background_path)
    # Remove only this test fixture source, never the user's original media.
    png_file.unlink()
    form.start_match()
    assert owned.exists() and root.match_view.background_texture is not None
    assert root.match_view.settings.background == str(owned)
