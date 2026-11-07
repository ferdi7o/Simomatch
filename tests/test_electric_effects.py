from math import pi, sin, cos, hypot, atan2
import pytest
from kivy.base import EventLoop
from kivy.graphics import Fbo, Color, Rectangle
from engine.match_engine import MatchEngine
from screens.electric_effects import ElectricPool, ElectricEffects
from screens.match_screen import MatchScreen
from services.match_settings import MatchSettings


@pytest.fixture(scope='module', autouse=True)
def graphics():
    EventLoop.ensure_window()


def test_bolts_are_jagged_morphing_varied_and_slots_reused():
    pool = ElectricPool()
    ids = [id(p) for p in (*pool.bolts, *pool.particles)]
    outward, forks, angles = set(), set(), set()
    for _ in range(80):
        pool.advance(2.)
        for b in pool.bolts:
            assert .15 <= b.life <= .4
            outward.add(b.outward)
            forks.add(b.fork)
            angles.add(round(b.angle, 1))
            a, z = b.chains(b.born+.02, 400), b.chains(b.born+.06, 400)
            assert 5 <= len(a[0])-1 <= 9
            assert len(a) == (2 if b.fork else 1)
            assert a != z
            assert hypot(*a[0][0]) == pytest.approx(400)
    assert outward == forks == {True, False}
    assert len(angles) > 20
    assert len(pool.outward_bolts) == 2 and len(pool.waves) == 6 and len(pool.particles) == 12
    assert ids == [id(p) for p in (*pool.bolts, *pool.particles)]


def test_absolute_timeline_is_fps_independent_and_stops_emitting():
    outcomes = []
    for fps in (30, 60, 120):
        pool = ElectricPool(91)
        for _ in range(fps*3):
            pool.advance(1/fps)
        outcomes.append([(p.born, p.life, p.angle) for p in (*pool.bolts, *pool.particles)])
        pool.advance(1, emitting=False)
        assert pool.idle
        assert 0 <= pool.brightness_boost <= .045
    for state in outcomes[1:]:
        for actual, expected in zip(state, outcomes[0]):
            assert actual == pytest.approx(expected)


def test_diagonal_arms_extend_outward_and_waves_travel_in_both_directions():
    pool = ElectricPool(77)
    directions, leans = set(), set()
    for _ in range(60):
        pool.advance(2.)
        for bolt in pool.bolts:
            assert .0075 <= bolt.width <= .015
            early = bolt.chains(bolt.born+.02, 400)[0]
            later = bolt.chains(bolt.born+.1, 400)[0]
            if bolt.outward:
                leans.add(bolt.lean > 0)
                assert hypot(*early[-1]) > 400
                assert hypot(early[-1][0]-early[0][0], early[-1][1]-early[0][1])/400 == pytest.approx(bolt.reach)
                assert .20 <= bolt.reach <= .35
            else:
                directions.add(bolt.travel > 0)
                delta = (atan2(later[0][1], later[0][0])-atan2(early[0][1], early[0][0])+pi) % (2*pi)-pi
                assert delta == pytest.approx(bolt.travel*.08)
                assert 25*pi/180 <= abs(bolt.span) <= 65*pi/180
                assert early != later
                # Geometry scales uniformly with resolution, including thickness.
                scaled = bolt.chains(bolt.born+.02, 800)[0]
                for a, b in zip(early, scaled):
                    assert b == pytest.approx((2*a[0], 2*a[1]))
    assert directions == leans == {True, False}


def test_lightning_adds_visible_bright_pixels_on_top_of_actual_png():
    from screens.arena_layers import ArenaLayers
    from services.arena_themes import get_theme
    fx = ElectricEffects()
    engine = MatchEngine(seed=7)
    engine.state = 'playing'
    project = lambda x, y: (160+x*.25, 160+y*.25)
    fbo = Fbo(size=(320, 320))
    with fbo:
        Color(.01, .02, .03, 1)
        Rectangle(size=(320, 320))
        layers = ArenaLayers(get_theme('electric_blue').layers)
    assert layers.loaded
    layers.layout(engine.goal, project)
    fbo.draw()
    before = bytes(fbo.pixels)
    fbo.add(fx.canvas)
    fx.update(engine, .15)
    for bolt in fx.pool.bolts:
        bolt.born = fx.pool.time-.02  # Force a visible instant for GPU comparison.
    fx.draw(engine.goal, project)
    fbo.ask_update()
    fbo.draw()
    after = fbo.pixels
    # A real texture underneath cannot occlude the bright cyan/white cores.
    assert sum(after[i] > before[i]+30 and after[i+1] > 130
               for i in range(0, len(after), 4)) > 40


@pytest.mark.parametrize('angle', [0, .4, pi/2, pi, 4.7, 6.1])
def test_gpu_lightning_glow_and_particles_leave_live_goal_gap_empty(angle):
    fx = ElectricEffects()
    fbo = Fbo(size=(320, 320))
    with fbo:
        Color(.04, .06, .08, 1)
        Rectangle(size=(320, 320))
    fbo.add(fx.canvas)
    engine = MatchEngine(seed=7)
    engine.state = 'playing'
    fx.update(engine, .15)
    engine.goal.angle = angle
    for bolt in fx.pool.bolts:
        bolt.born = fx.pool.time-.02
    fx.draw(engine.goal, lambda x, y: (160+x*.25, 160+y*.25))
    fbo.draw()
    pixels = fbo.pixels
    assert sum(pixels[i+2] > pixels[i]+25 for i in range(0, len(pixels), 4)) > 30
    for offset in (-.14, 0, .14):
        for radius in (390, 410, 435, 470, 505):
            x, y = round(160+radius*.25*cos(angle+offset)), round(160+radius*.25*sin(angle+offset))
            index = (y*320+x)*4
            assert list(pixels[index:index+3]) == pytest.approx([10.2, 15.3, 20.4], abs=2)


def test_visual_updates_do_not_touch_physics_and_batch_is_bounded():
    fx, engine = ElectricEffects(), MatchEngine(seed=17)
    engine.state = 'playing'
    before = engine.random.getstate(), [vars(d).copy() for d in engine.disks], vars(engine.goal).copy()
    children = len(fx.canvas.children)
    for _ in range(120):
        fx.update(engine, 1/60)
        fx.draw(engine.goal, lambda x, y: (x, y))
        assert len(fx.mesh.vertices)//6 < 5000
    assert children == len(fx.canvas.children)
    assert before == (engine.random.getstate(), [vars(d) for d in engine.disks], vars(engine.goal))
    engine.state = 'finished'
    fx.update(engine, 1)
    fx.draw(engine.goal, lambda x, y: (x, y))
    assert fx.idle and not fx.mesh.vertices


def test_global_lightning_schedule_is_sparse_random_and_bounded():
    pool = ElectricPool(42)
    assert all(not b.chains(0, 400) for b in pool.outward_bolts)
    births, silent_frames = [], 0
    previous = [b.born for b in pool.outward_bolts]
    for _ in range(120*120):
        pool.advance(1/120)
        active = sum(bool(b.chains(pool.time, 400)) for b in pool.outward_bolts)
        assert active <= 2
        silent_frames += active == 0
        for i, bolt in enumerate(pool.outward_bolts):
            if bolt.born != previous[i]:
                births.append(bolt.born)
                previous[i] = bolt.born
    intervals = [b-a for a, b in zip(births, births[1:])]
    assert 2 <= births[0] <= 4
    assert all(2 <= gap <= 4 for gap in intervals)
    assert len({round(gap, 2) for gap in intervals}) > 10
    assert 2.5 < sum(intervals)/len(intervals) < 3.5
    assert silent_frames > 120*100
    assert len(pool.particles) == 12  # 24 identical emitters -> 12, half the rate.


def test_waves_stay_dense_and_independent_of_outward_cooldown():
    regular, sparse = ElectricPool(91), ElectricPool(91)
    sparse.next_bolt = 10000
    counts = []
    for _ in range(60*20):
        regular.advance(1/60)
        sparse.advance(1/60)
        assert all(not wave.outward for wave in regular.waves)
        assert all(bolt.outward for bolt in regular.outward_bolts)
        assert [(w.born, w.angle, w.life) for w in regular.waves] == [
            (w.born, w.angle, w.life) for w in sparse.waves]
        counts.append(sum(bool(w.chains(regular.time, 400)) for w in regular.waves))
    assert max(counts) == 6
    assert 4 < sum(counts)/len(counts) < 6
    assert sum(n >= 3 for n in counts)/len(counts) > .95


@pytest.mark.parametrize('theme', ['fire_arena', 'electric_blue', 'rainbow_neon'])
def test_electric_layer_is_theme_specific_behind_goal_and_preserves_layout(theme):
    settings = MatchSettings({'id': 'a', 'name': 'A', 'logo': ''},
                             {'id': 'b', 'name': 'B', 'logo': ''}, theme=theme)
    view = MatchScreen(settings=settings, size=(450, 800))
    try:
        assert (view.electric_effects is not None) == (theme == 'electric_blue')
        assert (view.fire_particles is not None) == (theme == 'fire_arena')
        assert view.radius == 450*.37 and view.center_arena == (225, 392)
        if view.electric_effects:
            children = list(view.canvas.children)
            for _, mesh, _ in view.arena_layers.loaded:
                assert children.index(mesh) < children.index(view.electric_effects.canvas)
            assert children.index(view.electric_effects.canvas) < children.index(view.net[0])
            assert children.index(view.electric_effects.canvas) < children.index(view.goal_frame)
    finally:
        view.dispose()


def test_missing_png_keeps_procedural_electricity_working(tmp_path):
    from screens.arena_layers import ArenaLayers
    from services.arena_themes import get_theme
    layers = ArenaLayers(get_theme('electric_blue').layers, root=tmp_path)
    assert not layers.loaded and layers.missing_assets
    fx, engine = ElectricEffects(), MatchEngine()
    fx.update(engine, .1)
    fx.apply_brightness(layers.layer_colors)
    fx.draw(engine.goal, lambda x, y: (x, y))
    assert fx.mesh.vertices


def test_finished_electric_match_stops_clock_and_dispose_clears_mesh():
    settings = MatchSettings({'id': 'a', 'name': 'A', 'logo': ''},
                             {'id': 'b', 'name': 'B', 'logo': ''}, theme='electric_blue')
    view = MatchScreen(settings=settings)
    try:
        view.engine.state = 'finished'
        view.engine.final_elapsed = 4
        for _ in range(100):
            view.update(.1)
        assert view.electric_effects.idle
        assert not view.clock_event.is_triggered
    finally:
        view.dispose()
    assert not view.electric_effects.mesh.vertices
