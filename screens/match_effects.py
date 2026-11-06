"""Bounded Canvas pools for trails, contact flashes and short-lived sparks."""
from collections import deque
from math import cos, sin, pi, hypot
import random
from kivy.graphics import Color, Line, Ellipse
from services.arena_themes import EffectStyle


class MatchEffects:
    def __init__(self, style=None):
        self.style = style or EffectStyle()
        self.random = random.Random(2107)  # Separate from the simulation RNG.
        self.time = 0.
        self.last_event = 0
        self.round_id = None
        self.trails = [deque(maxlen=16), deque(maxlen=16)]
        self.trail_drawings = []
        for rgb in self.style.trail_colors:
            pool = []
            for _ in range(15):
                color = Color(*rgb, 0)
                pool.append((color, Line(width=1)))
            self.trail_drawings.append(pool)
        self.particles = []
        self.particle_pool = []
        for _ in range(48):
            color = Color(*self.style.spark_color, 0)
            self.particle_pool.append((color, Line(width=1.1)))
        self.flashes = []
        self.flash_pool = []
        for _ in range(8):
            color = Color(*self.style.flash_color, 0)
            self.flash_pool.append((color, Ellipse()))

    def update(self, engine, dt):
        self.time += max(0, dt)
        if self.round_id != engine.round_id:
            self.round_id, self.last_event = engine.round_id, 0
            for trail in self.trails:
                trail.clear()
            self.particles.clear()
            self.flashes.clear()
        for serial, kind, x, y, team in engine.events:
            if serial <= self.last_event:
                continue
            self.last_event = serial
            if kind == 'respawn':
                self.trails[engine.teams.index(team)].clear()
            elif kind in ('wall', 'post', 'disk', 'soft'):
                self.flashes.append((self.time, x, y))
                if kind == 'disk':
                    for _ in range(min(48, self.style.spark_count)):
                        angle = self.random.uniform(0, 2*pi)
                        speed = self.random.uniform(70, 170)
                        self.particles.append((self.time, x, y, cos(angle)*speed, sin(angle)*speed))
        self.particles = [p for p in self.particles if self.time-p[0] < .24][-48:]
        self.flashes = [f for f in self.flashes if self.time-f[0] < .16][-8:]
        for disk, trail in zip(engine.disks, self.trails):
            while trail and self.time-trail[0][0] > self.style.trail_lifetime:
                trail.popleft()
            if engine.state == 'playing' and (not trail or self.time-trail[-1][0] >= 1/90):
                if trail and hypot(disk.x-trail[-1][1], disk.y-trail[-1][2]) > 160:
                    trail.clear()
                trail.append((self.time, disk.x, disk.y))

    def draw(self, project, scale):
        for trail, pool in zip(self.trails, self.trail_drawings):
            points = list(trail)
            for index, (color, line) in enumerate(pool):
                color.a = 0
                if index+1 < len(points):
                    a, b = points[index:index+2]
                    color.a = .65*max(0, 1-(self.time-a[0])/self.style.trail_lifetime)
                    line.points = (*project(a[1], a[2]), *project(b[1], b[2]))
                    line.width = max(.65, scale*2)
        for index, (color, line) in enumerate(self.particle_pool):
            color.a = 0
            if index < len(self.particles):
                born, x, y, vx, vy = self.particles[index]
                age = self.time-born
                color.a = 1-age/.24
                line.points = (*project(x+vx*age, y+vy*age),
                               *project(x+vx*(age+.025), y+vy*(age+.025)))
        for index, (color, shape) in enumerate(self.flash_pool):
            color.a = 0
            if index < len(self.flashes):
                born, x, y = self.flashes[index]
                age = self.time-born
                color.a = .55*(1-age/.16)
                radius = (12+age*90)*scale
                px, py = project(x, y)
                shape.pos, shape.size = (px-radius, py-radius), (2*radius, 2*radius)
