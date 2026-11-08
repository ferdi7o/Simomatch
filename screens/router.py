"""Screen ownership and match clock lifecycle."""
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from screens.menu_screen import MenuScreen
from screens.team_screen import TeamScreen
from screens.setup_screen import SetupScreen
from screens.match_screen import MatchScreen


class AppRouter(ScreenManager):
    def __init__(self, store, picker, audio=None, background_data_dir=None, **kwargs):
        super().__init__(transition=NoTransition(), **kwargs)
        self.store, self.picker = store, picker
        self.audio = audio
        self.background_data_dir = background_data_dir or getattr(store, 'root', None)
        self.match_view = None
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
        if remember:
            self.history.append(self.current)
        if self.current == 'match' and name != 'match' and self.match_view:
            self.match_view.dispose()
        self.current = name

    def back(self):
        self.go(self.history.pop() if self.history else 'menu', remember=False)

    def start_match(self, settings):
        if self.match_view:
            self.match_view.dispose()
        self.match_page.clear_widgets()
        self.match_view = MatchScreen(settings=settings, store=self.store, on_back=self.back, audio=self.audio)
        self.match_page.add_widget(self.match_view)
        self.go('match')

    def dispose(self):
        self.get_screen('menu').dispose()
        self.get_screen('setup').on_pre_leave()
        self.get_screen('teams').on_pre_leave()
        if self.match_view:
            self.match_view.dispose()
