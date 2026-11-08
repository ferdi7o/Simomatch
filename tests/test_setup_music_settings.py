"""Per-team metadata, shared preview/goal timing and edge-to-edge regressions."""
import json
from types import SimpleNamespace
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from screens.router import AppRouter
from services.team_store import TeamStore
from test_android_audio_results import music  # Injected seekable provider and virtual clock.


@pytest.fixture
def setup(music, tmp_path):
    EventLoop.ensure_window()
    manager, path, clock = music
    store = TeamStore(tmp_path/'teams')
    store.save('Home', music=path)
    store.save('Away', music=path)
    root = AppRouter(store, SimpleNamespace(), audio=manager, size=(450, 800))
    root.go('setup')
    form = root.get_screen('setup')
    form.choose_team(0, 'Home')
    form.choose_team(1, 'Away')
    yield form, manager, clock
    root.dispose()


def test_preview_and_goal_use_same_offset_duration_and_independent_fades(setup):
    form, manager, clock = setup
    form.music_starts[0].value = 13
    form.music_durations[0].value = 8
    form.music_starts[1].value = 5
    form.music_durations[1].value = 7
    form.test_music(0)
    voice = manager.preview_pool[0]
    assert form.music_buttons[0].text == 'DURDUR'
    assert voice.sound.seeks == [13]
    assert voice.timer.seconds == 8 and voice.fade_timer.seconds == 6.5
    clock.advance(6.5)
    assert voice.sound.volume == manager.music_volume
    clock.advance(7.25)
    assert voice.sound.volume == pytest.approx(manager.music_volume*.5, abs=.01)
    clock.advance(8)
    form.update_music_test()
    assert not voice.busy and form.music_buttons[0].text == 'TEST ET'
    form.test_music(0)
    form.start_match()
    assert not voice.busy and form.router.current == 'match'
    session = form.router.match_view.audio_session
    assert session.goal('Home') and session.goal('Away')
    home, away = session.music['Home'][0], session.music['Away'][0]
    assert home.sound.seeks == [13] and away.sound.seeks == [5]
    assert home.timer.seconds == 8 and away.timer.seconds == 7
    session.stop_team('Home')
    assert not home.busy and away.busy


def test_tests_toggle_switch_and_navigation_cancel_old_timers(setup):
    form, manager, clock = setup
    form.test_music(0)
    voice = manager.preview_pool[0]
    old_stop, old_fade = voice.timer, voice.fade_timer
    form.test_music(0)
    assert not voice.busy and old_stop.cancelled and old_fade.cancelled
    form.test_music(0)
    form.test_music(1)
    assert not voice.busy
    assert [b.text for b in form.music_buttons] == ['TEST ET', 'DURDUR']
    other = manager.preview_pool[0]
    form.router.go('menu')
    assert not other.busy and form._music_test_event is None
    old_stop.callback(5)
    assert not voice.busy


def test_persistence_team_switch_and_team_editor_preserve_duration(setup):
    form, manager, clock = setup
    store = form.router.store
    form.music_starts[0].value = 13
    form.music_durations[0].value = 8
    form.music_durations[1].value = 7
    form.router.go('menu')  # Flush pending changes even before debounce fires.
    restored = TeamStore(store.root)
    home, away = restored.teams
    assert home['goal_music_start_seconds'] == 13 and home['goal_music_duration_seconds'] == 8
    assert away['goal_music_start_seconds'] == 0 and away['goal_music_duration_seconds'] == 7
    form.router.go('setup')
    assert form.music_starts[0].value == 13 and form.music_durations[0].value == 8
    form.router.go('teams')
    editor = form.router.get_screen('teams')
    editor.edit(home['id'])
    editor.save()
    assert TeamStore(store.root).get(home['id'])['goal_music_duration_seconds'] == 8


def test_bounds_missing_file_and_metadata_do_not_stop_other_preview(setup, monkeypatch):
    form, manager, clock = setup
    form.music_starts[0].value = 13
    form.music_durations[0].value = 100
    assert form.music_durations[0].value == 27
    assert form.music_starts[0].value+form.music_durations[0].value <= 40
    form.test_music(0)
    voice = manager.preview_pool[0]
    form.configure_music(1, form.router.store.teams[1])
    assert voice.busy  # Metadata preparation never switches the preview player.
    monkeypatch.setattr(manager, 'music_length', lambda _:0.)
    form.configure_music(1, form.router.store.teams[1])
    assert form.music_buttons[1].disabled and form.music_starts[1].disabled
    assert voice.busy
    form.configure_music(0, None)
    assert form.music_buttons[0].disabled and not voice.busy
    form.test_music(0)
    assert 'MP3' in form.status.text


def test_invalid_saved_range_is_clamped_and_shared_with_real_goal(setup):
    form, manager, clock = setup
    store = form.router.store
    home = store.teams[0]
    store.set_music_settings(home['id'], 80, 50)
    form.configure_music(0, store.get(home['id']))
    assert form.music_starts[0].value == 0 and form.music_durations[0].value == 40
    form.start_match()
    assert store.get(home['id'])['goal_music_start_seconds'] == 0
    assert store.get(home['id'])['goal_music_duration_seconds'] == 40
    session = form.router.match_view.audio_session
    assert session.goal('Home')
    assert session.music['Home'][0].timer.seconds == 40


@pytest.mark.parametrize('size', [(320,640),(450,800),(720,1280),(1080,1920)])
def test_music_controls_fit_cards_and_safe_insets_keep_full_background(setup, size):
    form, manager, clock = setup
    root = form.router
    root.size = size
    root.set_safe_insets((0, 30, 0, 12))
    for _ in range(5): Clock.tick()
    assert form.bg.size == list(size) or tuple(form.bg.size) == size
    assert form.shell.padding[1] >= 30
    for card in form.team_cards:
        children = list(reversed(card.children))
        assert all(b.top <= a.y+.1 for a,b in zip(children,children[1:]))
    for widget in (*form.music_starts, *form.music_durations, *form.music_buttons):
        assert widget.width > 80 and widget.height >= 30
    assert form.start_button.y >= 12
    form.start_match()
    view = root.match_view
    for _ in range(3): Clock.tick()
    original = (view.center_arena, view.radius)
    root.set_safe_insets((0, 0, 0, 0))
    assert (view.center_arena, view.radius) == original
    assert tuple(view.background.size) == size


@pytest.mark.parametrize('bad', [0, -1, True, float('inf'), float('nan'), 'bad'])
def test_duration_validation_is_atomic_and_old_json_not_rewritten(tmp_path, bad):
    path = tmp_path/'teams.json'
    path.write_text(json.dumps({'version':1,'teams':[dict(id='old', name='Old', logo='', music='')]}))
    before = path.read_bytes()
    store = TeamStore(tmp_path)
    assert store.get('old')['goal_music_duration_seconds'] == 5
    assert path.read_bytes() == before
    with pytest.raises(ValueError): store.set_music_settings('old', 13, bad)
    assert path.read_bytes() == before


@pytest.mark.parametrize('bad', [0, -1, float('inf'), float('nan')])
def test_invalid_playback_duration_stops_safely(music, bad):
    manager, path, clock = music
    assert not manager.preview_music(path, 0, bad)
    assert not manager.preview_pool[0].busy
