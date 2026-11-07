from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import shutil
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from services.custom_backgrounds import CustomBackgroundStore
from services.backgrounds import BackgroundTextures, BackgroundPreferences, DEFAULT_BACKGROUND
from services.team_store import TeamStore
from screens.router import AppRouter


@pytest.fixture(scope='module', autouse=True)
def graphics():
    EventLoop.ensure_window()


class Picker:
    selected = None
    def pick(self, kind, callback):
        assert kind == 'image'
        callback(self.selected, '')


def test_add_same_named_files_and_restart_preserve_portable_records(tmp_path, png_file):
    store = CustomBackgroundStore(tmp_path/'app')
    assert store.path.exists() and json.loads(store.path.read_text())['backgrounds'] == []
    a = store.add(png_file)
    other = tmp_path/'elsewhere'/png_file.name
    other.parent.mkdir()
    # Another valid image with the same name and different pixels.
    from kivy.graphics.texture import Texture
    texture = Texture.create(size=(4, 4))
    texture.blit_buffer(bytes([0, 150, 255, 255])*16, colorfmt='rgba', bufferfmt='ubyte')
    texture.save(str(other))
    b = store.add(other)
    assert a['id'] != b['id'] and a['name'] == b['name']
    assert store.owned_path(a).read_bytes() != store.owned_path(b).read_bytes()
    assert all(not Path(row['path']).is_absolute() and row['added_at'] for row in store.rows)
    assert CustomBackgroundStore(store.root).rows == [a, b]
    assert png_file.exists() and other.exists()


def test_delete_only_owned_image_preserves_other_files_and_handles_missing(tmp_path, png_file):
    store = CustomBackgroundStore(tmp_path/'app')
    a, b = store.add(png_file), store.add(png_file)
    original = png_file.read_bytes()
    store.delete(a['id'])
    assert not store.owned_path(a).exists() and store.owned_path(b).exists()
    assert png_file.read_bytes() == original
    with pytest.raises(ValueError):
        store.delete('stadium_night')
    store.owned_path(b).unlink()
    store.delete(b['id'])
    assert CustomBackgroundStore(store.root).rows == []


def test_path_traversal_and_team_media_cannot_be_deleted(tmp_path, png_file):
    store = CustomBackgroundStore(tmp_path/'app')
    key = uuid4().hex
    photo = tmp_path/f'{key}.png'
    shutil.copyfile(png_file, photo)
    malicious = dict(id=key, name='Not owned', path=f'../../{photo.name}', added_at='today')
    store.rows.append(malicious)
    with pytest.raises(ValueError):
        store.delete(key)
    assert photo.exists()
    store.path.write_text(json.dumps(dict(backgrounds=[malicious])))
    assert CustomBackgroundStore(store.root).rows == []


@pytest.mark.parametrize('suffix,content', [('.gif', b'GIF89a'), ('.png', b'broken'), ('.jpg', b'broken')])
def test_invalid_images_do_not_create_records(tmp_path, suffix, content):
    source = tmp_path/f'invalid{suffix}'
    source.write_bytes(content)
    store = CustomBackgroundStore(tmp_path/'app')
    with pytest.raises(ValueError, match='PNG'):
        store.add(source)
    assert store.rows == [] and source.read_bytes() == content
    with pytest.raises(ValueError, match='Android'):
        store.add('content://provider/image/42')


def test_corrupt_index_recovers_owned_files_and_keeps_backup(tmp_path, png_file):
    store = CustomBackgroundStore(tmp_path/'app')
    row = store.add(png_file)
    store.path.write_text('corrupt json')
    recovered = CustomBackgroundStore(store.root)
    assert recovered.warning and recovered.rows[0]['id'] == row['id']
    assert recovered.path.read_text() == 'corrupt json'
    recovered.add(png_file)
    assert len(list(store.root.glob('custom_backgrounds.corrupt_*.json'))) == 1
    assert len(CustomBackgroundStore(store.root).rows) == 2


def test_failed_atomic_index_write_rolls_back_only_new_copy(tmp_path, png_file, monkeypatch):
    store = CustomBackgroundStore(tmp_path/'app')
    previous = store.path.read_bytes()
    def fail(_):
        raise OSError('disk full')
    monkeypatch.setattr(store, '_save', fail)
    with pytest.raises(OSError):
        store.add(png_file)
    assert store.path.read_bytes() == previous and store.rows == []
    assert list(store.directory.iterdir()) == [] and png_file.exists()


def test_thumbnails_survive_restart_and_never_reload_original(tmp_path, png_file):
    store = CustomBackgroundStore(tmp_path/'app')
    row = store.add(png_file)
    texture = store.thumbnail(row, BackgroundTextures())
    assert texture and store.thumbnail_path(row).is_file()
    calls = []
    from services.media import load_texture
    def load(path):
        calls.append(Path(path))
        return load_texture(path)
    reopened = CustomBackgroundStore(store.root)
    assert reopened.thumbnail(reopened.get(row['id']), BackgroundTextures(loader=load))
    assert calls == [store.thumbnail_path(row)]


def test_legacy_migration_copies_once_and_deleted_images_do_not_reappear(tmp_path, png_file):
    old = tmp_path/'old'/'backgrounds'
    old.mkdir(parents=True)
    source = old/'old_photo.png'
    shutil.copyfile(png_file, source)
    store = CustomBackgroundStore(tmp_path/'app')
    mapping = store.migrate(old)
    assert len(mapping) == 1 and len(store.rows) == 1 and source.exists()
    reopened = CustomBackgroundStore(store.root)
    reopened.migrate(old)
    assert len(reopened.rows) == 1
    reopened.delete(reopened.rows[0]['id'])
    again = CustomBackgroundStore(store.root)
    again.migrate(old)
    assert again.rows == [] and source.exists()


@pytest.fixture
def form(tmp_path):
    root = AppRouter(TeamStore(tmp_path/'teams'), Picker(), background_data_dir=tmp_path/'app', size=(450, 800))
    root.store.save('Home')
    root.store.save('Away')
    root.go('setup')
    yield root.get_screen('setup')
    root.dispose()


def test_ui_add_select_restart_new_match_and_delete_confirmation(form, png_file):
    root = form.router
    teams_before = root.store.path.read_bytes()
    root.picker.selected = str(png_file)
    form.pick_background()
    a = form.selected_custom_id
    form.pick_background()
    b = form.selected_custom_id
    assert a != b and len(form.custom_tiles) == 2
    assert 'kaydedildi' in form.status.text
    form.select_custom_background(a)
    form.theme.text = 'electric_blue'
    form.select_background('stadium_rain')
    form.custom_tiles[a].dispatch('on_release')
    assert form.background_path and form.custom_tiles[a].selected
    reopened = AppRouter(TeamStore(root.store.root), Picker(), background_data_dir=root.background_data_dir)
    try:
        fresh = reopened.get_screen('setup')
        assert fresh.selected_custom_id == a and fresh.background_path == form.background_path
        reopened.go('setup')
        for i, team in enumerate(reopened.store.teams):
            fresh.choose_team(i, team['name'])
        fresh.start_match()
        assert reopened.match_view.settings.background == form.background_path
        assert reopened.match_view.background_texture is not None
    finally:
        reopened.dispose()
    form.request_delete_background(a)
    assert form.delete_dialog
    form.delete_cancel_button.dispatch('on_release')
    assert form.custom_store.get(a) and form.delete_dialog is None
    form.request_delete_background(a)
    form.delete_confirm_button.dispatch('on_release')
    assert a not in form.custom_tiles and b in form.custom_tiles
    assert form.background_choice.text == DEFAULT_BACKGROUND and not form.background_path
    assert form.theme.text == 'electric_blue'
    assert png_file.exists() and root.store.path.read_bytes() == teams_before
    assert CustomBackgroundStore(root.background_data_dir).get(b)


def test_legacy_selected_background_migrates_to_app_data_without_modifying_old_files(tmp_path, png_file):
    old = tmp_path/'teams'
    prefs = BackgroundPreferences(old)
    prefs.root.mkdir()
    source = prefs.import_image(png_file)
    prefs.save('fire_arena', 'stadium_night', source, True)
    before = prefs.path.read_bytes()
    root = AppRouter(TeamStore(old), None, background_data_dir=tmp_path/'app')
    try:
        form = root.get_screen('setup')
        assert form.theme.text == 'fire_arena' and form.background_choice.text == 'stadium_night'
        assert form.selected_custom_id and Path(form.background_path).parent == tmp_path/'app'/'custom_backgrounds'
        assert Path(source).exists() and prefs.path.read_bytes() == before
    finally:
        root.dispose()


def test_many_cards_only_keep_visible_thumbnails_in_memory(form, png_file):
    for i in range(50):
        form.custom_store.add(png_file, name=f'Foto {i}')
    form.refresh_custom_gallery()
    for _ in range(4):
        Clock.tick()
    assert len(form.custom_tiles) == 50
    assert 1 <= sum(tile.preview.texture is not None for tile in form.custom_tiles.values()) <= 8
    form.custom_scroll.scroll_x = 1
    for _ in range(4):
        Clock.tick()
    assert sum(tile.preview.texture is not None for tile in form.custom_tiles.values()) <= 8
    assert form.custom_rows[0][1].preview.texture is None
    assert form.custom_rows[-1][1].preview.texture


def test_main_wires_app_user_data_dir_without_moving_team_data(tmp_path, monkeypatch):
    import main
    monkeypatch.setattr(main, 'TeamStore', lambda _: TeamStore(tmp_path/'teams'))
    monkeypatch.setattr(main, 'AudioManager', lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(main, 'create_file_picker', lambda *_: Picker())
    app = SimpleNamespace(user_data_dir=str(tmp_path/'app'), on_keyboard=lambda *_: None)
    root = main.SimomatchApp.build(app)
    try:
        assert root.get_screen('setup').custom_store.root == tmp_path/'app'
        assert (tmp_path/'app'/'custom_backgrounds.json').exists()
        assert root.store.root == tmp_path/'teams'
    finally:
        main.SimomatchApp.on_stop(app)
