"""Low-cost translucent controls; no blur pass, animation timer or hitbox change."""
from kivy.graphics import Color, RoundedRectangle, Line
from kivy.metrics import dp
from kivy.uix.button import Button


class GlassButton(Button):
    def __init__(self, **kwargs):
        super().__init__(background_normal='', background_down='',
                         background_color=(0, 0, 0, 0), color=(1, 1, 1, .40),
                         halign='center', valign='middle', **kwargs)
        with self.canvas.before:
            self.fill_color = Color(1, 1, 1, .065)
            self.fill = RoundedRectangle(radius=[dp(9)])
            self.edge_color = Color(1, 1, 1, .125)
            self.edge = Line(width=.8)
        self.bind(pos=self.paint, size=self.paint, state=self.paint)
        self.paint()

    def paint(self, *_):
        self.fill_color.a = .105 if self.state == 'down' else .065
        self.edge_color.a = .19 if self.state == 'down' else .125
        self.fill.pos, self.fill.size = self.pos, self.size
        self.edge.rounded_rectangle = (*self.pos, *self.size, dp(9))
        self.text_size = (max(1, self.width-dp(8)), self.height)
