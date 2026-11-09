"""Application invariants, not an Adreno driver reproduction."""
from threading import Thread, get_ident
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from kivy.graphics import Fbo
from kivy.graphics.texture import Texture
from screens.arena_layers import ArenaLayers
from screens.match_screen import MatchScreen
from screens.router import AppRouter
from services.arena_themes import SpriteLayer
from services.match_settings import MatchSettings
from services.team_store import TeamStore
from engine.match_engine import MatchEngine


@pytest.fixture(autouse=True)
def graphics():
    EventLoop.ensure_window()


def settings(theme='rainbow_neon', recording=False):
    return MatchSettings(dict(id='h', name='Home', logo=''), dict(id='a', name='Away', logo=''),
                         theme=theme, record_video=recording)


def test_raster_mesh_has_valid_topology_before_first_layout_and_draw():
    fbo = Fbo(size=(32,32))
    with fbo:
        layers = ArenaLayers((SpriteLayer('injected.png'),),
                             loader=lambda _:Texture.create(size=(4,4)))
    mesh = layers.loaded[0][1]
    assert len(mesh.indices) == 0  # Previously 576 indices with zero vertices.
    fbo.draw()
    layers.layout(MatchEngine().goal, lambda x,y:(x,y))
    assert len(mesh.indices) == 576
    assert max(mesh.indices) < len(mesh.vertices)//4
    fbo.ask_update(); fbo.draw()


@pytest.mark.parametrize('theme', ['rainbow_neon','fire_arena','electric_blue'])
def test_disposed_arena_cannot_be_rebuilt_by_resize_or_pending_updates(theme):
    view = MatchScreen(settings=settings(theme), size=(450,800))
    view.update(0)
    view.dispose()
    assert view._first_present is None and not view.clock_event.is_triggered
    initial = [list(mesh.vertices) for _, mesh, _ in view.arena_layers.loaded]
    calls = []
    original = view.draw_scene
    view.draw_scene = lambda: calls.append(True)
    view.size = (320,640)
    view.pos = (12,12)
    view.layout_scene()
    view.set_safe_insets((0,30,0,0))
    view.update(2)
    for _ in range(3): Clock.tick()
    assert not calls
    view.draw_scene = original
    view.draw_scene()
    assert initial == [list(mesh.vertices) for _, mesh, _ in view.arena_layers.loaded]
    for effect in (view.fire_particles, view.electric_effects):
        if effect:
            assert not effect.mesh.vertices and not effect.mesh.indices
    view.dispose()  # Idempotent resource cleanup.


def test_recording_off_never_constructs_android_adapter(tmp_path, monkeypatch, caplog):
    import services.video_recording as recording
    def forbidden(): raise AssertionError('Android capture must stay disabled')
    monkeypatch.setattr(recording, 'AndroidCapture', forbidden)
    router = AppRouter(TeamStore(tmp_path), None)
    router.video.platform = 'android'
    try:
        router.start_match(settings())
        assert router.current == 'match' and router.video.backend is None
        assert router.match_view.recording is None and router.video.state == 'idle'
        assert 'MATCH_START_REQUESTED' in caplog.text
        assert 'ARENA_CANVAS_READY' in caplog.text
        assert 'RECORDING_PERMISSION_REQUESTED' not in caplog.text
    finally:
        router.dispose()


def test_worker_start_request_is_marshaled_before_graphics_creation(tmp_path, monkeypatch):
    import screens.router as module
    owner, created = get_ident(), []
    original = module.MatchScreen
    def construct(*args, **kwargs):
        created.append(get_ident())
        assert get_ident() == owner
        return original(*args, **kwargs)
    router = AppRouter(TeamStore(tmp_path), None)
    monkeypatch.setattr(module, 'MatchScreen', construct)
    try:
        worker = Thread(target=lambda: router.start_match(settings()))
        worker.start(); worker.join()
        assert not created and router.match_view is None
        for _ in range(3): Clock.tick()
        assert created == [owner] and router.current == 'match'
    finally:
        router.dispose()


def test_three_theme_replacements_keep_separate_canvases_and_cancel_old_clocks(tmp_path):
    router = AppRouter(TeamStore(tmp_path), None)
    views = []
    try:
        for theme in ('rainbow_neon','fire_arena','electric_blue'):
            router.start_match(settings(theme))
            views.append(router.match_view)
            for _ in range(3): Clock.tick()
        assert len({id(v.canvas) for v in views}) == 3
        assert all(v._disposed and not v.clock_event.is_triggered for v in views[:-1])
        assert not views[-1]._disposed
        views[-1].engine.state = 'finished'
        views[-1].announcements.reset()
        views[-1].draw_scene()
        assert views[-1].result_panel.opacity == 1
    finally:
        router.dispose()


def test_dispose_cancels_worker_request_before_it_creates_a_canvas(tmp_path):
    router = AppRouter(TeamStore(tmp_path), None)
    worker = Thread(target=lambda: router.start_match(settings()))
    worker.start(); worker.join()
    pending = list(router._dispatch_events)
    assert pending
    router.dispose()
    for _ in range(3): Clock.tick()
    assert router.match_view is None and not router._dispatch_events
    assert all(not event.is_triggered for event in pending)
