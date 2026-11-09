"""Run with python main.py. Keep Kivy runtime files inside this project."""
import os
from pathlib import Path

os.environ['KIVY_HOME'] = str(Path(__file__).resolve().parent / '.kivy_runtime')

from kivy.config import Config
from kivy.utils import platform
from config import WINDOW_SIZE

if platform not in ('android', 'ios'):
    Config.set('graphics', 'width', str(WINDOW_SIZE[0]))
    Config.set('graphics', 'height', str(WINDOW_SIZE[1]))
elif platform == 'android':
    Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'maxfps', '120')

from kivy.app import App
from kivy.core.window import Window
from screens.router import AppRouter
from services.team_store import TeamStore
from services.file_picker import create_file_picker
from services.audio import AudioManager
from services.backgrounds import refresh_background_catalog
from services.android_display import ImmersiveDisplay


class SimomatchApp(App):
    def on_start(self):
        from kivy.clock import Clock
        self.immersive = ImmersiveDisplay(platform, Window, Clock.schedule_once, self.router.set_safe_insets)
        self.immersive.start()
        self.router.bind(current=self.immersive.request)

    def build(self):
        refresh_background_catalog()
        self.title = 'Simomatch'
        Window.softinput_mode = 'below_target'
        # Desktop data stays within the project; Android uses private app storage.
        data_dir = self.user_data_dir if platform == 'android' else Path(__file__).resolve().parent / 'data'
        store = TeamStore(data_dir)
        self.audio = AudioManager()
        self.router = AppRouter(store, create_file_picker(platform, data_dir), audio=self.audio,
                                background_data_dir=self.user_data_dir)
        Window.bind(on_keyboard=self.on_keyboard)
        return self.router

    def on_keyboard(self, window, key, *_):
        if key == 27:
            if self.router.current == 'menu':
                menu = self.router.get_screen('menu')
                if menu.exit_dialog:
                    menu.cancel_exit()
                else:
                    menu.request_exit()
            else:
                self.router.back()
            return True
        return False

    def on_stop(self):
        if hasattr(self, 'immersive'):
            self.router.unbind(current=self.immersive.request)
            self.immersive.close()
        Window.unbind(on_keyboard=self.on_keyboard)
        if hasattr(self, 'router'):
            self.router.dispose()
        if hasattr(self, 'audio'):
            self.audio.close()

    def on_pause(self):
        if hasattr(self, 'router'):
            self.router.get_screen('menu').emblem.stop()
            if hasattr(self.router, 'pause_recording'):
                self.router.pause_recording()
        if hasattr(self, 'audio'):
            if hasattr(self.audio, 'stop_preview'):
                self.audio.stop_preview()
            for session in self.audio.sessions:
                session.stop()
            self.audio.stop_effect('button')
        return True

    def on_resume(self):
        if hasattr(self, 'immersive'):
            self.immersive.request()
        if hasattr(self, 'router') and self.router.current == 'menu':
            self.router.get_screen('menu').emblem.start()
        view = getattr(getattr(self, 'router', None), 'match_view', None)
        if view:
            view._first_frame = True
            if self.router.current == 'match' and view.engine.state == 'countdown':
                self.audio.play('countdown')


if __name__ == '__main__':
    SimomatchApp().run()
