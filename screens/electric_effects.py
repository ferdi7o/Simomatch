"""Electric-only reusable lightning/energy pools, one GLES2 Canvas batch.

Shares Fire's exact goal clipping helpers without modifying Fire's renderer.
Absolute slot timelines and private per-slot RNG keep lifetime/morphing FPS-safe.
"""
from dataclasses import dataclass, field
from math import sin, cos, pi, hypot
import random
import json
from pathlib import Path
from kivy.graphics import RenderContext, Mesh, Canvas, Color, Callback
from screens.fire_particles import goal_normals, visibility, outside_goal
from screens.mesh_safety import MeshGuard
from services.graphics_diagnostics import milestone
from services.arena_gpu_probe import first_gpu_marker
from screens.particle_texture_batch import ParticleTextureBatch

PROBE_MODES = ('full', 'png_only', 'triangle', 'no_png', 'deferred')


def electric_probe_mode(path=None):
    """Packaged, explicit diagnostic switch; never stored in user/team data."""
    path = Path(path) if path else Path(__file__).resolve().parents[1]/'assets/electric_gpu_probe.json'
    try:
        mode = json.loads(path.read_text(encoding='utf8')).get('mode', 'full')
        if mode in PROBE_MODES:
            return mode
    except (OSError, ValueError, AttributeError):
        pass
    return 'full'


@dataclass(slots=True)
class Bolt:
    rng: random.Random = field(default_factory=random.Random)
    born: float = 0.
    life: float = .2
    rest: float = .03
    angle: float = 0.
    span: float = .2
    outward: bool = False
    fork: bool = False
    segments: int = 6
    width: float = .005
    phase: float = 0.
    reach: float = .13
    lean: float = .5
    travel: float = .8
    oval: float = .02
    jitter: list = field(default_factory=lambda: [0.]*10)

    def renew(self, born):
        self.born, self.life = born, self.rng.uniform(.15, .4)
        self.rest = self.rng.uniform(.015, .055)
        self.angle = self.rng.uniform(0, 2*pi)
        self.span = self.rng.choice((-1, 1))*self.rng.uniform(25*pi/180, 65*pi/180)
        self.outward = self.rng.random() < .45
        self.fork = self.rng.random() < .5
        self.segments = self.rng.randint(5, 9)
        self.width = self.rng.uniform(.003, .006)*2.5
        self.phase = self.rng.uniform(0, 2*pi)
        self.reach = self.rng.uniform(.20, .35)
        self.lean = self.rng.choice((-1, 1))*self.rng.uniform(.35, .85)
        self.travel = self.rng.choice((-1, 1))*self.rng.uniform(.4, 1.4)
        self.oval = self.rng.uniform(.01, .045)
        for i in range(10):
            self.jitter[i] = self.rng.uniform(.5, 1.2)*(-1 if i % 2 else 1)

    def chains(self, now, radius):
        age = now-self.born
        if not 0 <= age < self.life:
            return []
        points = []
        base = self.angle if self.outward else self.angle+self.travel*age
        for i in range(self.segments+1):
            t = i/self.segments
            # Keep the first point on the physical circle. Other vertices
            # change shape continuously, not just by rotating the whole bolt.
            wobble = self.jitter[i]*(.7+.3*sin(self.phase+age*55+i*1.7)) if i else 0.
            if self.outward:
                # A diagonal arm in the local radial/tangent frame. Its tip
                # displacement is 20–35% of R, independent of screen scale.
                distance = radius*self.reach*t
                dx = distance*cos(self.lean)
                dy = distance*sin(self.lean)+radius*.009*wobble*sin(pi*t)
                points.append(((radius+dx)*cos(base)-dy*sin(base),
                               (radius+dx)*sin(base)+dy*cos(base)))
            else:
                angle = base+self.span*t
                # Bowed arcs and alternating offsets make a moving electrical
                # wave rather than a perfectly circular decorative line.
                r = radius*(1+self.oval*sin(pi*t)+.022*wobble)
                points.append((r*cos(angle), r*sin(angle)))
        chains = [points]
        if self.fork:
            x, y = points[self.segments//2]
            angle = base+(self.lean if self.outward else self.span*.5)
            bend = .018*sin(age*70+self.phase)
            chains.append([(x, y), (x+radius*(.04*cos(angle)-bend*sin(angle)),
                                    y+radius*(.04*sin(angle)+bend*cos(angle))),
                           (x+radius*.08*cos(angle+.15), y+radius*.08*sin(angle+.15))])
        return chains


@dataclass(slots=True)
class Energy:
    rng: random.Random = field(default_factory=random.Random)
    born: float = 0.
    life: float = .3
    rest: float = .1
    angle: float = 0.
    speed: float = .08
    angular: float = .1
    size: float = .005
    brightness: float = .6

    def renew(self, born):
        self.born, self.life, self.rest = born, self.rng.uniform(.18, .48), self.rng.uniform(.05, .2)
        self.angle = self.rng.uniform(0, 2*pi)
        self.speed, self.angular = self.rng.uniform(.02, .13), self.rng.uniform(-.2, .2)
        self.size, self.brightness = self.rng.uniform(.003, .008), self.rng.uniform(.35, .75)


class ElectricPool:
    MAX_BOLTS = 2
    MAX_WAVES = 6
    MAX_PARTICLES = 12  # Half as many unchanged emitters: ~50% fewer births.
    BOLT_INTERVAL = (2., 4.)

    def __init__(self, seed=4200):
        self.outward_bolts = [Bolt() for _ in range(self.MAX_BOLTS)]
        self.waves = [Bolt() for _ in range(self.MAX_WAVES)]
        self.bolts = self.outward_bolts+self.waves  # Shared renderer, separate clocks.
        self.particles = [Energy() for _ in range(self.MAX_PARTICLES)]
        self.time = 0.
        self.reset(seed)

    def reset(self, seed=4200):
        self.time = 0.
        self.spawn_random = random.Random(seed+104729)
        self.next_bolt = self.spawn_random.uniform(*self.BOLT_INTERVAL)
        self.bolt_slot = 0
        for i, slot in enumerate((*self.outward_bolts, *self.particles, *self.waves)):
            slot.rng.seed(seed+i*7907)
            slot.renew(0.)
            slot.born = -slot.rng.random()*slot.life
        for wave in self.waves:
            wave.outward = False
        for bolt in self.outward_bolts:
            bolt.outward = True
            bolt.born = -bolt.life  # Start quietly; no initial lightning burst.

    def advance(self, dt, emitting=True):
        self.time += max(0., dt)
        if emitting:
            # One global schedule, not a separate 2–4s timer per bolt slot.
            while self.time >= self.next_bolt:
                bolt = self.outward_bolts[self.bolt_slot]
                bolt.renew(self.next_bolt)
                bolt.outward = True
                self.bolt_slot = (self.bolt_slot+1) % self.MAX_BOLTS
                self.next_bolt += self.spawn_random.uniform(*self.BOLT_INTERVAL)
            for slot in self.particles:
                while self.time >= slot.born+slot.life+slot.rest:
                    slot.renew(slot.born+slot.life+slot.rest)
            # Each wave retains the original short independent renewal timer;
            # the sparse outward-bolt schedule never blocks circumferential flow.
            for wave in self.waves:
                while self.time >= wave.born+wave.life+wave.rest:
                    wave.renew(wave.born+wave.life+wave.rest)
                    wave.outward = False

    @property
    def idle(self):
        return all(self.time >= p.born+p.life for p in (*self.bolts, *self.particles))

    @property
    def brightness_boost(self):
        # Only a slight local-layer brightness lift, never a screen overlay.
        return max((.045*(1-(self.time-b.born)/.065) for b in self.bolts
                    if 0 <= self.time-b.born < .065), default=0.)


class ElectricEffects:
    def __init__(self, probe_mode='full', custom_shader=True, trace=False, renderer=None):
        self.guard = MeshGuard('electric')
        self.texture_batch = None
        self.custom_shader = custom_shader
        self.probe_mode = probe_mode
        self.pool = ElectricPool()
        self.round_id = None
        if renderer == 'texture':
            self.custom_shader = False
            self.texture_batch = ParticleTextureBatch('electric',self.guard,trace)
            self.canvas, self.mesh = self.texture_batch.canvas,self.texture_batch.mesh
            return
        if renderer == 'flat_probe':
            self.custom_shader = custom_shader = False
        if custom_shader:
            self.canvas = RenderContext(use_parent_projection=True, use_parent_modelview=True)
            self.canvas.shader.vs = '''$HEADER$
attribute vec4 particle_color;
void main() {
    frag_color = particle_color * vec4(1.0, 1.0, 1.0, opacity);
    gl_Position = projection_mat * modelview_mat * vec4(vPosition, 0.0, 1.0);
}'''
            self.canvas.shader.fs = '''$HEADER$
void main() { gl_FragColor = frag_color; }'''
        else:
            self.canvas = Canvas()
        with self.canvas:
            if not custom_shader:
                Color(.15, .8, 1, .3)
            if trace:
                Callback(first_gpu_marker('ELECTRIC_MESH_GPU_ENTER'))
            self.mesh = Mesh(vertices=[], indices=[], mode='triangles',
                             fmt=([(b'vPosition', 2, 'float'), (b'particle_color', 4, 'float')] if custom_shader else
                                  [(b'vPosition', 2, 'float'), (b'vTexCoords0', 2, 'float')]))
            if trace:
                Callback(first_gpu_marker('ELECTRIC_MESH_GPU_EXIT'))
        milestone('ELECTRIC_SHADER_READY', success=bool(self.canvas.shader.success) if custom_shader else 'stock_probe', mode=probe_mode)

    @property
    def idle(self):
        return self.pool.idle

    def update(self, engine, dt):
        if self.round_id != engine.round_id:
            self.round_id = engine.round_id
            self.pool.reset(4200+engine.round_id)
        self.pool.advance(dt, emitting=engine.state != 'finished')

    def draw(self, goal, project):
        self.guard.check_thread()
        if self.probe_mode == 'triangle':
            # Same RenderContext, shader and 24-byte format, minimal topology.
            a = goal.angle+pi
            cx, cy = goal.radius*cos(a), goal.radius*sin(a)
            vertices = []
            for dx, dy in ((-8, -8), (8, -8), (0, 8)):
                vertices.extend((*project(cx+dx, cy+dy), .15, .85, 1., .8))
            self._upload(vertices,[0,1,2])
            return
        vertices, indices = [], []
        normals = goal_normals(goal)

        def emit(polygon):
            state = visibility(polygon, normals)
            if state == -1:
                return
            if state == 1:
                pieces = (polygon,)
            else:
                pieces = [part for i in range(1, len(polygon)-1)
                          for part in outside_goal((polygon[0], polygon[i], polygon[i+1]), goal, normals)]
            for part in pieces:
                if len(part) < 3:
                    continue
                start = len(vertices)//6
                for x, y, r, g, b, a in part:
                    px, py = project(x, y)
                    vertices.extend((px, py, r, g, b, a))
                for i in range(1, len(part)-1):
                    indices.extend((start, start+i, start+i+1))

        def ribbon(a, b, width, alpha):
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = max(1e-6, hypot(dx, dy))
            nx, ny = -dy/length, dx/length
            # Three explicit layers: soft blue envelope, cyan body, white core.
            for sign in (-1, 1):
                emit([(a[0]+nx*width*4*sign, a[1]+ny*width*4*sign, .02, .35, 1, 0),
                      (*a, .02, .35, 1, alpha*.32), (*b, .02, .35, 1, alpha*.32),
                      (b[0]+nx*width*4*sign, b[1]+ny*width*4*sign, .02, .35, 1, 0)])
            for scale, rgb, opacity in ((1., (.02, .85, 1), .95),
                                        (.36, (.92, .99, 1), 1.)):
                w = width*scale
                emit([(a[0]-nx*w, a[1]-ny*w, *rgb, alpha*opacity),
                      (a[0]+nx*w, a[1]+ny*w, *rgb, alpha*opacity),
                      (b[0]+nx*w, b[1]+ny*w, *rgb, alpha*opacity),
                      (b[0]-nx*w, b[1]-ny*w, *rgb, alpha*opacity)])

        for bolt in self.pool.bolts:
            chains = bolt.chains(self.pool.time, goal.radius)
            if not chains:
                continue
            progress = (self.pool.time-bolt.born)/bolt.life
            alpha = .9*(1-progress)**.65*(.9+.1*sin(progress*30+bolt.phase))
            for chain in chains:
                for i, (a, b) in enumerate(zip(chain, chain[1:])):
                    width = goal.radius*bolt.width*(1-.4*i/max(1, len(chain)-1))
                    ribbon(a, b, width, alpha)
        for particle in self.pool.particles:
            age = self.pool.time-particle.born
            if not 0 <= age < particle.life:
                continue
            progress = age/particle.life
            angle = particle.angle+particle.angular*age
            radius = goal.radius*(1+particle.speed*age)
            x, y = radius*cos(angle), radius*sin(angle)
            size = goal.radius*particle.size*(1+.5*sin(pi*progress))
            alpha = particle.brightness*sin(pi*progress)
            points = [(x-size, y), (x, y+size), (x+size, y), (x, y-size)]
            for i in range(4):
                emit([(x, y, .65, .95, 1, alpha), (*points[i], .1, .5, 1, 0),
                      (*points[(i+1) % 4], .1, .5, 1, 0)])
        self._upload(vertices,indices)

    def _upload(self, vertices, indices):
        if self.texture_batch:
            self.texture_batch.upload(vertices,indices)
        else:
            self.guard.upload_colors(self.mesh,vertices,indices,self.custom_shader)

    def apply_brightness(self, layer_colors):
        self.guard.check_thread()
        for color in layer_colors:
            color.a = min(.96, color.a+self.pool.brightness_boost)

    def clear(self):
        if self.texture_batch:
            self.texture_batch.clear()
        else:
            self.guard.upload_colors(self.mesh, [], [], self.custom_shader)
