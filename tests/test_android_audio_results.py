import json
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from kivy.metrics import Metrics, dp
from engine.cards import CardEvent
from services.android_display import ImmersiveDisplay
from services.audio import AudioManager, Voice
from services.music_backend import AndroidMusic
from services.team_store import TeamStore
from screens.result_panel import ResultPanel, CardRow
from screens.router import AppRouter


class Timer:
    def __init__(self, callback, seconds, due=0):
        self.callback, self.seconds, self.due, self.cancelled = callback, seconds, due, False
    def cancel(self): self.cancelled = True


class Scheduler:
    def __init__(self): self.time, self.timers = 0., []
    def schedule(self, callback, seconds):
        timer = Timer(callback, seconds, self.time+seconds)
        self.timers.append(timer)
        return timer
    def advance(self, target):
        while True:
            due = [t for t in self.timers if not t.cancelled and t.due <= target]
            if not due: break
            timer = min(due, key=lambda t:t.due)
            timer.cancelled = True
            self.time = timer.due
            timer.callback(timer.seconds)
        self.time = target


class SeekSound:
    supports_seek = True
    def __init__(self, path):
        self.path, self.length, self.state = path, 40., 'stop'
        self.volume, self.loop, self.position = .28, False, 0.
        self.seeks, self.stops = [], 0
    def play(self): self.state = 'play'
    def stop(self): self.state = 'stop'; self.stops += 1
    def unload(self): self.stop()
    def seek(self, position): self.seeks.append(position); self.position = position
    def get_pos(self): return self.position


@pytest.fixture
def music(tmp_path):
    path = tmp_path/'song.mp3'
    path.write_bytes(b'ID3\x04\0\0')
    scheduler = Scheduler()
    manager = AudioManager(tmp_path, loader=SeekSound, schedule=scheduler.schedule, now=lambda:scheduler.time)
    yield manager, path, scheduler
    manager.close()


def test_music_offset_shared_by_preview_goal_and_independent_team_fades(music):
    manager, path, clock = music
    assert manager.preview_music(path, 13)
    preview = manager.preview_pool[0]
    assert preview.sound.seeks == [13] and preview.seek_status == 'verified'
    assert preview.timer.seconds == 5 and preview.fade_timer.seconds == 3.5
    session = manager.create_session([dict(name='Home', music=str(path), goal_music_start_seconds=13),
                                      dict(name='Away', music=str(path), goal_music_start_seconds=20)],
                                     SimpleNamespace(asset_path=lambda p:Path(p)))
    assert session.goal('Home') and session.goal('Away')
    home, away = session.music['Home'][0], session.music['Away'][0]
    assert home.sound.seeks == [13] and away.sound.seeks == [20]
    clock.advance(3.5)
    assert preview.sound.volume == manager.music_volume
    clock.advance(4.25)
    assert home.sound.volume == pytest.approx(manager.music_volume*.5, abs=.01)
    session.stop_team('Home')
    assert not home.busy and away.busy
    clock.advance(5)
    assert not preview.busy and not away.busy


def test_repeated_preview_stops_old_test_and_old_seek_callbacks_cannot_interrupt(music):
    manager, path, clock = music
    manager.preview_music(path, 13)
    voice = manager.preview_pool[0]
    old_stop, old_fade = voice.timer, voice.fade_timer
    manager.preview_music(path, 15)
    assert old_stop.cancelled and old_fade.cancelled
    old_stop.callback(5)
    old_fade.callback(3.5)
    assert voice.busy and voice.sound.seeks == [13, 15]
    assert voice.sound.volume == manager.music_volume


def test_async_seek_is_muted_until_verified_and_times_out_safely(music, caplog):
    manager, path, clock = music
    manager.prepare_preview(path)
    voice = manager.preview_pool[0]
    voice.sound.seek = lambda _:None
    assert manager.preview_music(path, 13)
    assert voice.seek_status == 'pending' and voice.sound.volume == 0 and voice.timer is None
    assert voice.busy
    clock.advance(1.6)
    assert not voice.busy and voice.seek_status == 'failed'
    assert 'Seek position' in manager.diagnostics['music']
    assert 'Seek position' in caplog.text
    voice.sound.position = 0
    manager.preview_music(path, 13)
    old_seek = voice.seek_timer
    voice.sound.seek = lambda position:setattr(voice.sound, 'position', position)
    manager.preview_music(path, 14)
    old_seek.callback(.03)
    assert voice.seek_status == 'verified' and voice.busy


def test_seek_rejects_noop_provider_and_out_of_bounds_start(music, caplog):
    manager, path, _ = music
    manager.prepare_preview(path)
    voice = manager.preview_pool[0]
    voice.sound.supports_seek = False
    assert not manager.preview_music(path, 13)
    assert not voice.busy and 'cannot perform' in caplog.text
    voice.sound.supports_seek = True
    assert not manager.preview_music(path, 36)
    assert not manager.preview_music(path, float('nan'))
    assert manager.preview_music(path, 0)


def test_late_android_seek_waits_for_completion_and_occupies_its_own_voice(music):
    manager, path, clock = music
    class PausedSound(SeekSound):
        seeks_paused = True
        seek_ready = False
        def seek(self, position):
            self.position = position
            self.state = 'stop'
        def resume_after_seek(self): self.state = 'play'
    manager.music_loader = PausedSound
    session = manager.create_session([dict(name='Home', music=str(path), goal_music_start_seconds=13)],
                                     SimpleNamespace(asset_path=lambda p:Path(p)))
    assert session.goal('Home') and session.goal('Home')
    a, b = session.music['Home']
    assert a.seek_status == b.seek_status == 'pending' and a.busy and b.busy
    clock.advance(.8)
    assert a.timer is None and a.sound.volume == 0
    a.sound.seek_ready = b.sound.seek_ready = True
    clock.advance(.85)
    assert a.seek_status == b.seek_status == 'verified'
    assert a.timer.seconds == 5 and a.fade_timer.seconds == 3.5
    clock.advance(5.9)
    assert not a.busy and not b.busy


def test_old_team_json_default_and_new_offset_persist_without_eager_rewrite(tmp_path):
    path = tmp_path/'teams.json'
    path.write_text(json.dumps(dict(version=1, teams=[dict(id='old', name='Legacy', logo='', music='')])))
    original = path.read_bytes()
    store = TeamStore(tmp_path)
    assert store.get('old')['goal_music_start_seconds'] == 0
    assert path.read_bytes() == original
    music = tmp_path/'song.mp3'
    music.write_bytes(b'ID3\x04\0\0')
    team = store.save('New', music=music, goal_music_start_seconds=13)
    assert TeamStore(tmp_path).get(team['id'])['goal_music_start_seconds'] == 13
    store.save('Edited', team_id=team['id'], goal_music_start_seconds=22.5)
    assert TeamStore(tmp_path).get(team['id'])['goal_music_start_seconds'] == 22.5


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), 'bad', True])
def test_invalid_music_start_cannot_modify_team_json(tmp_path, value):
    store = TeamStore(tmp_path)
    store.save('Existing')
    original = store.path.read_bytes()
    with pytest.raises(ValueError): store.save('Invalid', goal_music_start_seconds=value)
    assert store.path.read_bytes() == original


def test_team_slider_duration_test_edit_and_cleanup(music, tmp_path):
    EventLoop.ensure_window()
    manager, path, _ = music
    picker = SimpleNamespace(pick=lambda kind, callback:callback(str(path), ''))
    root = AppRouter(TeamStore(tmp_path/'teams'), picker, audio=manager)
    try:
        root.go('teams')
        form = root.get_screen('teams')
        form.pick('music')
        assert form.music_start_slider.max == 35 and not form.music_start_slider.disabled
        form.music_start_slider.value = 13
        form.test_music_button.dispatch('on_release')
        assert manager.preview_pool[0].sound.seeks == [13]
        form.name_input.text = 'Music team'
        form.save()
        team = root.store.teams[0]
        assert team['goal_music_start_seconds'] == 13
        form.edit(team['id'])
        assert form.music_start_slider.value == 13
        form.music_start_slider.value = 19
        form.save()
        assert root.store.get(team['id'])['goal_music_start_seconds'] == 19
        root.back()
        assert not manager.preview_pool
    finally:
        root.dispose()


def test_android_media_player_seek_uses_integer_milliseconds(monkeypatch):
    calls = []
    player = SimpleNamespace(setDataSource=lambda _:None, prepare=lambda:None,
                             getDuration=lambda:40000, release=lambda:None,
                             setOnSeekCompleteListener=lambda _:None,
                             seekTo=lambda *args:calls.append(args))
    jnius = ModuleType('jnius')
    jnius.PythonJavaClass = object
    jnius.java_method = lambda signature:lambda method:method
    jnius.autoclass = lambda name:(lambda:player) if name == 'android.media.MediaPlayer' else SimpleNamespace(SDK_INT=35)
    monkeypatch.setitem(sys.modules, 'jnius', jnius)
    sound = AndroidMusic('/fake/music.mp3')
    sound.seek(13)
    assert calls == [(13000, 3)] and isinstance(calls[0][0], int)
    assert not sound.seek_ready
    sound.seek(14)
    assert calls == [(13000, 3)]
    sound.listener.onSeekComplete(player)
    assert calls[-1] == (14000, 3) and not sound.seek_ready
    sound.listener.onSeekComplete(player)
    assert sound.seek_ready
    sound.seek(15)
    sound.seek(16)
    def rejected(*args):
        sound.listener.owner = None  # A concurrent close detaches the listener.
        raise RuntimeError('native seek rejected')
    player.seekTo = rejected
    sound.listener.onSeekComplete(player)  # Must not escape a Java/UI callback.
    assert sound.seek_error == 'native seek rejected'


def test_windows_immersive_does_not_import_android_modules(monkeypatch):
    monkeypatch.setitem(sys.modules, 'android', None)
    monkeypatch.setitem(sys.modules, 'jnius', None)
    display = ImmersiveDisplay('win', None, lambda *_:None)
    display.start(); display.request(); display.apply(); display.close()
    assert not display.active


def test_immersive_lifecycle_binds_actual_kivy_focus_property():
    from kivy.core.window import Window
    clock = Scheduler()
    display = ImmersiveDisplay('android', Window, clock.schedule)
    display.start()
    assert display.active and display.pending
    display.close()
    assert display.pending.cancelled


def test_android_immersive_ui_thread_controller_cutout_and_cleanup(monkeypatch):
    calls, on_ui = [], [False]
    def ensure(call):
        assert on_ui[0]
        calls.append(call)
    cutout = SimpleNamespace(getSafeInsetLeft=lambda:0, getSafeInsetTop=lambda:72,
                             getSafeInsetRight=lambda:0, getSafeInsetBottom=lambda:0)
    decor = SimpleNamespace(getRootWindowInsets=lambda:SimpleNamespace(getDisplayCutout=lambda:cutout),
                            getWidth=lambda:1080, getHeight=lambda:1920)
    controller = SimpleNamespace(setSystemBarsBehavior=lambda x:ensure(('behavior', x)), hide=lambda x:ensure(('hide', x)))
    native = SimpleNamespace(getDecorView=lambda:decor, setDecorFitsSystemWindows=lambda x:ensure(('fits', x)),
                             getInsetsController=lambda:controller, setNavigationBarContrastEnforced=lambda _:None,
                             setStatusBarContrastEnforced=lambda _:None,
                             getAttributes=lambda:SimpleNamespace(),
                             setAttributes=lambda a:ensure(('cutout', a.layoutInDisplayCutoutMode)),
                             setStatusBarColor=lambda c:ensure(('status_color', c)),
                             setNavigationBarColor=lambda c:ensure(('navigation_color', c)),
                             findViewById=lambda _:SimpleNamespace(setPadding=lambda *x:ensure(('padding', x))))
    mapping = {'org.kivy.android.PythonActivity':SimpleNamespace(mActivity=SimpleNamespace(getWindow=lambda:native)),
               'android.os.Build$VERSION':SimpleNamespace(SDK_INT=35),
               'android.view.WindowInsets$Type':SimpleNamespace(systemBars=lambda:3),
               'android.R$id':SimpleNamespace(content=42)}
    jnius, android, runnable = ModuleType('jnius'), ModuleType('android'), ModuleType('android.runnable')
    jnius.autoclass = lambda name:mapping[name]
    def decorate(callback):
        def run():
            on_ui[0] = True
            try:callback()
            finally:on_ui[0] = False
        return run
    runnable.run_on_ui_thread = decorate
    for name, module in [('android', android), ('android.runnable', runnable), ('jnius', jnius)]:
        monkeypatch.setitem(sys.modules, name, module)
    clock = Scheduler()
    window = SimpleNamespace(bind=lambda **_:None, unbind=lambda **_:None, width=450, height=800)
    safe_insets = []
    def receive_safe(value):
        assert not on_ui[0]  # Kivy foreground changes must run on Clock, not Java's UI thread.
        safe_insets.append(value)
    display = ImmersiveDisplay('android', window, clock.schedule, receive_safe)
    display.start(); first = display.pending; display.focus(None, True)
    assert first.cancelled
    clock.advance(.2)
    assert ('hide', 3) in calls and ('behavior', 2) in calls and ('padding', (0,0,0,0)) in calls
    assert ('cutout', 3) in calls and ('fits', False) in calls
    assert ('status_color', 0) in calls and ('navigation_color', 0) in calls
    assert safe_insets == [(0, 30, 0, 0)]
    # Retry attachment only a bounded number of times; later focus requests
    # can start a fresh attempt without leaking Clock events after close.
    native.getInsetsController = lambda:None
    display.request()
    clock.advance(2)
    assert display.attach_attempts == 3
    native.getInsetsController = lambda:controller
    display.focus(None, True)
    clock.advance(2.2)
    assert display.diagnostics == 'WindowInsetsController'
    display.request(); pending = display.pending
    display.close(); pending.callback(.15)
    assert pending.cancelled and not display.active


def test_older_android_uses_available_p4a_immersive_helper(monkeypatch):
    calls = []
    native = SimpleNamespace(getDecorView=lambda:None, setNavigationBarContrastEnforced=lambda _:None,
                             setStatusBarContrastEnforced=lambda _:None,
                             setStatusBarColor=lambda _:None, setNavigationBarColor=lambda _:None)
    jnius = ModuleType('jnius')
    jnius.autoclass = lambda name:(SimpleNamespace(SDK_INT=27) if name == 'android.os.Build$VERSION'
                                   else SimpleNamespace(mActivity=SimpleNamespace(getWindow=lambda:native)))
    android, cutout = ModuleType('android'), ModuleType('android.display_cutout')
    cutout.set_immersive_mode = lambda *args:calls.append(args)
    monkeypatch.setitem(sys.modules, 'android', android)
    monkeypatch.setitem(sys.modules, 'android.display_cutout', cutout)
    monkeypatch.setitem(sys.modules, 'jnius', jnius)
    display = ImmersiveDisplay('android', None, None)
    display.active = True
    display._apply_android()
    assert calls == [(True, True, True)]


@pytest.mark.parametrize('density', [1, 2, 3])
def test_card_minute_rows_fit_real_textures_and_scroll_at_android_density(density):
    EventLoop.ensure_window()
    previous = Metrics.density
    Metrics.density = density
    panel = ResultPanel(('Home', 'Away'), (None, None), size=(320, 480))
    try:
        cards = [CardEvent('yellow_card', 'Home', i) for i in (5, 24, 38, 62, 77)]
        cards += [CardEvent('red_card', 'Away', 88)]
        panel.set_result({'Home':1, 'Away':0}, [('Home',13)], cards)
        panel.set_visible(True)
        for _ in range(5): Clock.tick()
        assert panel.card_minutes['Home']['yellow_card'] == [5,24,38,62,77]
        assert panel.card_rows[1][0].text.text == "88' KIRMIZI"
        for rows in panel.card_rows:
            for row in rows:
                row.set_font_size(dp(22))  # Force wrapping at high density.
        for _ in range(5): Clock.tick()
        for rows in panel.card_rows:
            for row in rows:
                assert row.text.text_size[1] is None
                assert row.height >= row.text.texture_size[1]
                assert row.text.y == row.y and row.text.top <= row.top+.1
        if density > 1:
            assert panel.goal_contents[0].height > panel.goal_scrolls[0].height
    finally:
        Metrics.density = previous
