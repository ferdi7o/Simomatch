from math import cos, sin, pi, hypot
import pytest
from kivy.base import EventLoop
from kivy.graphics import Fbo, Color, Rectangle
from engine.match_engine import MatchEngine
from services.match_settings import MatchSettings
from screens.fire_particles import FlamePool, FireParticles, outside_goal
from screens.match_screen import MatchScreen


@pytest.fixture(scope='module', autouse=True)
def graphics():
    EventLoop.ensure_window()


def test_sixty_flames_are_varied_staggered_and_reuse_the_same_objects():
    pool = FlamePool(seed=4)
    flames = [p for p in pool.particles if not p.spark]
    assert len(flames) == 60 and len(pool.particles) == 72
    assert len({round(p.life, 3) for p in flames}) > 30
    assert len({round(p.born, 3) for p in flames}) > 30
    assert len({round(p.width, 4) for p in flames}) > 30
    assert len({round(p.brightness, 3) for p in flames}) > 30
    objects = [id(p) for p in pool.particles]
    old_births = [p.born for p in pool.particles]
    pool.advance(4)
    assert objects == [id(p) for p in pool.particles]
    assert all(p.born > old for p, old in zip(pool.particles, old_births))
    pool.reset()
    assert objects == [id(p) for p in pool.particles]


def test_geometry_size_motion_and_alpha_really_change_with_lifetime():
    pool = FlamePool(15)
    p = pool.particles[8]
    p.born = 0
    pool.time = p.life*.2
    early = pool.polygon(p, 400)
    pool.time = p.life*.6
    middle = pool.polygon(p, 400)
    pool.time = p.life*.99
    late = pool.polygon(p, 400)
    assert early != middle != late
    assert max(v[5] for v in middle) > max(v[5] for v in late)
    assert hypot(middle[2][0], middle[2][1]) > hypot(early[2][0], early[2][1])
    assert max(v[5] for v in early) != max(v[5] for v in middle)
    assert (max(v[0] for v in early)-min(v[0] for v in early)) != pytest.approx(
        max(v[0] for v in middle)-min(v[0] for v in middle))
    pool.time = p.life
    assert pool.polygon(p, 400) == []


def test_absolute_time_animation_matches_at_30_60_120_fps():
    snapshots = []
    for fps in (30, 60, 120):
        pool = FlamePool(seed=44)
        for _ in range(3*fps):
            pool.advance(1/fps)
        snapshots.append([(p.born, p.life, *pool.polygon(p, 400)[0]) for p in pool.particles])
    for state in snapshots[1:]:
        for actual, reference in zip(state, snapshots[0]):
            assert actual == pytest.approx(reference, abs=1e-8)


def test_sparks_travel_along_the_ring_and_expire():
    from math import atan2
    pool = FlamePool(18)
    particle = pool.particles[pool.FLAMES+2]
    particle.born = 0
    angles = []
    for fraction in (.1, .7):
        pool.time = fraction*particle.life
        points = pool.polygon(particle, 400)
        angles.append(atan2(sum(p[1] for p in points), sum(p[0] for p in points)))
    assert (angles[1]-angles[0]+pi) % (2*pi)-pi > .01
    pool.time = particle.life
    assert pool.polygon(particle, 400) == []


@pytest.mark.parametrize('angle', [0, .17, pi/2, pi, 3*pi/2, 6.1])
def test_gpu_flames_never_fill_the_moving_goal_wedge(angle):
    fire = FireParticles()
    fbo = Fbo(size=(320, 320))
    with fbo:
        Color(.04, .06, .08, 1)
        Rectangle(size=(320, 320))
    fbo.add(fire.canvas)
    e = MatchEngine(seed=2, goal_speed_degrees=180)
    e.state = 'playing'
    fire.update(e, .3)
    e.goal.angle = angle
    fire.draw(e.goal, lambda x, y: (160+x*.25, 160+y*.25))
    fbo.draw()
    pixels = fbo.pixels
    # Warm pixels outside the gap prove the shader batch is actually visible.
    assert sum(pixels[i] > pixels[i+2]+25 for i in range(0, len(pixels), 4)) > 30
    for offset in (-.14, 0, .14):
        for radius in (410, 435, 470, 505):
            x, y = round(160+radius*.25*cos(angle+offset)), round(160+radius*.25*sin(angle+offset))
            index = (y*320+x)*4
            assert list(pixels[index:index+3]) == pytest.approx([10.2, 15.3, 20.4], abs=2)


def test_clipping_removes_partial_triangles_not_just_centers():
    e = MatchEngine()
    e.goal.angle = 0
    triangle = [(400, -150, 1, 0, 0, 1), (430, 0, 1, 1, 0, 1), (400, 150, 1, 0, 0, 1)]
    pieces = outside_goal(triangle, e.goal)
    assert all(len(p) >= 3 for p in pieces)
    for polygon in pieces:
        midpoint = tuple(sum(v[i] for v in polygon)/len(polygon) for i in range(2))
        from math import atan2
        assert abs(atan2(midpoint[1], midpoint[0])) >= e.goal.half_angle-1e-6


def test_fire_batch_is_bounded_and_does_not_change_physics():
    fire = FireParticles()
    e = MatchEngine(seed=17)
    e.state = 'playing'
    before = e.random.getstate(), [vars(d).copy() for d in e.disks], vars(e.goal).copy()
    count = len(fire.canvas.children)
    ids = [id(p) for p in fire.pool.particles]
    for _ in range(120):
        fire.update(e, 1/60)
        fire.draw(e.goal, lambda x, y: (x, y))
        assert len(fire.mesh.vertices)//6 < 5000
    assert len(fire.canvas.children) == count
    assert ids == [id(p) for p in fire.pool.particles]
    assert before == (e.random.getstate(), [vars(d) for d in e.disks], vars(e.goal))
    e.state = 'finished'
    fire.update(e, 1.3)
    fire.draw(e.goal, lambda x, y: (x, y))
    assert fire.idle and fire.mesh.vertices == []


@pytest.mark.parametrize('theme', ['fire_arena', 'electric_blue', 'rainbow_neon'])
def test_only_fire_gets_the_new_layer_and_layout_is_unchanged(theme):
    settings = MatchSettings({'id': 'a', 'name': 'A', 'logo': ''},
                             {'id': 'b', 'name': 'B', 'logo': ''}, theme=theme)
    view = MatchScreen(settings=settings, size=(450, 800))
    try:
        assert (view.fire_particles is not None) == (theme == 'fire_arena')
        assert view.radius == 450*.37 and view.center_arena == (225, 392)
        if view.fire_particles:
            children = list(view.canvas.children)
            assert children.index(view.fire_particles.canvas) < children.index(view.goal_frame)
    finally:
        view.dispose()
