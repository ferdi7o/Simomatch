"""Small shared controls for the dark violet interface."""
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView
from services.audio import play_button_sound

PURPLE = (.45, .22, .85, 1)


def button(text, action, secondary=False, **kwargs):
    widget = Button(text=text, size_hint_y=None, height=dp(42), font_size=dp(14),
                    background_normal='', background_color=(.14, .12, .22, 1) if secondary else PURPLE,
                    **kwargs)
    def activate(*args):
        play_button_sound()
        action()
    widget.bind(on_release=activate)
    return widget


def caption(text, height=28, **kwargs):
    kwargs.setdefault('font_size', dp(14))
    kwargs.setdefault('color', (.8, .77, .91, 1))
    widget = Label(text=text, size_hint_y=None, height=dp(height), **kwargs)
    widget.bind(size=lambda w, size: setattr(w, 'text_size', (size[0], None)))
    return widget


class Page(Screen):
    def __init__(self, router, title, **kwargs):
        super().__init__(**kwargs)
        self.router = router
        with self.canvas.before:
            Color(.027, .022, .055, 1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._background, size=self._background)
        self.shell = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        self.add_widget(self.shell)
        header = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(10))
        header.add_widget(button('‹ Geri', router.back, secondary=True, size_hint_x=None, width=dp(68)))
        header.add_widget(caption(title, height=42, bold=True, font_size=dp(19)))
        self.shell.add_widget(header)
        scroll = ScrollView(do_scroll_x=False)
        self.scroll = scroll
        self.content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(12), padding=(0, 0, 0, dp(16)))
        self.content.bind(minimum_height=self.content.setter('height'))
        scroll.add_widget(self.content)
        self.shell.add_widget(scroll)
        self.status = caption('', height=64, color=(1, .75, .4, 1))
        self.shell.add_widget(self.status)

    def _background(self, *_):
        self.bg.pos, self.bg.size = self.pos, self.size
