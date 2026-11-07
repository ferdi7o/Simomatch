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
from screens.arena_layers import ArenaLayers
from services.audio import play_button_sound
from screens.announcements import Announcements, CardIndicators
from screens.fire_particles import FireParticles
from screens.electric_effects import ElectricEffects


class MatchScreen(FloatLayout):
    def __init__(self, settings=None, store=None, on_back=None, audio=None, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings
        self._disposed = False
        self._finished_render_key = None
        self.engine = MatchEngine(duration=settings.duration,
                                  teams=(settings.home['name'], settings.away['name']),
                                  radii=settings.radii,
                                  goal_speed_degrees=settings.goal_speed_degrees,
                                  goal_size_percent=settings.goal_size_percent) if settings else MatchEngine()
        teams = (settings.home, settings.away) if settings else ()
        # Decode custom music before scheduling the match clock/countdown.
        self.audio_session = audio.create_session(teams, store) if audio else None
        if self.audio_session:
            self.audio_session.defer_cards = True
        textures = [None, None]
        if settings and store:
            for i, team in enumerate((settings.home, settings.away)):
                texture = load_texture(store.asset_path(team['logo']))
                textures[i] = texture
        self.logo_textures = textures
        self.theme = get_theme(settings.theme if settings else 'neon_purple')
        self.fire_particles = FireParticles() if settings and settings.theme == 'fire_arena' else None
        self.electric_effects = ElectricEffects() if settings and settings.theme == 'electric_blue' else None
        background_texture = load_texture(settings.background) if settings and settings.background else None
        if background_texture is None:
            for path in self.theme.image_paths:
                background_texture = load_texture(path)
                if background_texture is not None:
                    break
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
            self.ring = NeonRing(self.theme.palette, self.theme.glow_strength,
                                 self.theme.decorative_speed_degrees, self.theme.pulse_hz)
            self.arena_layers = ArenaLayers(self.theme.layers)
            if self.fire_particles:
                self.canvas.add(self.fire_particles.canvas)
            if self.electric_effects:
                self.canvas.add(self.electric_effects.canvas)
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
        self.card_indicators = [CardIndicators() for _ in range(2)]
        for indicator in self.card_indicators:
            self.add_widget(indicator)
        self.announcements = Announcements(on_start=self.announcement_started)
        self.add_widget(self.announcements)
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
        if self._disposed:
            return
        play_button_sound()
        self.engine.restart()
        self.announcements.reset()
        self.result_panel.set_visible(False)
        self._result_snapshot = None
        self._finished_render_key = None
        if not self.clock_event.is_triggered:
            self._first_frame = True
            self.clock_event = Clock.schedule_interval(self.update, 0)
        if self.audio_session:
            self.audio_session.update(self.engine)

    def dispose(self):
        self._disposed = True
        self.clock_event.cancel()
        self.announcements.reset()
        if self.fire_particles:
            self.fire_particles.clear()
        if self.electric_effects:
            self.electric_effects.clear()
        if self.audio_session:
            self.audio_session.close()

    def announcement_started(self, kind, team):
        if kind in ('yellow_card', 'red_card') and self.audio_session:
            self.audio_session.manager.play(kind)

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
        for i, indicator in enumerate(self.card_indicators):
            indicator.pos = (self.x+w*(.005 if i == 0 else .935), self.y+h*.885)
            indicator.size = (w*.06, h*.075)
        # Reserve the full moving goal depth; never move/resize the arena.
        bottom = cy+r*1.26+h*.003
        top = min(label.y for label in self.team_names)-h*.004
        goal_bounds = (self.x+w*.15, bottom, w*.70, max(1., top-bottom))
        card_bottom = self.y+h*.15
        card_top = cy-r-h*.02
        card_bounds = (self.x+w*.12, card_bottom, w*.76, max(1., card_top-card_bottom))
        self.announcements.set_bounds(goal_bounds, card_bounds)
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
        self.arena_layers.layout(g, self.project)
        if self.fire_particles:
            self.fire_particles.draw(g, self.project)
        if self.electric_effects:
            self.electric_effects.apply_brightness(self.arena_layers.layer_colors)
            self.electric_effects.draw(g, self.project)
        self.effects.draw(self.project, s)
        p, q = g.posts
        depth = 100.*(g.size_percent/100)**.5
        outward = (cos(g.angle)*depth, sin(g.angle)*depth)
        back_p = (p[0]+outward[0], p[1]+outward[1])
        back_q = (q[0]+outward[0], q[1]+outward[1])
        self.goal_frame.points = [v for point in (p, back_p, back_q, q) for v in self.project(*point)]
        self.goal_glow.points = self.goal_frame.points
        self.goal_frame.width = max(1.4, s*4.5*(g.size_percent/100)**.5)
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
        self.notice.text = str(max(1, ceil(e.countdown))) if e.state == 'countdown' else ''
        for team, indicator in zip(e.teams, self.card_indicators):
            indicator.set_counts(sum(c.team == team and c.kind == 'yellow_card' for c in e.cards),
                                 sum(c.team == team and c.kind == 'red_card' for c in e.cards))
        finished = e.state == 'finished' and self.announcements.idle
        self.result_panel.set_visible(finished)
        if finished:
            snapshot = (e.round_id, tuple(e.scores.values()), tuple(e.goals), tuple(e.cards))
            if snapshot != self._result_snapshot:
                self.result_panel.set_result(e.scores, e.goals, e.cards)
                self._result_snapshot = snapshot
        self.restart_button.opacity = 1 if e.can_restart else 0
        self.restart_button.disabled = not e.can_restart

    def update(self, dt):
        if self._disposed:
            return
        # Exclude synchronous preload time from the first simulation tick.
        if self._first_frame:
            dt, self._first_frame = 0., False
        self.engine.advance(dt)
        finished = self.engine.state == 'finished'
        if not finished:
            self.ring.advance(dt)
            self.arena_layers.advance(dt)
        fire_pending = self.fire_particles and (not finished or not self.fire_particles.idle or
                                               self.fire_particles.round_id != self.engine.round_id)
        if fire_pending:
            self.fire_particles.update(self.engine, dt)
        electric_pending = self.electric_effects and (not finished or not self.electric_effects.idle or
                                                     self.electric_effects.round_id != self.engine.round_id)
        if electric_pending:
            self.electric_effects.update(self.engine, dt)
        if self.audio_session:
            self.audio_session.update(self.engine)
        self.announcements.sync(self.engine)
        self.announcements.advance(dt)
        # Let short-lived effects drain, then avoid all arena mesh rebuilding.
        effects_pending = (not finished or not self.effects.idle or
                           self.effects.round_id != self.engine.round_id or
                           self.effects.last_event < self.engine.event_serial)
        if effects_pending:
            self.effects.update(self.engine, dt)
        key = ((self.engine.round_id, self.announcements.idle, self.engine.can_restart,
                tuple(self.engine.scores.values()), tuple(self.engine.goals), tuple(self.engine.cards))
               if finished else None)
        if not finished or effects_pending or fire_pending or electric_pending or key != self._finished_render_key:
            self.draw_scene()
        self._finished_render_key = key if finished else None
        # Audio fades have their own Clock callbacks and keep running safely.
        if (finished and self.effects.idle and self.announcements.idle and self.engine.can_restart
                and (self.fire_particles is None or self.fire_particles.idle)
                and (self.electric_effects is None or self.electric_effects.idle)):
            self.clock_event.cancel()
