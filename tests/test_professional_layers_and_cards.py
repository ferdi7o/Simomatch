"""Real PNG/GPU coverage checks and font-independent result card rows."""
from pathlib import Path
from math import sin, cos, pi, radians, hypot
import struct
import pytest
from kivy.graphics import Fbo, Color, Rectangle, RoundedRectangle
from kivy.clock import Clock
from kivy.core.image import Image
from services.arena_themes import get_theme
from services.match_settings import MatchSettings
from screens.arena_layers import ArenaLayers
from screens.match_screen import MatchScreen
from engine.match_engine import MatchEngine
from engine.cards import CardEvent

ROOT = Path(__file__).resolve().parents[1]
THEMES = ('fire_arena', 'electric_blue', 'rainbow_neon')


@pytest.fixture(scope='module', autouse=True)
def graphics_context():
    from kivy.base import EventLoop
    EventLoop.ensure_window()


@pytest.mark.parametrize('theme', THEMES)
def test_rgba_asset_mapping_and_transparent_source_calibration(theme):
    style = get_theme(theme)
    definition = style.layers[0]
    path = ROOT / definition.image
    assert path == ROOT/'assets'/'arena_effects'/f'{theme}.png'
    raw = path.read_bytes()
    assert raw[:8] == b'\x89PNG\r\n\x1a\n' and raw[25] == 6
    width, height = struct.unpack('!II', raw[16:24])
    assert width == height == 1254
    image = Image(str(path), keep_data=True)
    assert image.read_pixel(626, 626)[3] == 0
    assert 400 < definition.source_radius_pixels < 520
    assert definition.frames == 1


@pytest.mark.parametrize('theme', THEMES)
@pytest.mark.parametrize('angle', [0, pi/2, pi, 3*pi/2])
def test_gpu_gap_keeps_original_background_while_closed_arc_draws(theme, angle):
    fbo = Fbo(size=(256, 256))
    background = (.12, .33, .21)
    with fbo:
        Color(*background, 1)
        Rectangle(pos=(0, 0), size=(256, 256))
        layers = ArenaLayers(get_theme(theme).layers)
    assert len(layers.loaded) == 1 and not layers.missing_assets
    engine = MatchEngine(goal_speed_degrees=180)
    engine.goal.angle = angle
    engine.goal.update(.037)
    angle = engine.goal.angle
    project = lambda x, y: (128+x*.20, 128+y*.20)
    layers.layout(engine.goal, project)
    fbo.draw()
    pixels = fbo.pixels
    def rgb(x, y):
        start = (round(y)*256+round(x))*4
        return pixels[start:start+3]
    # Sample the entire missing wedge, not only a fully transparent source hole.
    for scale in (.92, 1., 1.12):
        for offset in (-.15, 0, .15):
            x, y = project(engine.arena.radius*scale*cos(angle+offset),
                           engine.arena.radius*scale*sin(angle+offset))
            assert list(rgb(x, y)) == pytest.approx([v*255 for v in background], abs=2)
    # On the other side there must be actual PNG color, not just empty geometry.
    contrast = []
    for offset in (-.12, 0, .12):
        for scale in (.94, 1., 1.06):
            x, y = project(engine.arena.radius*scale*cos(angle+pi+offset),
                           engine.arena.radius*scale*sin(angle+pi+offset))
            contrast.append(sum(abs(p-v*255) for p, v in zip(rgb(x, y), background)))
    assert max(contrast) > 70


@pytest.mark.parametrize('theme', THEMES)
def test_calibrated_uv_uses_uniform_pixel_scale_and_independent_animation(theme):
    with Fbo(size=(64, 64)):
        layers = ArenaLayers(get_theme(theme).layers)
    e = MatchEngine(goal_speed_degrees=180)
    layers.advance(.4)
    layers.layout(e.goal, lambda x, y: (x, y))
    definition, mesh, frames = layers.loaded[0]
    texture = frames[0]
    # UV at the first outer vertex corresponds to exactly the calibrated
    # source radius times the same visual scale on both axes.
    x, y, tu, tv = mesh.vertices[4:8]
    uv = texture.tex_coords
    u = (tu-uv[0])/(uv[2]-uv[0])
    v = (tv-uv[1])/(uv[7]-uv[1])
    center_x, center_y = definition.source_center_pixels
    dx = u*texture.width-center_x
    dy = (1-v)*texture.height-center_y
    assert hypot(dx, dy) == pytest.approx(definition.source_radius_pixels*definition.outer_scale, rel=1e-5)
    assert hypot(x, y) == pytest.approx(e.arena.radius*definition.outer_scale, rel=1e-5)
    before = vars(e.goal).copy()
    layers.advance(.2)
    layers.layout(e.goal, lambda x, y: (x, y))
    assert vars(e.goal) == before


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280)])
def test_real_layers_and_canvas_card_rows_preserve_layout(size):
    settings = MatchSettings({'id': 'h', 'name': 'Ev sahibi', 'logo': ''},
                             {'id': 'a', 'name': 'Deplasman', 'logo': ''}, theme='fire_arena')
    view = MatchScreen(settings=settings, size=size)
    try:
        assert len(view.arena_layers.loaded) == 1
        assert view.center_arena == (size[0]/2, size[1]*.49)
        assert view.radius == pytest.approx(min(size[0]*.37, size[1]*.30))
        e = view.engine
        e.cards = [CardEvent('yellow_card', e.teams[0], 24), CardEvent('red_card', e.teams[1], 77)]
        e.state = 'finished'
        view.draw_scene()
        for _ in range(5):
            Clock.tick()
        rows = [row for column in view.result_panel.card_rows for row in column]
        assert [row.text.text for row in rows] == ["24' SARI", "77' KIRMIZI"]
        assert all(row.text.text.isascii() and not row.text.markup for row in rows)
        assert all(isinstance(row.icon, RoundedRectangle) and min(row.icon.size) > 0 for row in rows)
        assert rows[0].icon_color.rgba != rows[1].icon_color.rgba
        assert all(row.text.right <= row.right+1e-5 for row in rows)
        assert view.result_panel.goal_contents[0].height >= rows[0].height
        for scroll, content, label in zip(view.result_panel.goal_scrolls, view.result_panel.goal_contents,
                                          view.result_panel.goal_labels):
            assert scroll.viewport_size == pytest.approx(content.size)
            assert scroll.g_translate.y+label.top <= scroll.top+2
            assert scroll.g_translate.y+label.y >= scroll.y-2
    finally:
        view.dispose()


@pytest.mark.parametrize('theme', THEMES)
def test_missing_professional_image_uses_canvas_fallback(theme):
    with Fbo(size=(64, 64)):
        layer = ArenaLayers(get_theme(theme).layers, loader=lambda path: None)
    assert not layer.loaded and layer.missing_assets
    layer.advance(.2)
    layer.layout(MatchEngine().goal, lambda x, y: (x, y))
