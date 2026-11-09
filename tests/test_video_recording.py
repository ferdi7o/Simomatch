"""Recording orchestration with a deterministic native boundary, no Android imports."""
import configparser
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree
from zipfile import ZipFile
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from kivy.core.window import Window
from screens.router import AppRouter
from services.match_settings import MatchSettings
from services.team_store import TeamStore
from services.video_recording import RecordingPreference, VideoRecording, video_name
from test_android_audio_results import Scheduler


class Backend:
    def __init__(self):
        self.requests, self.starts, self.stops = [], [], []
        self.responses = {}
        self.callback = None
        self.cancelled = 0
    def request(self, token, name, callback):
        self.requests.append((token, name))
        self.responses[token] = {'state':'preparing'}
        self.callback = callback
    def status(self, token): return self.responses[token]
    def mark(self, state, message=''):
        self.responses[self.requests[-1][0]] = {'state':state, 'message':message}
    def start(self, token): self.starts.append(token)
    def stop(self, token): self.stops.append(token)
    def cancel_consent(self): self.cancelled += 1


@pytest.fixture
def recording():
    backend, clock, notices = Backend(), Scheduler(), []
    manager = VideoRecording('android', clock.schedule, notices.append, backend)
    settings = MatchSettings(dict(id='h',name='Ev'),dict(id='a',name='Deplasman'), record_video=True)
    yield manager, backend, clock, notices, settings
    manager.close()


def prepared(recording):
    manager, backend, clock, notices, settings = recording
    callbacks = []
    manager.prepare(settings, callbacks.append)
    assert callbacks == [] and manager.state == 'consent'
    backend.callback(True)
    assert manager.state == 'preparing' and callbacks == []
    backend.mark('prepared')
    clock.advance(clock.time+.05)
    assert callbacks == [True] and manager.state == 'prepared'
    return callbacks


def test_windows_never_imports_android_or_requests_consent(recording, monkeypatch):
    manager, backend, clock, notices, settings = recording
    monkeypatch.setitem(sys.modules, 'android', None)
    monkeypatch.setitem(sys.modules, 'jnius', None)
    manager.platform = 'win'
    result = []
    manager.prepare(settings, result.append)
    assert result == [False] and not backend.requests
    assert 'yalnızca Android' in notices[-1]


def test_decline_and_stale_consent_cannot_start_old_session(recording):
    manager, backend, clock, notices, settings = recording
    result = []
    manager.prepare(settings, result.append)
    old = backend.callback
    old(False)
    assert result == [False] and not manager.busy
    manager.prepare(settings, result.append)
    old(True)
    assert manager.state == 'consent'
    assert backend.requests[0][0] != backend.requests[1][0]
    assert backend.requests[0][1] != backend.requests[1][1]
    assert not backend.starts


def test_first_encoded_frame_ack_results_three_seconds_and_save_after_finalize(recording):
    manager, backend, clock, notices, settings = recording
    prepared(recording)
    result = []
    manager.start(result.append)
    clock.advance(.1)
    assert result == [] and manager.state == 'starting'
    backend.mark('recording')
    clock.advance(.2)
    assert result == [True]
    manager.results_visible()
    timer = manager.result_event
    manager.results_visible()
    assert manager.result_event is timer and timer.seconds == 3
    clock.advance(3.19)
    assert not backend.stops
    clock.advance(3.2)
    assert backend.stops and manager.state == 'stopping'
    assert not any('kaydedildi' in n for n in notices)
    backend.mark('saved')
    clock.advance(3.3)
    assert manager.state == 'saved' and 'sessiz' in notices[-1]


@pytest.mark.parametrize('verified',[False,True])
def test_save_message_requires_explicit_native_decoded_audio_verification(recording,verified):
    manager,backend,clock,notices,_ = recording
    prepared(recording)
    manager.start(lambda _:None)
    backend.mark('recording'); clock.advance(.1)
    manager.stop()
    backend.mark('saved')
    backend.responses[manager.token]['audio_verified'] = verified
    clock.advance(.2)
    assert ('oyun sesi doğrulandı' in notices[-1]) == verified
    assert ('sessiz' in notices[-1]) != verified


@pytest.mark.parametrize('stage', ['consent','preparing','prepared','starting','recording'])
def test_cancel_during_each_lifecycle_stage_releases_callbacks(recording, stage):
    manager, backend, clock, notices, settings = recording
    result = []
    manager.prepare(settings, result.append)
    if stage != 'consent': backend.callback(True)
    if stage in ('prepared','starting','recording'):
        backend.mark('prepared'); clock.advance(.1)
    if stage in ('starting','recording'): manager.start(result.append)
    if stage == 'recording': backend.mark('recording'); clock.advance(.2)
    manager.stop()
    if stage == 'consent': assert not manager.busy and backend.cancelled
    else:
        backend.mark('discarded')
        clock.advance(.4)
        assert not manager.busy and backend.stops
    manager.close()
    assert all(t.cancelled for t in clock.timers)


def test_failure_timeout_is_not_reported_as_saved_and_stale_timers_cannot_stop_new_match(recording):
    manager, backend, clock, notices, settings = recording
    prepared(recording)
    result = []
    manager.start(result.append)
    clock.advance(11)
    assert result == [False] and backend.stops and not any('kaydedildi' in n for n in notices)
    backend.mark('failed', 'Encoder hatası')
    clock.advance(11.1)
    manager.prepare(settings, lambda _:None)
    token = manager.token
    old_deadlines = [t for t in clock.timers if t.cancelled]
    for timer in old_deadlines:
        if timer.seconds >= 10: timer.callback(timer.seconds)
    assert manager.token == token and manager.state == 'consent'


def test_preference_backward_compatibility_atomic_persistence_and_unique_names(tmp_path):
    pref = RecordingPreference(tmp_path)
    assert not pref.enabled
    pref.save(True)
    assert RecordingPreference(tmp_path).enabled
    pref.save(False)
    assert not RecordingPreference(tmp_path).enabled
    pref.path.write_text('broken', encoding='utf8')
    assert not RecordingPreference(tmp_path).enabled
    pref.path.write_text('[]', encoding='utf8')
    assert not RecordingPreference(tmp_path).enabled
    a, b = video_name('Ev / ../', 'GS'), video_name('Ev / ../', 'GS')
    assert a != b and '/' not in a and a.endswith('.mp4')


@pytest.fixture
def root(tmp_path):
    EventLoop.ensure_window()
    router = AppRouter(TeamStore(tmp_path), SimpleNamespace(), size=(450,800))
    router.store.save('Home'); router.store.save('Away')
    clock, backend, notices = Scheduler(), Backend(), []
    router.video = VideoRecording('android', clock.schedule, notices.append, backend)
    router.go('setup')
    form = router.get_screen('setup')
    form.choose_team(0,'Home'); form.choose_team(1,'Away')
    yield router, form, clock, backend, notices
    router.dispose()


def test_disabled_recording_keeps_original_countdown_and_physics(root):
    router, form, clock, backend, notices = root
    form.start_match()
    assert router.current == 'match' and not backend.requests
    assert router.match_view.engine.state == 'countdown'
    assert router.match_view.recording is None


def test_consent_denial_opens_normal_match_and_pending_navigation_cancels(root):
    router, form, clock, backend, notices = root
    form.record_switch.active = True
    form.start_match()
    assert router.current == 'setup' and router._launch_pending
    form.start_match()  # Double-tap never requests two sessions.
    assert len(backend.requests) == 1
    backend.callback(False)
    assert router.current == 'match' and router.match_view.recording is None


def test_recorded_match_waits_for_first_frame_and_final_panel_stays_visible(root):
    router, form, clock, backend, notices = root
    form.record_switch.active = True
    form.start_match()
    backend.callback(True)
    assert router.current == 'setup'
    backend.mark('prepared'); clock.advance(.1)
    view = router.match_view
    view.clock_event.cancel()
    view._first_frame = False
    view.engine.countdown = .001
    before = [(d.x,d.y,d.vx,d.vy) for d in view.engine.disks]
    view.update(.02)
    assert view._capture_waiting and view.engine.state == 'countdown'
    view._start_capture()
    view.update(.2)
    assert before == [(d.x,d.y,d.vx,d.vy) for d in view.engine.disks]
    assert view.engine.elapsed == 0 and not any(e[1]=='start' for e in view.engine.events)
    backend.mark('recording'); clock.advance(.2)
    view.update(.02); view.update(.02)
    assert view.engine.state == 'playing' and any(e[1]=='start' for e in view.engine.events)
    view.engine.state = 'finished'
    view.announcements.reset()
    view.draw_scene()
    assert not router.video.results_seen
    view._result_flip()  # Actual Window flip boundary, not engine-end time.
    assert router.video.results_seen
    clock.advance(3.2)
    assert router.video.state == 'stopping'
    assert view.result_panel.opacity == 1
    backend.mark('saved'); clock.advance(3.3)
    assert view.result_panel.opacity == 1
    view.restart_match()
    assert router.current == 'match' and router._launch_pending
    assert len(backend.requests) == 2  # Fresh consent; no token reuse.
    backend.callback(True)
    backend.mark('prepared'); clock.advance(3.4)
    assert router.match_view is not view
    assert router.video.state == 'prepared'  # Old view.dispose cannot stop it.


def test_pending_launch_cancelled_on_back_and_pause_only_ignores_consent(root):
    router, form, clock, backend, notices = root
    form.record_switch.active = True
    form.start_match()
    callback = backend.callback
    router.pause_recording()
    assert router.video.state == 'consent'
    router.go('menu')
    callback(True)
    assert router.current == 'menu' and router.match_view is None
    assert not router._launch_pending


def test_large_render_delta_cannot_record_seconds_of_blank_countdown(root):
    router, form, clock, backend, notices = root
    form.record_switch.active = True
    form.start_match(); backend.callback(True)
    backend.mark('prepared'); clock.advance(.1)
    view = router.match_view
    view.clock_event.cancel(); view._first_frame = False
    view.update(10)
    assert view.engine.state == 'countdown' and view.engine.elapsed == 0
    assert 0 < view.engine.countdown < .03
    assert view._capture_waiting and not any(e[1]=='start' for e in view.engine.events)


def test_buildozer_manifest_and_java_sources_are_packaged_consistently():
    root = Path(__file__).resolve().parents[1]
    config = configparser.ConfigParser(interpolation=None)
    config.read(root/'buildozer.spec')
    app = config['app']
    assert app['android.api'] == '36' and app['android.archs'] == 'arm64-v8a'
    assert set(app['android.permissions'].split(', ')) == {'FOREGROUND_SERVICE','FOREGROUND_SERVICE_MEDIA_PROJECTION','RECORD_AUDIO'}
    with ZipFile(root/app['android.add_aars']) as aar:
        manifest = aar.read('AndroidManifest.xml')
        assert manifest == (root/'android_src/capture_manifest.xml').read_bytes()
        service = ElementTree.fromstring(manifest).find('application/service')
    ns = '{http://schemas.android.com/apk/res/android}'
    assert ElementTree.fromstring(manifest).find('uses-sdk').get(ns+'targetSdkVersion') == '36'
    assert service.get(ns+'foregroundServiceType') == 'mediaProjection'
    assert service.get(ns+'exported') == 'false'
    package = service.get(ns+'name')
    assert (root/'android_src'/Path(*package.split('.')).with_suffix('.java')).is_file()
    assert (root/app['android.add_src']).is_dir()
