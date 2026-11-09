"""Screen ownership and match clock lifecycle."""
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from screens.menu_screen import MenuScreen
from screens.team_screen import TeamScreen
from screens.setup_screen import SetupScreen
from screens.match_screen import MatchScreen
from services.video_recording import VideoRecording
from kivy.clock import Clock
from kivy.utils import platform
from kivy.uix.label import Label
from kivy.metrics import dp
from threading import get_ident
from services.graphics_diagnostics import milestone


class AppRouter(ScreenManager):
    def __init__(self, store, picker, audio=None, background_data_dir=None, **kwargs):
        super().__init__(transition=NoTransition(), **kwargs)
        self.store, self.picker = store, picker
        self._graphics_thread = get_ident()
        self._disposed = False
        self._dispatch_events = []
        self.audio = audio
        self.background_data_dir = background_data_dir or getattr(store, 'root', None)
        self.match_view = None
        self.safe_insets = (0, 0, 0, 0)
        self.video = VideoRecording(platform, Clock.schedule_once, self.notify)
        self._launch_pending = False
        self._launch_serial = 0
        self._toast_event = None
        self.history = []
        self.add_widget(MenuScreen(self, name='menu'))
        self.add_widget(TeamScreen(self, name='teams'))
        self.add_widget(SetupScreen(self, name='setup'))
        self.match_page = Screen(name='match')
        self.add_widget(self.match_page)
        self.current = 'menu'

    def go(self, name, remember=True):
        if name == self.current:
            return
        if self._launch_pending:
            self._launch_serial += 1
            self._launch_pending = False
            self.video.stop()
        if remember:
            self.history.append(self.current)
        if self.current == 'match' and name != 'match' and self.match_view:
            self.match_view.dispose()
        self.current = name

    def back(self):
        self.go(self.history.pop() if self.history else 'menu', remember=False)

    def start_match(self, settings):
        if self._disposed:
            return
        if get_ident() != self._graphics_thread:
            milestone('MATCH_START_DISPATCHED_TO_KIVY')
            self._dispatch_events.append(Clock.schedule_once(lambda _: self.start_match(settings), 0))
            return
        milestone('MATCH_START_REQUESTED', theme=settings.theme)
        milestone('RECORDING_ENABLED', enabled=int(settings.record_video),
                  backend_initialized=self.video.backend is not None)
        if self._launch_pending or self.video.busy:
            self.notify('Önceki kayıt işleminin tamamlanması bekleniyor.')
            return
        if self.match_view and self.match_view.recording is self.video:
            # The coordinator is reused, projection tokens are not. An old
            # result view must never stop the next prepared recording on dispose.
            self.match_view.recording = None
        if settings.record_video:
            self._launch_pending = True
            self._launch_serial += 1
            serial = self._launch_serial
            def ready(recording):
                if serial != self._launch_serial:
                    return
                self._launch_pending = False
                self._open_match(settings, self.video if recording else None)
            self.video.prepare(settings, ready)
        else:
            self._open_match(settings)

    def _open_match(self, settings, recording=None):
        if self._disposed:
            return
        if get_ident() != self._graphics_thread:
            self._dispatch_events.append(Clock.schedule_once(lambda _: self._open_match(settings, recording), 0))
            return
        if self.match_view:
            self.match_view.dispose()
        self.match_page.clear_widgets()
        self.match_view = MatchScreen(settings=settings, store=self.store, on_back=self.back, audio=self.audio,
                                      recording=recording, on_restart=lambda: self.start_match(settings),
                                      graphics_selection=self.get_screen('setup').graphics_probe.selection(settings.theme))
        milestone('MATCH_SCREEN_CREATED', theme=settings.theme)
        self.match_page.add_widget(self.match_view)
        self.match_view.set_safe_insets(self.safe_insets)
        self.go('match')

    def notify(self, text):
        """Transient foreground message, including after returning to setup."""
        if self._toast_event:
            self._toast_event.cancel()
        if not hasattr(self, '_toast'):
            from kivy.core.window import Window
            self._toast = Label(size_hint=(None, None), color=(1, .9, .65, 1),
                                font_size=dp(12), halign='center', valign='middle')
            Window.add_widget(self._toast)
        from kivy.core.window import Window
        self._toast.size = (Window.width*.94, dp(68))
        self._toast.text_size = self._toast.size
        self._toast.pos = (Window.width*.03, max(dp(12), Window.height*.10))
        self._toast.text, self._toast.opacity = text, 1
        self._toast_event = Clock.schedule_once(lambda _: setattr(self._toast, 'opacity', 0), 5)

    def pause_recording(self):
        # The consent Activity itself pauses Kivy. Do not cancel its own request.
        if self.video.state != 'consent':
            self.video.stop()

    def set_safe_insets(self, insets):
        self.safe_insets = insets
        for page in self.screens:
            if hasattr(page, 'set_safe_insets'):
                page.set_safe_insets(insets)
        if self.match_view:
            self.match_view.set_safe_insets(insets)

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        for event in self._dispatch_events:
            event.cancel()
        self._dispatch_events.clear()
        self._launch_serial += 1
        self.video.close()
        if self._toast_event:
            self._toast_event.cancel()
        if hasattr(self, '_toast'):
            from kivy.core.window import Window
            Window.remove_widget(self._toast)
        self.get_screen('menu').dispose()
        self.get_screen('setup').on_pre_leave()
        self.get_screen('teams').on_pre_leave()
        if self.match_view:
            self.match_view.dispose()
