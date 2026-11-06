from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from screens.common import Page, button, caption


class MenuScreen(Page):
    def __init__(self, router, **kwargs):
        super().__init__(router, 'SIMOMATCH', **kwargs)
        self.shell.clear_widgets()
        anchor = AnchorLayout()
        panel = BoxLayout(orientation='vertical', size_hint=(None, None),
                          width=dp(320), height=dp(300), spacing=dp(16))
        self.bind(width=lambda _, w: setattr(panel, 'width', min(dp(320), max(dp(100), w-dp(48)))))
        panel.add_widget(caption('SIMOMATCH', height=62, font_size=dp(34), bold=True, color=(.72, .5, 1, 1)))
        panel.add_widget(caption('Kendi rekabetini oluştur.', height=36))
        self.match_button = button('MAÇ OLUŞTUR', lambda: router.go('setup'))
        self.team_button = button('TAKIM OLUŞTUR', lambda: router.go('teams'), secondary=True)
        panel.add_widget(self.match_button)
        panel.add_widget(self.team_button)
        anchor.add_widget(panel)
        self.shell.add_widget(anchor)
