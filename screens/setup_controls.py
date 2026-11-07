"""Canvas controls scoped to match setup; no game or shared-screen styling."""
from math import cos, sin, pi
from kivy.event import EventDispatcher
from kivy.properties import StringProperty, ListProperty, BooleanProperty
from kivy.graphics import Color, RoundedRectangle, Line, Ellipse
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from services.audio import play_button_sound

BG = (16/255, 11/255, 32/255, 1)
SURFACE = (33/255, 25/255, 54/255, 1)
SECONDARY = (48/255, 36/255, 71/255, 1)
ACCENT = (155/255, 100/255, 1, 1)
TEXT = (244/255, 239/255, 1, 1)
MUTED = (185/255, 169/255, 214/255, 1)


class ChoiceValue(EventDispatcher):
    """Retain the existing text/value binding contract without a stock Spinner."""
    text = StringProperty('')
    values = ListProperty([])


class SettingHeading(BoxLayout):
    text = StringProperty('')

    def __init__(self, text, **kwargs):
        super().__init__(size_hint_y=None, height=dp(24), **kwargs)
        self.title = label(bold=True, font_size=dp(11), size_hint_y=1)
        self.value = label(color=ACCENT, bold=True, font_size=dp(12), halign='right',
                           size_hint=(None, 1), width=dp(68))
        self.add_widget(self.title)
        self.add_widget(self.value)
        self.bind(text=self.refresh)
        self.text = text

    def refresh(self, *_):
        title, _, value = self.text.partition('·')
        self.title.text, self.value.text = title.strip(), value.strip()


def label(text='', height=24, **kwargs):
    defaults = dict(color=TEXT, font_size=dp(12), size_hint_y=None, height=dp(height),
                    halign='left', valign='middle', shorten=True, shorten_from='right')
    defaults.update(kwargs)
    if 'size_hint' in kwargs and 'size_hint_y' not in kwargs:
        defaults.pop('size_hint_y', None)
    widget = Label(text=text, **defaults)
    widget.bind(size=lambda w, size: setattr(w, 'text_size', size))
    widget.text_size = widget.size
    return widget


class Surface(BoxLayout):
    selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*SURFACE)
            self.panel = RoundedRectangle(radius=[dp(14)])
            self.outline_color = Color(*SECONDARY)
            self.outline = Line(width=1)
        self.bind(pos=self.paint, size=self.paint, selected=self.paint)
        self.paint()

    def paint(self, *_):
        self.panel.pos, self.panel.size = self.pos, self.size
        self.outline_color.rgba = ACCENT if self.selected else SECONDARY
        self.outline.rounded_rectangle = (*self.pos, *self.size, dp(14))
        self.outline.width = 1.4 if self.selected else .7


class Action(Button):
    def __init__(self, text, callback, primary=False, **kwargs):
        defaults = dict(size_hint_y=None, height=dp(38), font_size=dp(12), bold=True)
        defaults.update(kwargs)
        if 'size_hint' in kwargs and 'size_hint_y' not in kwargs:
            defaults.pop('size_hint_y', None)
        super().__init__(text=text, background_normal='', background_down='',
                         background_color=(0, 0, 0, 0), color=TEXT,
                         halign='center', valign='middle', **defaults)
        self.primary = primary
        with self.canvas.before:
            self.tint = Color(*(ACCENT if primary else SECONDARY))
            self.fill = RoundedRectangle(radius=[dp(10)])
            self.edge_color = Color(*((.73, .53, 1, .6) if primary else (.6, .4, .9, .15)))
            self.edge = Line(width=.8)
        self.bind(pos=self.paint, size=self.paint, state=self.paint, disabled=self.paint)
        self.bind(on_release=lambda *_: (play_button_sound(), callback()))
        self.bind(size=lambda w, size: setattr(w, 'text_size', (max(0, size[0]-dp(8)), size[1])))
        self.shorten = True
        self.paint()

    def paint(self, *_):
        rgb = ACCENT if self.primary else SECONDARY
        factor = .78 if self.state == 'down' else 1
        self.tint.rgba = tuple(c*factor for c in rgb[:3])+( .35 if self.disabled else 1,)
        self.fill.pos, self.fill.size = self.pos, self.size
        self.edge.rounded_rectangle = (*self.pos, *self.size, dp(10))


class NeonSlider(Slider):
    def __init__(self, **kwargs):
        super().__init__(padding=dp(12), **kwargs)
        # Keep Slider's tested touch handling; replace only its stock artwork.
        self.canvas.clear()
        with self.canvas:
            Color(*SECONDARY)
            self.track = Line(width=dp(2.3))
            Color(*ACCENT)
            self.active_track = Line(width=dp(2.3))
            Color(*ACCENT[:3], .16)
            self.glow = Ellipse()
            Color(*TEXT)
            self.thumb = Ellipse()
        self.bind(pos=self.paint, size=self.paint, value=self.paint, min=self.paint, max=self.paint)
        self.paint()

    def paint(self, *_):
        # Calculate from raw geometry: AliasProperty caches may update after
        # pos/size callbacks, leaving old track endpoints during a resize.
        y = self.y+self.height/2
        start, end = self.x+self.padding, self.x+self.width-self.padding
        x = start+(end-start)*self.value_normalized
        self.track.points = (start, y, end, y)
        self.active_track.points = (start, y, x, y)
        self.glow.pos, self.glow.size = (x-dp(11), y-dp(11)), (dp(22), dp(22))
        self.thumb.pos, self.thumb.size = (x-dp(5), y-dp(5)), (dp(10), dp(10))


class DurationInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(text='55', multiline=False, input_filter='int', input_type='number',
                         background_normal='', background_active='', background_color=SECONDARY,
                         foreground_color=TEXT, cursor_color=ACCENT, halign='center',
                         font_size=dp(25), padding=(dp(4), dp(5)), **kwargs)
        self.last_valid = 55
        self.bind(focus=self.commit)
        self.bind(on_text_validate=lambda *_: self.commit(self, False))

    def insert_text(self, substring, from_undo=False):
        start, end = (sorted((self.selection_from, self.selection_to)) if self.selection_text
                      else (self.cursor_index(), self.cursor_index()))
        candidate = self.text[:start]+substring+self.text[end:]
        if substring.isdigit() and len(candidate) <= 3 and int(candidate) <= 600:
            super().insert_text(substring, from_undo=from_undo)

    def commit(self, _, focused):
        if not focused:
            try:
                value = max(10, min(600, int(self.text)))
            except ValueError:
                value = self.last_valid
            self.last_valid = value
            self.text = str(value)


class ThemeTile(ButtonBehavior, Surface):
    def __init__(self, key, title, texture, palette, callback, **kwargs):
        super().__init__(orientation='vertical', padding=dp(7), spacing=dp(4),
                         size_hint=(None, None), size=(dp(116), dp(112)), **kwargs)
        self.key = key
        if texture:
            from kivy.uix.image import Image
            self.add_widget(Image(texture=texture, fit_mode='contain'))
        else:
            self.add_widget(RingPreview(palette))
        self.add_widget(label(title, height=24, halign='center', font_size=dp(11), bold=True))
        self.bind(on_release=lambda *_: (play_button_sound(), callback(key)))


class RingPreview(Widget):
    """Honest Canvas placeholder for themes without a local preview asset."""
    def __init__(self, palette, **kwargs):
        super().__init__(**kwargs)
        self.strokes = []
        with self.canvas:
            for color in palette:
                Color(*color, .85)
                self.strokes.append(Line(width=dp(2)))
        self.bind(pos=self.paint, size=self.paint)
        self.paint()

    def paint(self, *_):
        radius = max(1, min(self.width, self.height)*.38)
        for i, line in enumerate(self.strokes):
            line.points = [coordinate for j in range(17) for coordinate in
                           (self.center_x+radius*cos(2*pi*(i+j/16)/len(self.strokes)),
                            self.center_y+radius*sin(2*pi*(i+j/16)/len(self.strokes)))]


class BackgroundTile(ButtonBehavior, Surface):
    def __init__(self, key, title, texture, callback, fallback=False, **kwargs):
        super().__init__(orientation='vertical', padding=dp(7), spacing=dp(4),
                         size_hint=(None, None), size=(dp(116), dp(128)), **kwargs)
        self.key = key
        from kivy.uix.image import Image
        from kivy.uix.floatlayout import FloatLayout
        area = FloatLayout()
        self.preview = Image(texture=texture, fit_mode='contain', pos_hint={'x': 0, 'y': 0})
        placeholder = label('Varsayılan', size_hint=(1, 1), pos_hint={'x': 0, 'y': 0},
                            color=MUTED, halign='center', font_size=dp(11))
        placeholder.opacity = 0 if texture else 1
        self.preview.bind(texture=lambda _, value: setattr(placeholder, 'opacity', 0 if value else 1))
        area.add_widget(self.preview)
        area.add_widget(placeholder)
        self.add_widget(area)
        if fallback and texture is not None:
            self.add_widget(label('Varsayılan görsel', height=14, halign='center', color=MUTED, font_size=dp(8)))
        self.add_widget(label(title, height=24, halign='center', font_size=dp(10), bold=True))
        self.bind(on_release=lambda *_: (play_button_sound(), callback(key)))


class TeamRow(ButtonBehavior, Surface):
    def __init__(self, team, texture, callback, **kwargs):
        super().__init__(size_hint_y=None, height=dp(60), padding=dp(8), spacing=dp(12), **kwargs)
        from kivy.uix.image import Image
        if texture:
            self.add_widget(Image(texture=texture, fit_mode='contain', size_hint_x=None, width=dp(44)))
        else:
            self.add_widget(label(team['name'][:2].upper(), height=44, halign='center',
                                  size_hint=(None, 1), width=dp(44), bold=True, color=ACCENT))
        self.add_widget(label(team['name'], size_hint_y=1, font_size=dp(14)))
        self.bind(on_release=lambda *_: (play_button_sound(), callback(team['name'])))
