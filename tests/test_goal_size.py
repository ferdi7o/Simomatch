from math import cos, sin, pi, hypot, radians
import pytest
from kivy.base import EventLoop
from kivy.graphics import Fbo, Color, Rectangle
from config import ARENA_RADIUS, GOAL_HALF_ANGLE, FIXED_DT, MAX_SPEED
from engine.goal import Goal
from engine.arena import Arena
from engine.physics import Disk
from engine.match_engine import MatchEngine
from services.match_settings import MatchSettings
from services.team_store import TeamStore
from services.arena_themes import get_theme
from screens.router import AppRouter
from screens.arena_layers import ArenaLayers
from screens.match_screen import MatchScreen
from screens.fire_particles import FireParticles
from screens.electric_effects import ElectricEffects


@pytest.fixture(scope='module', autouse=True)
def graphics():
    EventLoop.ensure_window()


@pytest.mark.parametrize('percent', [60, 100, 150])
def test_chord_width_inset_rotation_and_post_collision(percent):
    goal = Goal.sized(percent, angle=0, angular_speed=0)
    p, q = goal.posts
    assert hypot(p[0]-q[0], p[1]-q[1]) == pytest.approx(2*ARENA_RADIUS*sin(GOAL_HALF_ANGLE)*percent/100)
    assert hypot(*p) == pytest.approx(ARENA_RADIUS*.97)
    disk = Disk('A', p[0]-18-goal.post_radius+1, p[1], MAX_SPEED, 0, radius=18)
    assert Arena().resolve(disk, goal) == 'post'
    assert disk.vx < 0 and not goal.fully_crossed(disk)
    center = Disk('A', goal.line_distance+18-.01, 0, MAX_SPEED, 0, radius=18)
    assert Arena().resolve(center, goal) == 'opening'
    assert not goal.fully_crossed(center)
    center.x += .02
    assert goal.fully_crossed(center)
    goal.angular_speed = -pi
    goal.update(.3)
    assert goal.size_percent == percent
    assert hypot(*goal.posts[0]) == pytest.approx(ARENA_RADIUS*.97)
    assert hypot(goal.posts[0][0]-goal.posts[1][0], goal.posts[0][1]-goal.posts[1][1]) == pytest.approx(hypot(p[0]-q[0], p[1]-q[1]))


@pytest.mark.parametrize('percent', [60, 100, 150])
@pytest.mark.parametrize('speed', [30, 180])
def test_fast_rotating_goal_scores_once_and_preserves_opponent(percent, speed):
    engine = MatchEngine(seed=3, goal_size_percent=percent, goal_speed_degrees=speed,
                         radii=(18, 18), cards_enabled=False)
    engine.state = 'playing'
    engine.goal.angle = 0
    direction = -radians(speed)*.06
    scorer, other = engine.disks
    scorer.x, scorer.y = 320*cos(direction), 320*sin(direction)
    scorer.vx, scorer.vy = MAX_SPEED*cos(direction), MAX_SPEED*sin(direction)
    other.x, other.y, other.vx, other.vy = -180, -180, 0, 880
    for _ in range(24):
        before = vars(other).copy()
        engine.advance(FIXED_DT)
        if engine.goals:
            assert (other.x, other.y, other.vx, other.vy) == pytest.approx(
                (before['x']+before['vx']*FIXED_DT, before['y']+before['vy']*FIXED_DT,
                 before['vx'], before['vy']))
            break
    assert len(engine.goals) == engine.scores['FB'] == 1
    assert (scorer.x, scorer.y) == (0, 0)
    engine.advance(FIXED_DT)
    assert len(engine.goals) == 1
    engine.restart()
    assert engine.goal.size_percent == percent
    assert engine.goal.angular_speed == pytest.approx(-radians(speed))


@pytest.mark.parametrize('percent', [59, 151, float('inf'), float('nan')])
def test_invalid_size_is_rejected(percent):
    with pytest.raises(ValueError):
        MatchEngine(goal_size_percent=percent)
    with pytest.raises(ValueError):
        MatchSettings({'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}, goal_size_percent=percent)


@pytest.mark.parametrize('percent', [60, 100, 150])
def test_setup_slider_transfer_and_order(tmp_path, percent):
    root = AppRouter(TeamStore(tmp_path), None)
    try:
        a, b = root.store.save('Home'), root.store.save('Away')
        root.go('setup')
        form = root.get_screen('setup')
        assert (form.goal_size_slider.min, form.goal_size_slider.max, form.goal_size_slider.value) == (60, 150, 100)
        order = list(reversed(form.content.children))
        assert order.index(form.goal_size_label) == order.index(form.goal_speed_slider)+1
        form.spinners[0].text, form.spinners[1].text = a['name'], b['name']
        form.goal_speed_slider.value = 180
        form.goal_size_slider.value = percent
        assert form.goal_size_label.text.endswith(f'%{percent}')
        form.start_match()
        assert root.current == 'match'
        assert root.match_view.engine.goal.size_percent == percent
        assert root.match_view.engine.goal.angular_speed == pytest.approx(-pi)
    finally:
        root.dispose()


@pytest.mark.parametrize('percent', [60, 100, 150])
@pytest.mark.parametrize('theme', ['fire_arena', 'electric_blue', 'rainbow_neon'])
def test_raster_gap_tracks_resized_rotating_goal_on_gpu(percent, theme):
    goal = Goal.sized(percent)
    effect = FireParticles() if theme == 'fire_arena' else ElectricEffects() if theme == 'electric_blue' else None
    fbo = Fbo(size=(256, 256))
    with fbo:
        Color(.04, .06, .08, 1)
        Rectangle(size=(256, 256))
        layers = ArenaLayers(get_theme(theme).layers)
    assert layers.loaded
    if effect:
        fbo.add(effect.canvas)
        engine = MatchEngine(goal_size_percent=percent)
        engine.state = 'playing'
        effect.update(engine, .15)
    for angle in (0, pi/2, 3.8):
        goal.angle = angle
        layers.layout(goal, lambda x, y: (128+x*.2, 128+y*.2))
        if effect:
            effect.draw(goal, lambda x, y: (128+x*.2, 128+y*.2))
        fbo.ask_update()
        fbo.draw()
        pixels = fbo.pixels
        assert sum(pixels[i+2] > 60 or pixels[i] > 60 for i in range(0, len(pixels), 4)) > 100
        for offset in (-goal.half_angle*.65, 0, goal.half_angle*.65):
            for radius in (380, 410, 450, 490):
                x, y = round(128+radius*.2*cos(angle+offset)), round(128+radius*.2*sin(angle+offset))
                index = (y*256+x)*4
                assert list(pixels[index:index+3]) == pytest.approx([10.2, 15.3, 20.4], abs=2)


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280)])
@pytest.mark.parametrize('percent', [60, 100, 150])
def test_goal_draw_matches_physics_without_moving_arena(size, percent):
    settings = MatchSettings({'id': 'a', 'name': 'A', 'logo': ''},
                             {'id': 'b', 'name': 'B', 'logo': ''}, goal_size_percent=percent)
    view = MatchScreen(settings=settings, size=size)
    try:
        assert view.radius == min(size[0]*.37, size[1]*.30)
        assert view.center_arena == (size[0]/2, size[1]*.49)
        for angle in (0, pi/2, 3.8):
            view.engine.goal.angle = angle
            view.draw_scene()
            p, q = view.engine.goal.posts
            assert view.goal_frame.points[:2] == pytest.approx(view.project(*p))
            assert view.goal_frame.points[-2:] == pytest.approx(view.project(*q))
            for shape, point in zip(view.posts, (p, q)):
                assert (shape.pos[0]+shape.size[0]/2, shape.pos[1]+shape.size[1]/2) == pytest.approx(view.project(*point))
    finally:
        view.dispose()
