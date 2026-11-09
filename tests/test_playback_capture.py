"""Host tests of permission/session guards and independent exported-PCM inspection.

These are not device tests of Android codecs or SDL capture eligibility.
"""
from array import array
from io import BytesIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
import json
import sys
from xml.etree import ElementTree
from zipfile import ZipFile
import pytest
from kivy.base import EventLoop
from services.video_recording import AndroidCapture
from tools.check_recorded_audio import pcm_stats, check


ROOT = Path(__file__).resolve().parents[1]


def test_pcm_analysis_rejects_silence_and_handles_unaligned_chunks():
    assert not pcm_stats([bytes(200)])['audible']
    assert not pcm_stats([])['audible']
    pcm = array('h',[0,0,0,1000,-1000,0]).tobytes()
    stats = pcm_stats([pcm[:3],pcm[3:7],pcm[7:]],rate=10)
    assert stats['audible'] and stats['nonzero_samples'] == 2
    assert stats['peak'] == 1000 and stats['first_audible_second'] == .3
    with pytest.raises(ValueError,match='Truncated'): pcm_stats([b'\x00'])


@pytest.mark.parametrize('audible',[False,True])
def test_mp4_inspector_decodes_samples_not_just_track_metadata(monkeypatch,audible):
    import tools.check_recorded_audio as tool
    monkeypatch.setattr(tool.subprocess,'check_output',lambda *a,**k:json.dumps({'streams':[
        {'codec_type':'video','codec_name':'h264'}, {'codec_type':'audio','codec_name':'aac'}]}))
    pcm = array('h',[1200,-1200]*100 if audible else [0]*200).tobytes()
    class Process:
        def __init__(self,*a,**k): self.stdout = BytesIO(pcm)
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def wait(self): return 0
    monkeypatch.setattr(tool.subprocess,'Popen',Process)
    if audible:
        report = check('pulled.mp4')
        assert report['audible'] and report['audio_codec'] == 'aac'
    else:
        with pytest.raises(ValueError,match='empty/silent'): check('pulled.mp4')


def test_mp4_without_audio_cannot_pass_verification(monkeypatch):
    import tools.check_recorded_audio as tool
    monkeypatch.setattr(tool.subprocess,'check_output',lambda *a,**k:'{"streams":[{"codec_type":"video"}]}')
    with pytest.raises(ValueError,match='both video and AAC'): check('silent.mp4')


@pytest.fixture
def adapter(monkeypatch):
    EventLoop.ensure_window()
    import kivy.clock
    monkeypatch.setattr(kivy.clock,'Clock',SimpleNamespace(schedule_once=lambda f,t:f(t)))
    android = ModuleType('android')
    permissions = ModuleType('android.permissions')
    runnable = ModuleType('android.runnable')
    callbacks, launches, bindings = [], [], []
    permissions.Permission = SimpleNamespace(RECORD_AUDIO='android.permission.RECORD_AUDIO')
    permissions.check_permission = lambda permission:False
    permissions.request_permissions = lambda values,callback:callbacks.append(callback)
    android.activity = SimpleNamespace(bind=lambda **kw:bindings.append(kw),unbind=lambda **kw:None)
    runnable.run_on_ui_thread = lambda callback:callback
    for name,module in [('android',android),('android.permissions',permissions),('android.runnable',runnable)]:
        monkeypatch.setitem(sys.modules,name,module)
    backend = AndroidCapture.__new__(AndroidCapture)
    backend.pending = backend.permission_callback = backend.audio_dialog = None
    backend.activity = SimpleNamespace(startActivityForResult=lambda intent,code:launches.append((intent,code)))
    backend.java = SimpleNamespace(consentIntent=lambda activity:'fresh-consent')
    yield backend,callbacks,launches,permissions
    backend.cancel_consent()


@pytest.mark.parametrize('granted',[False,True])
def test_audio_permission_grant_or_denial_both_continue_to_fresh_video_consent(adapter,granted):
    backend,callbacks,launches,permissions = adapter
    backend.request('session','match.mp4',lambda granted:None)
    assert backend.audio_dialog and not launches
    buttons = backend.audio_dialog.content.children[0]
    next(button for button in buttons.children if button.text == 'DEVAM').dispatch('on_release')
    assert callbacks and not launches
    callbacks[0]([permissions.Permission.RECORD_AUDIO],[granted])
    assert len(launches) == 1


def test_cancelled_permission_callback_cannot_open_capture_for_a_new_session(adapter):
    backend,callbacks,launches,_ = adapter
    backend.request('old','old.mp4',lambda granted:None)
    buttons = backend.audio_dialog.content.children[0]
    next(button for button in buttons.children if button.text == 'DEVAM').dispatch('on_release')
    backend.cancel_consent()
    backend.request('new','new.mp4',lambda granted:None)
    callbacks[0]([],[])
    assert not launches


def test_skip_audio_explanation_still_allows_silent_video(adapter):
    backend,callbacks,launches,_ = adapter
    backend.request('session','match.mp4',lambda granted:None)
    buttons = backend.audio_dialog.content.children[0]
    next(button for button in buttons.children if button.text == 'SESSİZ KAYDET').dispatch('on_release')
    assert len(launches) == 1 and not callbacks


def test_already_granted_audio_permission_skips_dialog(adapter):
    backend,callbacks,launches,permissions = adapter
    permissions.check_permission = lambda permission:True
    backend.request('session','match.mp4',lambda granted:None)
    assert len(launches) == 1 and backend.audio_dialog is None and not callbacks


def test_manifest_archive_explicitly_allows_playback_capture_without_microphone_service():
    xml = (ROOT/'android_src/capture_manifest.xml').read_bytes()
    with ZipFile(ROOT/'android_src/capture_manifest.aar') as archive:
        assert archive.read('AndroidManifest.xml') == xml
    root = ElementTree.fromstring(xml)
    ns = '{http://schemas.android.com/apk/res/android}'
    assert root.find('application').get(ns+'allowAudioPlaybackCapture') == 'true'
    assert root.find('uses-permission').get(ns+'name') == 'android.permission.RECORD_AUDIO'
    assert root.find('application/service').get(ns+'foregroundServiceType') == 'mediaProjection'


def test_java_capture_is_own_uid_playback_only_and_checks_decoded_output():
    # Packaging/privacy contract only; runtime codec behavior requires an APK.
    source = (ROOT/'android_src/org/simomatch/capture/PlaybackAudio.java').read_text(encoding='utf8')
    assert '.addMatchingUid(Process.myUid())' in source
    assert '.setAudioPlaybackCaptureConfig(capture)' in source
    assert '.setAudioSource(' not in source
    movie = (ROOT/'android_src/org/simomatch/capture/AudioMovie.java').read_text(encoding='utf8')
    assert 'createDecoderByType' in movie and 'rms > 1' in movie
