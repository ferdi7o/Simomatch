"""Menu artwork is independent of match geometry, themes and storage."""
from math import sin, cos, pi
from time import monotonic
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle, RoundedRectangle, Ellipse, Line
from kivy.metrics import dp
from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout

PURPLE = (.61, .35, 1, 1)
CYAN = (.2, .84, 1, 1)


def caption(text, **kwargs):
    kwargs.setdefault('color', (.96, .94, 1, 1))
    widget = Label(text=text, halign='center', valign='middle', **kwargs)
    widget.bind(size=lambda w, size: setattr(w, 'text_size', size))
    widget.text_size = widget.size
    return widget


class MenuButton(Button):
    """Rounded Canvas artwork, press feedback and duplicate-release protection."""
    def __init__(self, text, action, sound, variant='secondary', **kwargs):
        super().__init__(text=text, background_normal='', background_down='',
                         background_color=(0, 0, 0, 0), color=(.96, .94, 1, 1), bold=True,
                         halign='center', valign='middle', font_size=dp(14), **kwargs)
        self.action, self.sound, self.variant = action, sound, variant
        self.last_action = float('-inf')
        with self.canvas.before:
            self.glow_color = Color(0, 0, 0, 0)
            self.glow = RoundedRectangle(radius=[dp(16)])
            self.fill_color = Color(1, 1, 1, 1)
            self.fill = RoundedRectangle(radius=[dp(12)])
            self.edge_color = Color(1, 1, 1, 1)
            self.edge = Line(width=1)
        self.bind(pos=self.paint, size=self.paint, state=self.paint)
        self.paint()

    def paint(self, *_):
        primary = self.variant == 'primary'
        rgb = (.51, .25, .88) if primary else (.09, .065, .16)
        factor = .76 if self.state == 'down' else 1
        self.fill_color.rgba = (*(c*factor for c in rgb), 1)
        self.edge_color.rgba = (.85, .26, .4, .48) if self.variant == 'danger' else (*PURPLE[:3], .9 if primary else .5)
        self.glow_color.rgba = (*PURPLE[:3], .11 if primary else .025)
        self.glow.pos, self.glow.size = (self.x-dp(3), self.y-dp(3)), (self.width+dp(6), self.height+dp(6))
        self.fill.pos, self.fill.size = self.pos, self.size
        self.edge.rounded_rectangle = (*self.pos, *self.size, dp(12))
        self.text_size = (max(1, self.width-dp(16)), self.height)

    def on_release(self):
        now = monotonic()
        if self.disabled or now-self.last_action < .35:
            return
        self.last_action = now
        self.sound()
        self.action()


class ArenaEmblem(Widget):
    """One 30Hz Clock event and reused instructions; no simulation involved."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.time, self.clock_event = 0., None
        self.arcs, self.disks, self.halos = [], [], []
        with self.canvas:
            for i in range(8):
                Color(.32, .12, .7, .014+i*.002)
                self.halos.append(Ellipse())
            Color(.035, .025, .08, 1)
            self.field = Ellipse()
            Color(.45, .32, .8, .18)
            self.inner = Line(width=1)
            for i in range(12):
                glow_color = Color(*PURPLE[:3], .11)
                glow = Line(width=dp(5))
                core_color = Color(*CYAN)
                core = Line(width=dp(1.5))
                self.arcs.append((glow_color, glow, core_color, core))
            for rgb in (PURPLE, CYAN):
                Color(*rgb[:3], .14)
                halo = Ellipse()
                Color(*rgb)
                disk = Ellipse()
                Color(.95, .98, 1, .9)
                shine = Ellipse()
                self.disks.append((halo, disk, shine))
            Color(.4, .75, 1, .25)
            self.net = [Line(width=.7) for _ in range(7)]
            Color(.94, .97, 1, 1)
            self.goal = Line(width=dp(1.5))
        self.bind(pos=self.draw, size=self.draw)
        self.draw()

    def start(self):
        if self.clock_event is None or not self.clock_event.is_triggered:
            self.clock_event = Clock.schedule_interval(self.advance, 1/30)

    def stop(self):
        if self.clock_event:
            self.clock_event.cancel()

    def advance(self, dt):
        self.time += dt
        self.draw()

    def draw(self, *_):
        x, y = self.x+self.width/2, self.y+self.height/2
        r = max(1, min(self.width, self.height)*.40)
        for i, shape in enumerate(self.halos):
            radius = r*(1.3-i*.04)
            shape.pos, shape.size = (x-radius, y-radius), (radius*2, radius*2)
        self.field.pos, self.field.size = (x-r, y-r), (r*2, r*2)
        self.inner.circle = (x, y, r*.76)
        start, length = pi/2+.23, 2*pi-.46
        for i, (outer, glow, core, line) in enumerate(self.arcs):
            phase = i/12*2*pi-self.time*.12
            pulse = .8+.2*sin(self.time*1.3+phase)
            rgb = (.2+.4*(.5+.5*sin(phase)), .45+.35*(.5+.5*cos(phase)), 1)
            outer.rgba, core.rgba = (*rgb, .10*pulse), (*rgb, .88*pulse)
            points = [v for j in range(9) for v in
                      (x+r*cos(start+length*(i+j/8)/12), y+r*sin(start+length*(i+j/8)/12))]
            glow.points = line.points = points
        for i, (halo, disk, shine) in enumerate(self.disks):
            angle = self.time*.075+i*pi+.25
            px, py, size = x+cos(angle)*r*.42, y+sin(angle)*r*.28, r*.20
            halo.pos, halo.size = (px-size*1.4, py-size*1.4), (size*2.8, size*2.8)
            disk.pos, disk.size = (px-size, py-size), (size*2, size*2)
            shine.pos, shine.size = (px-size*.42, py+size*.2), (size*.34, size*.34)
        left, right, bottom, top = x-r*.24, x+r*.24, y+r*.96, y+r*1.2
        self.goal.points = (left, bottom, left, top, right, top, right, bottom)
        for i, line in enumerate(self.net):
            if i < 4:
                xx = left+(right-left)*(i+1)/5
                line.points = (xx, bottom, xx, top)
            else:
                yy = bottom+(top-bottom)*(i-3)/4
                line.points = (left, yy, right, yy)


class MenuScreen(Screen):
    def __init__(self, router, **kwargs):
        super().__init__(**kwargs)
        self.router, self.exit_dialog, self._closing = router, None, False
        with self.canvas.before:
            Color(9/255, 7/255, 20/255, 1)
            self.background = Rectangle()
            self.ambient = []
            for i in range(6):
                Color(.27, .10, .6, .009+i*.002)
                self.ambient.append(Ellipse())
        self.emblem = ArenaEmblem(size_hint=(None, None))
        self.add_widget(self.emblem)
        self.title_glow = caption('SIMOMATCH', bold=True, color=(.52, .3, 1, .28), size_hint=(None, None))
        self.title_label = caption('SIMOMATCH', bold=True, color=(.85, .73, 1, 1), size_hint=(None, None))
        self.tagline = caption('Kendi rekabetini oluştur.', color=(.65, .61, .76, 1), size_hint=(None, None))
        for widget in (self.title_glow, self.title_label, self.tagline):
            self.add_widget(widget)
        self.match_button = MenuButton('MAÇ OLUŞTUR', lambda: self.navigate('setup'), self.click_sound, variant='primary')
        self.team_button = MenuButton('TAKIM OLUŞTUR', lambda: self.navigate('teams'), self.click_sound)
        self.exit_button = MenuButton('ÇIKIŞ', self.request_exit, self.click_sound, variant='danger')
        for button in (self.match_button, self.team_button, self.exit_button):
            button.size_hint = (None, None)
            self.add_widget(button)
        self.footer = caption('İKİ TAKIM. TEK ARENA.', color=(.4, .39, .53, 1), font_size=dp(10), size_hint=(None, None))
        self.add_widget(self.footer)
        self.bind(pos=self.layout_menu, size=self.layout_menu)
        self.layout_menu()

    def click_sound(self):
        if self.router.audio:
            self.router.audio.play('button')

    def navigate(self, destination):
        if self.router.current == self.name and not self._closing:
            self.router.go(destination)

    def layout_menu(self, *_):
        w, h, cx = self.width, self.height, self.x+self.width/2
        self.background.pos, self.background.size = self.pos, self.size
        for i, shape in enumerate(self.ambient):
            radius = min(w*.75, h*.42)*(1-i*.1)
            shape.pos, shape.size = (cx-radius, self.y+h*.69-radius), (radius*2, radius*2)
        left, top, right, bottom = getattr(self, 'safe_insets', (0, 0, 0, 0))
        w, h = max(1, w-left-right), max(1, h-top-bottom)
        cx = self.x+left+w/2
        origin = self.y+bottom
        emblem_size = min(w*.64, h*.27, dp(290))
        self.emblem.size = (emblem_size, emblem_size)
        self.emblem.center = (cx, origin+h*.735)
        for title in (self.title_label, self.title_glow):
            title.font_size = min(w*.095, dp(48))
            title.size, title.center = (w*.92, h*.075), (cx, origin+h*.54)
        self.title_glow.y -= dp(2)
        self.tagline.font_size = min(dp(15), w*.038)
        self.tagline.size, self.tagline.center = (w*.9, h*.045), (cx, origin+h*.47)
        width, height = min(w-dp(48), dp(360)), min(dp(56), max(dp(46), h*.065))
        gap = min(dp(15), h*.019)
        for i, button in enumerate((self.match_button, self.team_button, self.exit_button)):
            button.size = (width, height)
            button.pos = (cx-width/2, origin+h*.395-height-i*(height+gap))
        self.footer.size, self.footer.center = (w*.9, dp(24)), (cx, origin+h*.055)

    def set_safe_insets(self, insets):
        self.safe_insets = insets
        self.layout_menu()

    def on_enter(self, *_):
        self.emblem.start()

    def on_pre_enter(self, *_):
        self.emblem.start()

    def on_pre_leave(self, *_):
        self.emblem.stop()
        self.cancel_exit()

    def request_exit(self):
        if self._closing or self.exit_dialog is not None:
            return
        modal = ModalView(size_hint=(None, None), size=(min(self.width-dp(32), dp(370)), dp(204)),
                          background='', background_color=(0, 0, 0, 0),
                          overlay_color=(.01, .005, .03, .82), auto_dismiss=False)
        panel = BoxLayout(orientation='vertical', padding=dp(18), spacing=dp(12))
        with panel.canvas.before:
            Color(.085, .06, .14, 1)
            background = RoundedRectangle(radius=[dp(16)])
            Color(*PURPLE[:3], .5)
            edge = Line(width=1)
        def layout(*_):
            background.pos, background.size = panel.pos, panel.size
            edge.rounded_rectangle = (*panel.pos, *panel.size, dp(16))
        panel.bind(pos=layout, size=layout)
        panel.add_widget(caption('Çıkış', bold=True, font_size=dp(20), size_hint_y=None, height=dp(28)))
        panel.add_widget(caption("Simomatch'ten çıkmak istiyor musun?", font_size=dp(13)))
        buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(10))
        self.cancel_button = MenuButton('İPTAL', self.cancel_exit, self.click_sound)
        self.confirm_button = MenuButton('ÇIKIŞ YAP', self.confirm_exit, self.click_sound, variant='danger')
        buttons.add_widget(self.cancel_button)
        buttons.add_widget(self.confirm_button)
        panel.add_widget(buttons)
        modal.add_widget(panel)
        modal.bind(on_dismiss=lambda *_: setattr(self, 'exit_dialog', None))
        self.exit_dialog = modal
        modal.open()

    def cancel_exit(self):
        if self.exit_dialog:
            self.exit_dialog.dismiss()
            self.exit_dialog = None

    def confirm_exit(self):
        if self._closing:
            return
        self._closing = True
        self.cancel_exit()
        self.emblem.stop()
        app = App.get_running_app()
        if app:
            app.stop()  # App.on_stop already closes match and audio resources.

    def dispose(self):
        self.emblem.stop()
        self.cancel_exit()
