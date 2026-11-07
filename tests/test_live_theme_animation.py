from math import pi, cos, sin
import pytest
from kivy.graphics import Fbo, Color, Rectangle
from kivy.base import EventLoop
from kivy.clock import Clock
from services.arena_themes import get_theme
from services.match_settings import MatchSettings
from services.team_store import TeamStore
from screens.arena_layers import ArenaLayers
from screens.match_effects import MatchEffects
from screens.match_screen import MatchScreen
from screens.router import AppRouter
from engine.match_engine import MatchEngine


@pytest.fixture(scope='module', autouse=True)
def graphics():
    EventLoop.ensure_window()


@pytest.mark.parametrize('theme,period', [('fire_arena', 18), ('electric_blue', 12), ('rainbow_neon', 60)])
def test_rotation_period_and_fps_consistency(theme, period):
    style = get_theme(theme)
    assert 360/abs(style.layers[0].rotation_degrees) == period
    outcomes = []
    e = MatchEngine()
    for fps in (30, 60, 120):
        with Fbo(size=(64, 64)):
            layers = ArenaLayers(style.layers)
        for _ in range(3*fps):
            layers.advance(1/fps)
        layers.layout(e.goal, lambda x, y: (x, y))
        outcomes.append((list(layers.loaded[0][1].vertices), layers.layer_colors[0].a))
        layers.advance(period)
        layers.layout(e.goal, lambda x, y: (x, y))
        assert list(layers.loaded[0][1].vertices) == pytest.approx(outcomes[-1][0], abs=1e-3)
    for vertices, alpha in outcomes[1:]:
        assert vertices == pytest.approx(outcomes[0][0], abs=1e-3)
        assert alpha == pytest.approx(outcomes[0][1])


def test_electric_blue_flashes_and_particles_are_local_bounded_and_expire():
    with Fbo(size=(64, 64)):
        effects = MatchEffects(get_theme('electric_blue').effects)
    e = MatchEngine(seed=42)
    e.state = 'playing'
    before = [vars(d).copy() for d in e.disks], e.random.getstate(), vars(e.goal).copy()
    observed_particles, observed_flashes = False, False
    born_times = set()
    for _ in range(10*120):
        effects.update(e, 1/120)
        effects.draw(lambda x, y: (x, y), 1)
        observed_particles |= bool(effects.particles)
        observed_flashes |= bool(effects.flashes)
        born_times.update(f[0] for f in effects.flashes)
        assert len(effects.particles) <= 48 and len(effects.flashes) <= 8
        assert all(effects.time-born < .16 for born, _, _ in effects.flashes)
        assert all(color.a <= .55 for color, _ in effects.flash_pool)
        assert all(shape.size[0] < 55 for color, shape in effects.flash_pool if color.a > 0)
    assert observed_particles and observed_flashes
    intervals = [b-a for a, b in zip(sorted(born_times), sorted(born_times)[1:])]
    assert max(intervals)-min(intervals) > .05
    assert before == ([vars(d) for d in e.disks], e.random.getstate(), vars(e.goal))
    e.state = 'finished'
    effects.update(e, .3)
    effects.draw(lambda x, y: (x, y), 1)
    assert effects.idle


@pytest.mark.parametrize('theme', ['fire_arena', 'electric_blue', 'rainbow_neon'])
def test_turning_texture_keeps_gpu_goal_gap_and_physical_center(theme):
    fbo = Fbo(size=(256, 256))
    with fbo:
        Color(.1, .2, .3, 1)
        Rectangle(size=(256, 256))
        layers = ArenaLayers(get_theme(theme).layers)
    e = MatchEngine(goal_speed_degrees=180)
    before_radius = e.arena.radius
    for elapsed in (.3, 1.2, 2.7):
        layers.advance(elapsed)
        e.goal.update(.13)
        layers.layout(e.goal, lambda x, y: (128+x*.2, 128+y*.2))
        fbo.draw()
        for offset in (-.12, 0, .12):
            angle = e.goal.angle+offset
            x, y = round(128+80*cos(angle)), round(128+80*sin(angle))
            start = (y*256+x)*4
            assert list(fbo.pixels[start:start+3]) == pytest.approx([25.5, 51, 76.5], abs=2)
        assert e.arena.radius == before_radius


@pytest.mark.parametrize('theme', ['fire_arena', 'electric_blue', 'rainbow_neon'])
def test_finished_view_stops_visual_work_and_restart_resumes(theme):
    settings = MatchSettings({'id': 'h', 'name': 'Home', 'logo': ''},
                             {'id': 'a', 'name': 'Away', 'logo': ''}, theme=theme)
    view = MatchScreen(settings=settings, size=(450, 800))
    try:
        view._first_frame = False
        view.engine.state = 'playing'
        view.update(.1)
        assert view.arena_layers.time > 0
        view.engine.state = 'finished'
        layer_time, ring_time = view.arena_layers.time, view.ring.time
        for _ in range(40):
            view.update(.1)
        assert view.arena_layers.time == layer_time and view.ring.time == ring_time
        assert not view.clock_event.is_triggered
        calls = []
        original = view.arena_layers.layout
        view.arena_layers.layout = lambda *args: calls.append(True)
        view.update(.1)
        assert calls == []
        view.arena_layers.layout = original
        view.restart_match()
        assert view.clock_event.is_triggered
        view.update(.01)
        view.update(.1)
        assert view.arena_layers.time > layer_time
        assert view.radius == pytest.approx(450*.37) and view.center_arena == (225, 392)
    finally:
        view.dispose()


def test_theme_replacement_cancels_old_animation_clock(tmp_path):
    router = AppRouter(TeamStore(tmp_path), None)
    teams = ({'id': 'h', 'name': 'Home', 'logo': ''}, {'id': 'a', 'name': 'Away', 'logo': ''})
    try:
        router.start_match(MatchSettings(*teams, theme='fire_arena'))
        old = router.match_view
        old.update(.1)
        time = old.arena_layers.time
        router.start_match(MatchSettings(*teams, theme='electric_blue'))
        for _ in range(3):
            Clock.tick()
        old.update(1.)
        assert old.arena_layers.time == time and not old.clock_event.is_triggered
        assert router.match_view is not old
    finally:
        router.dispose()
