"""One recording session, asynchronous consent/preparation and match timing.

Only the Android adapter imports platform APIs. Capture/encoding never runs in
the Kivy render loop. The first encoded video sample is the start acknowledgement.
"""
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import json
import logging
import re
from services.graphics_diagnostics import milestone

log = logging.getLogger(__name__)


def video_name(home, away):
    def safe(text):
        return re.sub(r'[^\w-]+', '_', text, flags=re.UNICODE).strip('_')[:40] or 'Takim'
    return f'Simomatch_{safe(home)}_{safe(away)}_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.mp4'


class RecordingPreference:
    """Separate atomic preference; no team/background JSON migration required."""
    def __init__(self, directory):
        self.path = Path(directory)/'video_preferences.json'
        try:
            self.enabled = json.loads(self.path.read_text(encoding='utf8')).get('enabled') is True
        except (OSError, ValueError, AttributeError):
            self.enabled = False

    def save(self, enabled):
        temporary = self.path.with_name(f'.video_{uuid4().hex}.tmp')
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps({'enabled': bool(enabled)}), encoding='utf8')
            temporary.replace(self.path)
            self.enabled = bool(enabled)
        finally:
            temporary.unlink(missing_ok=True)


class VideoRecording:
    def __init__(self, platform, schedule, notify, backend=None):
        self.platform, self.schedule, self.notify = platform, schedule, notify
        self.backend = backend
        self.state, self.token = 'idle', ''
        self.poll_event = self.timeout_event = self.result_event = None
        self.prepared_callback = self.start_callback = None
        self.results_seen = False
        self.closed = False

    @property
    def busy(self):
        return self.state in ('consent', 'preparing', 'prepared', 'starting', 'recording', 'stopping')

    def _cancel(self, field):
        event = getattr(self, field)
        if event:
            event.cancel()
            setattr(self, field, None)

    def _deadline(self, seconds):
        self._cancel('timeout_event')
        token = self.token
        self.timeout_event = self.schedule(lambda _: self._fail('Kayıt işlemi zaman aşımına uğradı.')
                                           if token == self.token and self.busy else None, seconds)

    def prepare(self, settings, callback):
        if self.closed or self.busy:
            callback(False)
            return
        if self.platform != 'android':
            self.notify('Video kaydı yalnızca Android üzerinde destekleniyor.')
            callback(False)
            return
        self.token, self.state = uuid4().hex, 'consent'
        self.results_seen = False
        self.prepared_callback = callback
        try:
            if self.backend is None:
                self.backend = AndroidCapture()
            token = self.token
            self._deadline(180)
            milestone('RECORDING_PERMISSION_REQUESTED', session=token)
            self.backend.request(token, video_name(settings.home['name'], settings.away['name']),
                                 lambda granted: self._consent(token, granted))
        except Exception as exc:
            self._fail(f'Kayıt hazırlanamadı: {exc}')

    def _consent(self, token, granted):
        if token != self.token or self.state != 'consent' or self.closed:
            return
        if not granted:
            self._fail('Ekran kayıt izni verilmedi; maç kayıtsız başlayacak.')
            return
        self.state = 'preparing'
        self._deadline(25)
        self._poll()

    def _poll(self, *_):
        self.poll_event = None
        if not self.busy or self.state == 'consent':
            return
        try:
            status = self.backend.status(self.token)
            state = status.get('state')
            if state == 'prepared' and self.state == 'preparing':
                milestone('RECORDING_PREPARED', session=self.token)
                self.state = 'prepared'
                self._cancel('timeout_event')
                callback, self.prepared_callback = self.prepared_callback, None
                if callback:
                    callback(True)
            elif state == 'recording' and self.state == 'starting':
                self.state = 'recording'
                self._cancel('timeout_event')
                callback, self.start_callback = self.start_callback, None
                if callback:
                    callback(True)
            elif state in ('saved', 'discarded', 'failed'):
                self.state = state
                self._cancel('timeout_event')
                self._cancel('result_event')
                message = (('Video kaydedildi (oyun sesi doğrulandı).' if status.get('audio_verified') is True
                            else 'Video kaydedildi (sessiz).') if state == 'saved' else
                           status.get('message') or 'Kayıt tamamlanamadı; geçersiz video yayımlanmadı.')
                if state == 'saved' and status.get('message'):
                    message += ' '+status['message']
                self.notify(message)
                self._release_callbacks(False)
                return
        except Exception as exc:
            self._fail(f'Kayıt hatası: {exc}')
            return
        if self.busy:
            self.poll_event = self.schedule(self._poll, .03)

    def start(self, callback):
        if self.state != 'prepared':
            callback(False)
            return
        self.state, self.start_callback = 'starting', callback
        try:
            self.backend.start(self.token)
            self._deadline(10)
        except Exception as exc:
            self._fail(f'Video başlatılamadı: {exc}')

    def results_visible(self):
        if self.state != 'recording' or self.results_seen:
            return
        self.results_seen = True
        token = self.token
        self.result_event = self.schedule(lambda _: self.stop() if token == self.token else None, 3.)

    def stop(self):
        self._cancel('result_event')
        if not self.busy or self.state == 'stopping':
            return
        if self.state == 'consent':
            self.backend.cancel_consent()
            self.state = 'discarded'
            self._cancel('timeout_event')
            self._release_callbacks(False)
            return
        self.state = 'stopping'
        try:
            self.backend.stop(self.token)
            self._deadline(60)  # AAC EOS, remux and decoded-sample verification on worker.
        except Exception as exc:
            self._fail(str(exc))

    def _release_callbacks(self, success):
        callbacks = self.prepared_callback, self.start_callback
        self.prepared_callback = self.start_callback = None
        for callback in callbacks:
            if callback:
                callback(success)

    def _fail(self, message):
        log.warning('Video recording: %s', message)
        self._cancel('poll_event')
        self._cancel('timeout_event')
        self._cancel('result_event')
        cleanup_pending = self.state in ('preparing', 'prepared', 'starting', 'recording')
        try:
            if self.backend:
                self.backend.cancel_consent()
                self.backend.stop(self.token)
        except Exception:
            log.exception('Could not stop recording backend')
        self.state = 'failed'
        self.notify(message)
        self._release_callbacks(False)
        if cleanup_pending and not self.closed:
            # Keep new sessions blocked until the native service has released
            # its one-use projection. A failed start still resumes this match.
            self.state = 'stopping'
            self._deadline(60)
            self.poll_event = self.schedule(self._poll, .03)

    def close(self):
        self.closed = True
        self.prepared_callback = self.start_callback = None
        self.stop()
        for field in ('poll_event', 'timeout_event', 'result_event'):
            self._cancel(field)


class AndroidCapture:
    """Activity-result adapter; Java owns the foreground service and hardware codec."""
    request_serial = 8100

    def __init__(self):
        from jnius import autoclass
        self.activity = autoclass('org.kivy.android.PythonActivity').mActivity
        if autoclass('android.os.Build$VERSION').SDK_INT < 29:
            raise RuntimeError('Video kaydı Android 10 veya üzerini gerektirir.')
        milestone('CAPTURE_CLASS_LOAD_REQUESTED', java_class='org.simomatch.capture.CaptureService')
        self.java = autoclass('org.simomatch.capture.CaptureService')
        milestone('CAPTURE_SERVICE_CLASS_LOADED', java_class='org.simomatch.capture.CaptureService')
        self.pending = None
        self.permission_callback = None
        self.audio_dialog = None

    def request(self, token, name, callback):
        from android import activity
        from android.runnable import run_on_ui_thread
        self.cancel_consent()
        type(self).request_serial += 1
        code = type(self).request_serial
        self.pending = (code, token, name, callback)
        activity.bind(on_activity_result=self._result)
        @run_on_ui_thread
        def show():
            if not self.pending or self.pending[0] != code:
                return
            try:
                self.activity.startActivityForResult(self.java.consentIntent(self.activity), code)
            except Exception:
                from kivy.clock import Clock
                self.cancel_consent()
                Clock.schedule_once(lambda _: callback(False), 0)
        # RECORD_AUDIO is required by Android even for playback-only capture.
        # Explain the system's microphone-named prompt before requesting it.
        from android.permissions import check_permission, Permission, request_permissions
        from kivy.clock import Clock
        if check_permission(Permission.RECORD_AUDIO):
            show()
            return
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.button import Button
        from kivy.metrics import dp
        panel = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(12))
        text = Label(text='Yalnızca oyun sesini videoya eklemek için Android ses izni ister.\n'
                          'Mikrofon ve ortam sesi kaydedilmez.\nİzin vermezsen video sessiz kaydedilir.',
                     halign='center')
        text.bind(size=lambda widget,size:setattr(widget,'text_size',size))
        panel.add_widget(text)
        buttons = BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(8))
        allow, silent = Button(text='DEVAM'), Button(text='SESSİZ KAYDET')
        buttons.add_widget(allow); buttons.add_widget(silent); panel.add_widget(buttons)
        dialog = Popup(title='Oyun sesi kaydı', content=panel, size_hint=(.94,None),height=dp(300),auto_dismiss=False)
        self.audio_dialog = dialog
        def dismiss():
            if self.audio_dialog is dialog:
                self.audio_dialog = None
            dialog.dismiss()
        def choose_silent(*_):
            dismiss(); show()
        def ask(*_):
            dismiss()
            def answer(permissions, grants):
                # Activity callback can arrive from another thread or a stale session.
                Clock.schedule_once(lambda _: show() if self.pending and self.pending[0] == code else None,0)
                self.permission_callback = None
            self.permission_callback = answer
            try:
                request_permissions([Permission.RECORD_AUDIO],answer)
            except Exception:
                log.exception('Playback permission unavailable; recording silent video')
                show()
        allow.bind(on_release=ask); silent.bind(on_release=choose_silent)
        dialog.open()

    def _result(self, request, result, intent):
        if not self.pending or request != self.pending[0]:
            return
        from kivy.clock import Clock
        _, token, name, callback = self.pending
        self.cancel_consent()
        try:
            granted = result == -1 and intent is not None
            if granted:
                # Consent has completed; only now may a projection FGS start.
                self.java.prepare(self.activity, token, result, intent, name)
        except Exception:
            log.exception('Projection permission/service startup failed')
            granted = False
        Clock.schedule_once(lambda _: callback(granted), 0)

    def cancel_consent(self):
        if self.audio_dialog:
            self.audio_dialog.dismiss()
            self.audio_dialog = None
        if self.pending:
            from android import activity
            activity.unbind(on_activity_result=self._result)
            self.pending = None

    def status(self, token):
        return json.loads(str(self.java.status(token)))

    def start(self, token):
        self.java.startRecording(token)

    def stop(self, token):
        self.java.stopRecording(token)
