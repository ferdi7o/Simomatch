from dataclasses import replace
from math import radians, pi, cos, sin, atan2, hypot
import pytest
from kivy.graphics import Fbo
from services.match_settings import MatchSettings
from services.arena_themes import THEMES, SpriteLayer
from services.team_store import TeamStore
from engine.match_engine import MatchEngine
from screens.router import AppRouter
from screens.arena_layers import ArenaLayers
from screens.match_visuals import NeonRing
from config import FIXED_DT, MAX_SPEED


def settings(speed=90, theme='neon_purple', **kwargs):
    return MatchSettings({'id': 'h', 'name': 'Home', 'logo': ''},
                         {'id': 'a', 'name': 'Away', 'logo': ''},
                         theme=theme, goal_speed_degrees=speed, **kwargs)


@pytest.mark.parametrize('speed', [30, 90, 180])
def test_speed_degrees_transfer_rotation_and_restart(tmp_path, speed):
    root = AppRouter(TeamStore(tmp_path), None)
    try:
        a, b = root.store.save('Home'), root.store.save('Away')
        root.go('setup')
        form = root.get_screen('setup')
        assert (form.goal_speed_slider.min, form.goal_speed_slider.max, form.goal_speed_slider.value) == (30, 180, 90)
        form.spinners[0].text, form.spinners[1].text = a['name'], b['name']
        form.goal_speed_slider.value = speed
        form.start_match()
        e = root.match_view.engine
        assert root.current == 'match'
        assert e.goal.angular_speed == pytest.approx(-radians(speed))
        e.state = 'playing'
        initial = e.goal.angle
        e.advance(.1)
        assert e.goal.angle == pytest.approx((initial-radians(speed)*.1) % (2*pi))
        e.restart()
        assert e.goal.angular_speed == pytest.approx(-radians(speed))
    finally:
        root.dispose()


@pytest.mark.parametrize('speed', [0, 29, 181, float('inf'), float('nan')])
def test_speed_range_is_validated_in_model_and_engine(speed):
    with pytest.raises(ValueError):
        settings(speed)
    with pytest.raises(ValueError):
        MatchEngine(goal_speed_degrees=speed)


@pytest.mark.parametrize('angle', [0, pi/2, pi, 3*pi/2])
@pytest.mark.parametrize('radius', [60, 80])
def test_clear_passage_at_180_degrees_scores_once(angle, radius):
    e = MatchEngine(seed=10, radii=(radius, 60), goal_speed_degrees=180)
    e.state = 'playing'
    e.goal.angle = angle
    def rotate(x, y):
        return x*cos(angle)-y*sin(angle), x*sin(angle)+y*cos(angle)
    scorer, other = e.disks
    # Aim through where the fast clockwise-moving opening will actually be.
    scorer.x, scorer.y = rotate(320, -45)
    scorer.vx, scorer.vy = rotate(1000, -600)
    other.x, other.y = rotate(-160, -200)
    other.vx, other.vy = rotate(0, -880)
    for _ in range(40):
        e.advance(FIXED_DT)
        if e.goals:
            break
    assert e.scores['FB'] == len(e.goals) == 1
    assert (scorer.x, scorer.y) == (0, 0)
    assert e.last_substeps >= 10
    e.advance(FIXED_DT)
    assert len(e.goals) == 1


@pytest.mark.parametrize('speed', [90, 180])
@pytest.mark.parametrize('radius', [18, 60, 80])
def test_fast_rotating_post_detects_collision_without_goal(speed, radius):
    e = MatchEngine(seed=2, radii=(radius, 60), goal_speed_degrees=speed)
    e.state = 'playing'
    e.goal.angle = 0
    d, other = e.disks
    x, y = e.goal.posts[0]
    d.x, d.y, d.vx, d.vy = x-radius-e.goal.post_radius-3, y, MAX_SPEED, 0
    other.x, other.y = 0, -200
    e.advance(FIXED_DT*3)
    assert e.post_hits > 0 and d.vx < 0
    assert not e.goals and d.speed <= MAX_SPEED+1e-6


def test_decorative_phase_is_independent_from_goal_speed():
    fbo = Fbo(size=(64, 64))
    with fbo:
        a, b = NeonRing(), NeonRing()
    slow, fast = MatchEngine(goal_speed_degrees=30), MatchEngine(goal_speed_degrees=180)
    slow.state = fast.state = 'playing'
    for _ in range(60):
        slow.advance(1/60)
        fast.advance(1/60)
        a.advance(1/60)
        b.advance(1/60)
        a.layout(slow.goal, lambda x, y: (x, y), 1)
        b.layout(fast.goal, lambda x, y: (x, y), 1)
    assert slow.goal.angle != pytest.approx(fast.goal.angle)
    assert a.phase == pytest.approx(b.phase)
    assert a.color_at(.3) == pytest.approx(b.color_at(.3))


def test_missing_corrupt_and_invalid_effect_assets_are_safe(tmp_path):
    (tmp_path/'broken.webp').write_bytes(b'invalid')
    with Fbo(size=(64, 64)):
        missing = ArenaLayers((SpriteLayer('missing.png'), SpriteLayer('broken.webp'),
                               SpriteLayer('invalid.png', columns=0)), root=tmp_path)
    assert missing.loaded == [] and len(missing.missing_assets) == 3
    missing.advance(1)
    missing.layout(MatchEngine().goal, lambda x, y: (x, y))


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280)])
def test_sprite_atlas_preloads_animates_and_preserves_gap(png_file, size):
    fbo = Fbo(size=(64, 64))
    calls = []
    from services.media import load_texture
    def load(path):
        calls.append(path)
        return load_texture(path)
    with fbo:
        layers = ArenaLayers((SpriteLayer(str(png_file), columns=2, frames=2, fps=10),), loader=load)
    assert len(layers.loaded) == 1
    e = MatchEngine(goal_speed_degrees=180)
    scale = size[0]*.37/e.arena.radius
    project = lambda x, y: (size[0]/2+x*scale, size[1]*.49+y*scale)
    definition, mesh, frames = layers.loaded[0]
    count = len(fbo.children)
    for _ in range(15):
        layers.advance(.01)
        e.goal.update(.01)
        layers.layout(e.goal, project)
    assert mesh.texture is frames[1]
    assert len(calls) == 1 and len(fbo.children) == count
    vertices = mesh.vertices
    for index in range(0, len(vertices), 4):
        x, y = (vertices[index]-size[0]/2)/scale, (vertices[index+1]-size[1]*.49)/scale
        angle = atan2(y, x)
        offset = (angle-e.goal.angle+pi) % (2*pi)-pi
        assert abs(offset) >= e.goal.half_angle-1e-5
        assert hypot(x, y)/e.arena.radius == pytest.approx(definition.inner_scale if index % 8 == 0 else definition.outer_scale)


def test_effect_layers_are_bounded_and_theme_physics_unchanged(png_file):
    with Fbo(size=(64, 64)):
        layers = ArenaLayers((SpriteLayer(str(png_file)),)*20)
    assert len(layers.loaded) == layers.MAX_LAYERS == 3
    assert all(len(theme.layers) <= layers.MAX_LAYERS for theme in THEMES.values())


def test_neon_background_priority_and_custom_override(tmp_path, png_file, monkeypatch):
    import screens.match_screen as module
    original = THEMES['neon_purple']
    missing = tmp_path/'background1.png'
    theme = replace(original, background_image=str(missing), background_fallbacks=(str(png_file),))
    monkeypatch.setitem(THEMES, 'neon_purple', theme)
    from services.media import load_texture
    calls = []
    def load(path):
        calls.append(str(path))
        return load_texture(path)
    monkeypatch.setattr(module, 'load_texture', load)
    view = module.MatchScreen(settings=settings())
    try:
        assert calls == [str(missing), str(png_file)]
        assert view.background_texture is not None
    finally:
        view.dispose()
    calls.clear()
    view = module.MatchScreen(settings=settings(background=str(png_file)))
    try:
        assert calls == [str(png_file)]
        assert view.background_texture is not None
    finally:
        view.dispose()


def test_oversized_atlas_is_rejected_without_building_mesh():
    from types import SimpleNamespace
    texture = SimpleNamespace(size=(8192, 8192), width=8192, height=8192)
    with Fbo(size=(64, 64)):
        layer = ArenaLayers((SpriteLayer('large.png'),), loader=lambda path: texture)
    assert not layer.loaded and layer.diagnostics
