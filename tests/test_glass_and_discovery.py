from configparser import ConfigParser
from dataclasses import replace
from pathlib import Path
import shutil
import pytest
from kivy.base import EventLoop
from screens.glass_button import GlassButton
from screens.match_screen import MatchScreen
from screens.router import AppRouter
from services.team_store import TeamStore
from services.match_settings import MatchSettings
from services.backgrounds import (discover_backgrounds, refresh_background_catalog, BACKGROUNDS,
                                  DEFAULT_BACKGROUND, BackgroundTextures)


@pytest.fixture(scope='module', autouse=True)
def graphics():
    EventLoop.ensure_window()


@pytest.fixture
def catalog():
    previous = dict(BACKGROUNDS)
    yield
    BACKGROUNDS.clear()
    BACKGROUNDS.update(previous)


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280), (1080, 1920)])
def test_glass_controls_keep_hitboxes_and_work_before_and_after_final(size):
    back = []
    view = MatchScreen(size=size, on_back=lambda: back.append(True))
    try:
        for button in (view.back_button, view.restart_button):
            assert isinstance(button, GlassButton)
            assert button.fill_color.a == pytest.approx(.065)
            assert button.edge_color.a == pytest.approx(.125)
            assert button.color[3] == pytest.approx(.4)
            assert button.background_color[3] == 0
            before = tuple(button.pos), tuple(button.size)
            button.state = 'down'
            assert button.fill_color.a > .065
            button.state = 'normal'
            assert (tuple(button.pos), tuple(button.size)) == before
        assert view.back_button.size == pytest.approx((size[0]*.5, size[1]*.045))
        assert view.back_button.center == pytest.approx((size[0]/2, size[1]*.035))
        assert view.restart_button.size == pytest.approx((size[0]*.65, size[1]*.065))
        assert view.restart_button.center == pytest.approx((size[0]/2, size[1]*.1))
        view.back_button.dispatch('on_release')
        assert back == [True]
        view.engine.state = 'finished'
        view.engine.final_elapsed = 4
        view.draw_scene()
        assert not view.restart_button.disabled and view.restart_button.opacity == 1
        view.back_button.dispatch('on_release')
        assert back == [True, True]
        view.restart_button.dispatch('on_release')
        assert view.engine.state == 'countdown' and view.engine.countdown == 3
        assert view.clock_event.is_triggered
    finally:
        view.dispose()


def test_new_image_is_discovered_once_with_stable_id_and_friendly_name(tmp_path, png_file):
    folder = tmp_path/'assets/backgrounds'
    folder.mkdir(parents=True)
    shutil.copyfile(png_file, folder/'gs_stad.png')
    shutil.copyfile(png_file, folder/'new_stad.png')
    shutil.copyfile(png_file, folder/'alpha.JPG')
    (folder/'bad.png').write_bytes(b'broken')
    (folder/'ignored.webp').write_bytes(png_file.read_bytes())
    (folder/'directory.png').mkdir()
    first, second = discover_backgrounds(tmp_path), discover_backgrounds(tmp_path)
    assert first == second
    new = [(key, item) for key, item in first.items() if key.startswith('asset_')]
    assert [item.title for _, item in new] == ['Alpha', 'New Stad']
    assert len({key for key, _ in new}) == 2
    assert sum(item.image == 'assets/backgrounds/gs_stad.png' for item in first.values()) == 1
    assert first['stadium_rain'].title == 'Rainy Stadium'
    assert first[DEFAULT_BACKGROUND].image == 'assets/background/backgraund1.png'


def test_known_filename_keeps_existing_key_and_not_duplicate(tmp_path, png_file):
    path = tmp_path/'assets/backgrounds/stadium_rain.png'
    path.parent.mkdir(parents=True)
    shutil.copyfile(png_file, path)
    result = discover_backgrounds(tmp_path)
    assert result['stadium_rain'].title == 'Rainy Stadium'
    assert sum(item.image == 'assets/backgrounds/stadium_rain.png' for item in result.values()) == 1


def test_auto_asset_enters_ready_gallery_and_saved_selection_survives_restart(tmp_path, png_file, catalog, monkeypatch):
    folder = tmp_path/'assets/backgrounds'
    folder.mkdir(parents=True)
    asset = folder/'new_stad.png'
    shutil.copyfile(png_file, asset)
    refresh_background_catalog(tmp_path)
    key = next(key for key, item in BACKGROUNDS.items() if item.title == 'New Stad')
    import screens.setup_screen as setup_ui
    import screens.match_screen as match_ui
    textures = BackgroundTextures(tmp_path)
    monkeypatch.setattr(setup_ui, 'TEXTURES', textures)
    monkeypatch.setattr(match_ui, 'TEXTURES', textures)
    root = AppRouter(TeamStore(tmp_path/'data'), None)
    try:
        form = root.get_screen('setup')
        assert key in form.background_tiles and key not in form.custom_tiles
        form.select_background(key)
        settings = MatchSettings({'id': 'a', 'name': 'A', 'logo': ''}, {'id': 'b', 'name': 'B', 'logo': ''}, background_id=key)
        view = MatchScreen(settings=settings)
        try:
            assert view.background_texture is textures.preset(key)
        finally:
            view.dispose()
        restored = setup_ui.SetupScreen(root)
        assert restored.background_choice.text == key
        before = asset.read_bytes()
        form.request_delete_background(key)
        assert form.delete_dialog is None and asset.read_bytes() == before
        with pytest.raises(ValueError):
            form.custom_store.delete(key)
        restored.on_pre_leave()
        asset.unlink()  # This test fixture only; simulate an updated APK.
        refresh_background_catalog(tmp_path)
        missing = setup_ui.SetupScreen(root)
        assert missing.background_choice.text == DEFAULT_BACKGROUND
        assert replace(settings).background_id == DEFAULT_BACKGROUND
        assert textures.preset(key) is None  # All fallback assets absent here.
        missing.on_pre_leave()
    finally:
        root.dispose()


def test_discovery_never_scans_user_library(tmp_path, png_file):
    path = tmp_path/'custom_backgrounds'/'my_photo.png'
    path.parent.mkdir()
    shutil.copyfile(png_file, path)
    before = path.read_bytes()
    assert not any(item.image.endswith('my_photo.png') for item in discover_backgrounds(tmp_path).values())
    assert path.read_bytes() == before


def test_background_folder_rename_preserves_existing_selection_ids(tmp_path, png_file):
    catalogs = []
    for layout in ('backgrounds', 'background'):
        root = tmp_path/layout
        path = root/'assets'/layout/'renamed_stadium.png'
        path.parent.mkdir(parents=True)
        shutil.copyfile(png_file, path)
        catalogs.append([(key, item) for key, item in discover_backgrounds(root).items()
                         if key.startswith('asset_')])
    assert len(catalogs[0]) == len(catalogs[1]) == 1
    assert catalogs[0][0][0] == catalogs[1][0][0]
    assert catalogs[1][0][1].image == 'assets/background/renamed_stadium.png'


def test_buildozer_includes_images_without_packaging_private_data():
    config = ConfigParser()
    config.read(Path(__file__).resolve().parents[1]/'buildozer.spec', encoding='utf-8')
    included = {ext.strip() for ext in config['app']['source.include_exts'].split(',')}
    assert {'png', 'jpg', 'jpeg', 'webp', 'wav', 'mp3'} <= included
    excluded = {name.strip() for name in config['app']['source.exclude_dirs'].split(',')}
    assert {'data', '.test_runtime', '.smoke_runtime', 'venv'} <= excluded
