"""Queued goal/card presentation. Persistent Canvas instructions and labels."""
from collections import deque
from math import sin, cos, pi
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label


class Announcements(FloatLayout):
    DURATIONS = {'goal': 1.8, 'yellow_card': 1.5, 'red_card': 1.5}

    def __init__(self, on_start=None, **kwargs):
        super().__init__(size_hint=(None, None), **kwargs)
        self.on_start = on_start
        self.queue, self.active = deque(), None
        self.age, self.serial, self.round_id = 0., 0, None
        self.goal_bounds = self.card_bounds = (0, 0, 100, 30)
        with self.canvas.before:
            self.burst_color = Color(1, .85, .3, 0)
            self.rays = [Line(width=1.2) for _ in range(8)]
            self.card_color = Color(1, .8, .15, 0)
            self.card = RoundedRectangle(radius=[3])
        self.glow = Label(size_hint=(None, None), bold=True, color=(1, .75, .15, 0))
        self.text = Label(size_hint=(None, None), bold=True, shorten=True, shorten_from='right', halign='center')
        self.subtitle = Label(size_hint=(None, None), halign='center')
        for label in (self.glow, self.text, self.subtitle):
            self.add_widget(label)
        self.opacity = 0

    @property
    def idle(self):
        return self.active is None and not self.queue

    def reset(self):
        self.queue.clear()
        self.active = None
        self.age = 0.
        self.opacity = 0

    def sync(self, engine):
        if self.round_id != engine.round_id:
            self.reset()
            self.round_id, self.serial = engine.round_id, 0
        for serial, kind, x, y, team in engine.events:
            if serial > self.serial:
                self.serial = serial
                if kind in self.DURATIONS:
                    self.queue.append((kind, team))

    def advance(self, dt):
        remaining = max(0., dt)
        while True:
            if self.active is None:
                if not self.queue:
                    break
                self.active, self.age = self.queue.popleft(), 0.
                if self.on_start:
                    self.on_start(*self.active)
            step = min(remaining, self.DURATIONS[self.active[0]]-self.age)
            self.age += step
            remaining -= step
            if self.age+1e-9 >= self.DURATIONS[self.active[0]]:
                self.active = None
                if remaining > 0:
                    continue
            break
        self.draw()

    def set_bounds(self, goal_bounds, card_bounds):
        self.goal_bounds, self.card_bounds = goal_bounds, card_bounds
        self.draw()

    def draw(self):
        if self.active is None:
            self.opacity = 0
            return
        kind, team = self.active
        self.pos, self.size = (self.goal_bounds[:2], self.goal_bounds[2:]) if kind == 'goal' else (self.card_bounds[:2], self.card_bounds[2:])
        w, h = self.size
        duration = self.DURATIONS[kind]
        fade = min(1., max(0., (duration-self.age)/.55))
        alpha = min(1., self.age/.12)*fade*fade*(3-2*fade)
        grow = .55+.45*sin(min(1., self.age/.25)*pi/2)
        self.opacity = alpha
        self.card_color.a = 0 if kind == 'goal' else 1
        self.burst_color.a = max(0., 1-self.age/.35)*.7 if kind == 'goal' else 0
        for i, ray in enumerate(self.rays):
            angle = 2*pi*i/8
            rx, ry = w*.16*cos(angle), h*.42*sin(angle)
            ray.points = (self.center_x+rx*.65, self.center_y+ry*.65, self.center_x+rx, self.center_y+ry)
        if kind == 'goal':
            self.text.text, self.subtitle.text = 'GOOL!', ''
            self.text.color = (1, .89, .35, 1)
            self.text.size, self.text.center = (w, h), self.center
            self.text.font_size = min(w*.16, h*.94)*grow
            self.glow.text = 'GOOL!'
            self.glow.size, self.glow.center = self.text.size, (self.center_x+1, self.center_y+1)
            self.glow.font_size = self.text.font_size*1.04
            self.glow.color = (1, .7, .12, .25)
        else:
            self.glow.text = ''
            self.card_color.rgba = (1, .8, .1, 1) if kind == 'yellow_card' else (1, .15, .14, 1)
            self.card.pos, self.card.size = (self.x+w*.14, self.y+h*.18), (h*.39*grow, h*.63*grow)
            self.text.text = team or ''
            self.text.color = (1, 1, 1, 1)
            self.text.size, self.text.center = (w*.65, h*.46), (self.x+w*.62, self.y+h*.66)
            self.text.font_size = min(w*.06, h*.27)*grow
            self.subtitle.text = 'SARI KART' if kind == 'yellow_card' else 'KIRMIZI KART'
            self.subtitle.size, self.subtitle.center = (w*.65, h*.3), (self.x+w*.62, self.y+h*.32)
            self.subtitle.font_size = min(w*.04, h*.20)
        self.text.text_size = self.text.size


class CardIndicators(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(size_hint=(None, None), **kwargs)
        self.counts = (0, 0)
        self.icons = []
        with self.canvas.before:
            for rgb in ((1, .8, .1), (1, .15, .14)):
                color = Color(*rgb, 0)
                self.icons.append((color, RoundedRectangle(radius=[1])))
        self.labels = [Label(size_hint=(None, None), bold=True) for _ in range(2)]
        for label in self.labels:
            self.add_widget(label)
        self.bind(pos=self.layout_icons, size=self.layout_icons)

    def set_counts(self, yellow, red):
        self.counts = (yellow, red)
        self.layout_icons()

    def layout_icons(self, *args):
        for i, ((color, icon), label, count) in enumerate(zip(self.icons, self.labels, self.counts)):
            color.a = 1 if count else 0
            width = max(6., self.width*.3)
            height = min(self.height*.34, width*1.5)
            y = self.y+self.height*(.72 if i == 0 else .22)
            icon.pos, icon.size = (self.x, y-height/2), (width, height)
            label.text = str(count) if count else ''
            label.pos, label.size = (self.x+width+1, y-height/2), (self.width-width-1, height)
            label.font_size = max(10., self.width*.48)
