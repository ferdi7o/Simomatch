"""Reusable Fire-only tongues, batched with vertex colors and exact goal clipping."""
from dataclasses import dataclass, field
from math import cos, sin, pi, hypot
import random
from kivy.graphics import RenderContext, Mesh, Canvas, Color, Callback
from screens.mesh_safety import MeshGuard
from services.arena_gpu_probe import first_gpu_marker
from screens.particle_texture_batch import ParticleTextureBatch


@dataclass(slots=True)
class Flame:
    slot: int
    spark: bool = False
    rng: random.Random = field(default_factory=random.Random)
    born: float = 0.
    life: float = 1.
    angle: float = 0.
    angular_speed: float = 0.
    radial_speed: float = 0.
    lift: float = 0.
    width: float = 0.
    length: float = 0.
    brightness: float = 0.
    sway: float = 0.
    origin: float = 1.025

    def renew(self, born, count):
        self.born = born
        self.life = self.rng.uniform(.25, .55) if self.spark else self.rng.uniform(.65, 1.15)
        self.angle = 2*pi*self.slot/count+self.rng.uniform(-.045, .045)
        self.angular_speed = self.rng.uniform(.35, .65) if self.spark else self.rng.uniform(-.12, .12)
        self.radial_speed = self.rng.uniform(.015, .04) if self.spark else self.rng.uniform(.06, .11)
        self.lift = self.rng.uniform(.015, .03)
        self.width = self.rng.uniform(.003, .007) if self.spark else self.rng.uniform(.015, .032)
        self.length = self.rng.uniform(.016, .03) if self.spark else self.rng.uniform(.055, .11)
        self.brightness = self.rng.uniform(.45, .9)
        self.sway = self.rng.uniform(0, 2*pi)
        self.origin = self.rng.uniform(1.015, 1.045) if self.spark else self.rng.uniform(1.035, 1.08)


class FlamePool:
    FLAMES = 60
    SPARKS = 12

    def __init__(self, seed=730):
        self.particles = [Flame(i) for i in range(self.FLAMES)]
        self.particles += [Flame(i, spark=True) for i in range(self.SPARKS)]
        self.time = 0.
        self.reset(seed)

    def reset(self, seed=730):
        self.time = 0.
        for index, particle in enumerate(self.particles):
            particle.rng.seed(seed+index*7919)
            particle.renew(0., self.SPARKS if particle.spark else self.FLAMES)
            particle.born = -particle.rng.random()*particle.life

    def advance(self, dt, emitting=True):
        self.time += max(0., dt)
        if emitting:
            for particle in self.particles:
                # Per-slot RNG + absolute birth times make renewal independent
                # of render order and FPS; reuse the same Python object.
                while self.time >= particle.born+particle.life:
                    particle.renew(particle.born+particle.life,
                                   self.SPARKS if particle.spark else self.FLAMES)

    @property
    def idle(self):
        return all(self.time >= p.born+p.life for p in self.particles)

    def polygon(self, particle, radius):
        """World coordinates and RGBA; lifetime changes shape, size and motion."""
        age = self.time-particle.born
        progress = age/particle.life
        if not 0 <= progress < 1:
            return []
        angle = particle.angle+particle.angular_speed*age
        nx, ny = cos(angle), sin(angle)
        tx, ty = -ny, nx
        radial = radius*(particle.origin+particle.radial_speed*age)
        x, y = nx*radial, ny*radial+radius*particle.lift*age
        width = radius*particle.width*(1-.45*progress)
        length = radius*particle.length*(.2+1.1*progress)
        alpha = particle.brightness*sin(pi*progress)**1.2
        sway = sin(particle.sway+age*9)*width*.65*progress
        if particle.spark:
            return [(x-tx*length, y-ty*length, 1, .38, .03, 0),
                    (x+nx*width, y+ny*width, 1, .8, .12, alpha),
                    (x+tx*length, y+ty*length, 1, .55, .03, 0),
                    (x-nx*width, y-ny*width, 1, .8, .12, alpha)]
        red = (1., .15+.12*(1-progress), .015, alpha*.32)
        hot = (1., .72-.22*progress, .10, alpha)
        tip = (1., .30, .02, 0.)
        points = [(-width, 0., red), (-width*.60+sway, length*.45, hot),
                  (sway*1.8, length, tip), (width*.48+sway, length*.52, hot),
                  (width, 0., red), (0., length*.28, hot)]
        polygon = []
        for u, v, rgba in points:
            px, py = x+tx*u+nx*v, y+ty*u+ny*v+v*.25
            # Limit decorative reach without changing the physical radius.
            factor = min(1., radius*1.32/max(1., hypot(px, py)))
            polygon.append((px*factor, py*factor, *rgba))
        return polygon


def clip_halfplane(polygon, normal, sign):
    if not polygon:
        return []
    result = []
    previous = polygon[-1]
    before = sign*(normal[0]*previous[0]+normal[1]*previous[1])
    for current in polygon:
        after = sign*(normal[0]*current[0]+normal[1]*current[1])
        if (before >= 0) != (after >= 0):
            t = before/(before-after)
            result.append(tuple(a+(b-a)*t for a, b in zip(previous, current)))
        if after >= 0:
            result.append(current)
        previous, before = current, after
    return result


def goal_normals(goal):
    c, s = cos(goal.angle), sin(goal.angle)
    sh, ch = sin(goal.half_angle), cos(goal.half_angle)
    return (sh*c+ch*s, sh*s-ch*c), (sh*c-ch*s, sh*s+ch*c)


def visibility(polygon, normals):
    a, b = normals
    side_a = [a[0]*p[0]+a[1]*p[1] for p in polygon]
    side_b = [b[0]*p[0]+b[1]*p[1] for p in polygon]
    if max(side_a) <= 0 or max(side_b) <= 0:
        return 1  # Entire shape is outside the removed wedge.
    if min(side_a) >= 0 and min(side_b) >= 0:
        return -1
    return 0


def outside_goal(triangle, goal, normals=None):
    """Disjoint visible halfplanes: clip position AND interpolated RGBA."""
    a, b = normals or goal_normals(goal)
    return (clip_halfplane(triangle, a, -1),
            clip_halfplane(clip_halfplane(triangle, a, 1), b, -1))


class FireParticles:
    def __init__(self, custom_shader=True, trace=False, renderer=None):
        self.guard, self.custom_shader = MeshGuard('fire'), custom_shader
        self.texture_batch = None
        self.pool = FlamePool()
        self.round_id = None
        if renderer == 'texture':
            self.custom_shader = False
            self.texture_batch = ParticleTextureBatch('fire',self.guard,trace)
            self.canvas, self.mesh = self.texture_batch.canvas,self.texture_batch.mesh
            return
        if renderer == 'flat_probe':
            self.custom_shader = custom_shader = False
        # Created outside a parent Canvas context, then explicitly inserted
        # behind posts and logos. GLES2-compatible vertex colors, one batch.
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
                Color(1, .45, .08, .3)
            if trace:
                Callback(first_gpu_marker('FIRE_MESH_GPU_ENTER'))
            self.mesh = Mesh(vertices=[], indices=[], mode='triangles',
                             fmt=([(b'vPosition', 2, 'float'), (b'particle_color', 4, 'float')] if custom_shader else
                                  [(b'vPosition', 2, 'float'), (b'vTexCoords0', 2, 'float')]))
            if trace:
                Callback(first_gpu_marker('FIRE_MESH_GPU_EXIT'))

    @property
    def idle(self):
        return self.pool.idle

    def update(self, engine, dt):
        if self.round_id != engine.round_id:
            self.round_id = engine.round_id
            self.pool.reset(730+engine.round_id)
        self.pool.advance(dt, emitting=engine.state != 'finished')

    def draw(self, goal, project):
        self.guard.check_thread()
        vertices, indices = [], []
        normals = goal_normals(goal)
        for particle in self.pool.particles:
            polygon = self.pool.polygon(particle, goal.radius)
            if not polygon:
                continue
            state = visibility(polygon, normals)
            if state == -1:
                continue
            if state == 1:
                # Most tongues need no clipping: share six vertices instead
                # of copying them for every triangle. One GPU draw remains.
                start = len(vertices)//6
                for x, y, r, g, b, a in polygon:
                    px, py = project(x, y)
                    vertices.extend((px, py, r, g, b, a))
                if particle.spark:
                    indices.extend((start, start+1, start+2, start, start+2, start+3))
                else:
                    for i in range(5):
                        indices.extend((start+5, start+i, start+(i+1) % 5))
                continue
            if particle.spark:
                triangles = ((polygon[0], polygon[1], polygon[2]), (polygon[0], polygon[2], polygon[3]))
            else:
                triangles = [(polygon[-1], polygon[i], polygon[(i+1) % 5]) for i in range(5)]
            for triangle in triangles:
                for clipped in outside_goal(triangle, goal, normals):
                    if len(clipped) < 3:
                        continue
                    start = len(vertices)//6
                    for x, y, r, g, b, a in clipped:
                        px, py = project(x, y)
                        vertices.extend((px, py, r, g, b, a))
                    for i in range(1, len(clipped)-1):
                        indices.extend((start, start+i, start+i+1))
        if self.texture_batch:
            self.texture_batch.upload(vertices,indices)
        else:
            self.guard.upload_colors(self.mesh, vertices, indices, self.custom_shader)

    def clear(self):
        if self.texture_batch:
            self.texture_batch.clear()
        else:
            self.guard.upload_colors(self.mesh, [], [], self.custom_shader)
