"""Persistent canvas instructions, scaled from the simulation coordinate system."""
from math import sin, cos, ceil
from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from engine.match_engine import MatchEngine
from services.media import load_texture
from services.arena_themes import get_theme
from screens.match_visuals import LogoDrawing, NeonRing, cover_coordinates
from screens.match_effects import MatchEffects
from screens.result_panel import ResultPanel
from services.audio import play_button_sound


class MatchScreen(FloatLayout):
    def __init__(self, settings=None, store=None, on_back=None, audio=None, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings
        self.engine = MatchEngine(duration=settings.duration,
                                  teams=(settings.home['name'], settings.away['name']),
                                  radii=settings.radii) if settings else MatchEngine()
        teams = (settings.home, settings.away) if settings else ()
        # Decode custom music before scheduling the match clock/countdown.
        self.audio_session = audio.create_session(teams, store) if audio else None
        textures = [None, None]
        if settings and store:
            for i, team in enumerate((settings.home, settings.away)):
                texture = load_texture(store.asset_path(team['logo']))
                textures[i] = texture
        self.logo_textures = textures
        self.theme = get_theme(settings.theme if settings else 'neon_purple')
        background_texture = load_texture(settings.background) if settings and settings.background else None
        if background_texture is None:
            background_texture = load_texture(self.theme.image_path)
        self.background_texture = background_texture
        with self.canvas.before:
            self.background_color = Color(*((1, 1, 1, 1) if background_texture else self.theme.background_color))
            self.background = Rectangle(texture=background_texture)
            Color(0, 0, 0, .35 if background_texture else 0)
            self.background_shade = Rectangle()
        with self.canvas:
            self.atmosphere = []
            for i in range(10):
                Color(*self.theme.atmosphere_color, (.012+i*.002)*self.theme.glow_strength)
                self.atmosphere.append(Ellipse())
            Color(*self.theme.background_color[:3], .82)
            self.field = Ellipse()
            self.ring = NeonRing(self.theme.palette, self.theme.glow_strength)
            self.effects = MatchEffects(self.theme.effects)
            Color(.8, .94, 1, .58)
            self.net = [Line(width=1) for _ in range(12)]
            Color(.7, .88, 1, .12)
            self.goal_glow = Line(width=5)
            Color(1, 1, 1, 1)
            self.goal_frame = Line(width=2.2)
            self.posts = [Ellipse() for _ in range(2)]
            colors = [(.04, .22, .48), (.76, .1, .11)]
            self.disk_shapes = [LogoDrawing(texture, color) for texture, color in zip(textures, colors)]
            self.header_logos = [LogoDrawing(texture, color) for texture, color in zip(textures, colors)]
        self.score = self.make_label(bold=True)
        self.minute_label = self.make_label(color=(.4, 1, .7, 1))
        self.team_names = [self.make_label(text=name, bold=True, shorten=True, shorten_from='right', halign='center')
                           for name in self.engine.teams]
        self.team_labels = [self.make_label(text='' if texture else name[:3].upper(), bold=True)
                            for name, texture in zip(self.engine.teams, textures)]
        self.score.halign = 'center'
        self.notice = self.make_label(bold=True, color=(1, .86, .15, 1))
        self.result_panel = ResultPanel(self.engine.teams, textures)
        self._result_snapshot = None
        self.add_widget(self.result_panel)
        self.restart_button = Button(text='Yeniden başlat', size_hint=(None, None),
                                     background_color=(.08, .5, .3, 1))
        self.restart_button.bind(on_release=self.restart_match)
        self.add_widget(self.restart_button)
        self.back_button = Button(text='‹ Maç ayarları', size_hint=(None, None),
                                  background_normal='', background_color=(.14, .08, .24, 1))
        def leave(*args):
            play_button_sound()
            if on_back:
                on_back()
        self.back_button.bind(on_release=leave)
        self.add_widget(self.back_button)
        self.bind(size=self.layout_scene, pos=self.layout_scene)
        self.layout_scene()
        self._first_frame = True
        self.clock_event = Clock.schedule_interval(self.update, 0)
        if self.audio_session:
            self.audio_session.update(self.engine)

    def restart_match(self, *args):
        play_button_sound()
        self.engine.restart()
        self.result_panel.set_visible(False)
        self._result_snapshot = None
        if self.audio_session:
            self.audio_session.update(self.engine)

    def dispose(self):
        self.clock_event.cancel()
        if self.audio_session:
            self.audio_session.close()

    def make_label(self, **kwargs):
        label = Label(size_hint=(None, None), **kwargs)
        self.add_widget(label)
        return label

    def layout_scene(self, *_):
        w, h = self.size
        self.background.pos, self.background.size = self.pos, self.size
        self.background_shade.pos, self.background_shade.size = self.pos, self.size
        if self.background_texture:
            self.background.tex_coords = cover_coordinates(self.background_texture, self.size)
        # Reserve header/footer and space outside the circle for goal depth.
        self.radius = max(1., min(w * .37, h * .30))
        self.scale = self.radius / self.engine.arena.radius
        self.center_arena = (self.x + w / 2, self.y + h * .49)
        cx, cy = self.center_arena
        r = self.radius
        self.field.pos, self.field.size = (cx-r, cy-r), (2*r, 2*r)
        for i, shape in enumerate(self.atmosphere):
            glow_radius = r*(1.14-i*.014)
            shape.pos, shape.size = (cx-glow_radius, cy-glow_radius), (2*glow_radius, 2*glow_radius)
        for label, y, height in [(self.score, .925, .09), (self.minute_label, .855, .04),
                                  (self.notice, .49, .15)]:
            label.size = (w * .96, h * height)
            label.center = (self.x+w/2, self.y+h*y)
        self.score.size = (w*.34, h*.09)
        self.minute_label.size = (w*.18, h*.04)
        # Recenter after changing widths; Widget.center depends on current size.
        self.score.center = (self.x+w/2, self.y+h*.925)
        self.minute_label.center = (self.x+w/2, self.y+h*.855)
        self.score.font_size = min(w * .105, h * .06)
        self.score.text_size = self.score.size
        for i, (logo, name) in enumerate(zip(self.header_logos, self.team_names)):
            x = self.x+w*(.18 if i == 0 else .82)
            # 1.7x header-only scale; arena logo radii remain unchanged.
            logo.layout(x, self.y+h*.925, 1.7*min(w*.065, h*.04))
            name.size = (w*.30, h*.045)
            name.center = (x, self.y+h*.825)
            name.text_size = name.size
            name.font_size = min(w*.037, h*.024)
        self.minute_label.font_size = min(w * .045, h * .03)
        self.notice.font_size = min(w * .14, h * .1)
        self.result_panel.pos = (self.x+w*.03, self.y+h*.18)
        self.result_panel.size = (w*.94, h*.60)
        self.restart_button.size = (w * .65, h * .065)
        self.restart_button.center = (self.x+w/2, self.y+h * .1)
        self.restart_button.font_size = min(w*.045, h*.025)
        self.back_button.size = (w*.5, h*.045)
        self.back_button.center = (self.x+w/2, self.y+h*.035)
        self.back_button.font_size = min(w*.035, h*.022)
        self.draw_scene()

    def project(self, x, y):
        return (self.center_arena[0] + x*self.scale, self.center_arena[1] + y*self.scale)

    def draw_scene(self):
        e, s = self.engine, self.scale
        g = e.goal
        self.ring.layout(g, self.project, s)
        self.effects.draw(self.project, s)
        p, q = g.posts
        depth = 100.
        outward = (cos(g.angle)*depth, sin(g.angle)*depth)
        back_p = (p[0]+outward[0], p[1]+outward[1])
        back_q = (q[0]+outward[0], q[1]+outward[1])
        self.goal_frame.points = [v for point in (p, back_p, back_q, q) for v in self.project(*point)]
        self.goal_glow.points = self.goal_frame.points
        self.goal_frame.width = max(1.4, s*4.5)
        self.goal_glow.width = self.goal_frame.width*3
        for i, line in enumerate(self.net):
            if i < 8:
                f = (i+1)/9
                a = (p[0]+(q[0]-p[0])*f, p[1]+(q[1]-p[1])*f)
                b = (a[0]+outward[0], a[1]+outward[1])
            else:
                f = (i-7)/5
                a = (p[0]+outward[0]*f, p[1]+outward[1]*f)
                b = (q[0]+outward[0]*f, q[1]+outward[1]*f)
            line.points = (*self.project(*a), *self.project(*b))
        for shape, point in zip(self.posts, (p, q)):
            x, y = self.project(*point)
            r = g.post_radius*s
            shape.pos, shape.size = (x-r, y-r), (2*r, 2*r)
        for disk, logo, label in zip(e.disks, self.disk_shapes, self.team_labels):
            x, y = self.project(disk.x, disk.y)
            r = disk.radius*s
            logo.layout(x, y, r)
            label.size, label.center, label.font_size = (2*r, 2*r), (x, y), r*.7
        home, away = e.teams
        self.score.text = f"{e.scores[home]} - {e.scores[away]}"
        self.minute_label.text = f"{e.minute}'"
        self.notice.text = str(max(1, ceil(e.countdown))) if e.state == 'countdown' else ('GOOL!' if e.flash > 0 and e.state == 'playing' else '')
        finished = e.state == 'finished'
        self.result_panel.set_visible(finished)
        if finished:
            snapshot = (e.round_id, tuple(e.scores.values()), tuple(e.goals))
            if snapshot != self._result_snapshot:
                self.result_panel.set_result(e.scores, e.goals)
                self._result_snapshot = snapshot
        self.restart_button.opacity = 1 if e.can_restart else 0
        self.restart_button.disabled = not e.can_restart

    def update(self, dt):
        # Exclude synchronous preload time from the first simulation tick.
        if self._first_frame:
            dt, self._first_frame = 0., False
        self.engine.advance(dt)
        if self.audio_session:
            self.audio_session.update(self.engine)
        self.effects.update(self.engine, dt)
        self.draw_scene()
