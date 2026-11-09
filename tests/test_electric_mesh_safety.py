from threading import Thread
from types import SimpleNamespace
import pytest
from kivy.base import EventLoop
from kivy.graphics import Fbo, Color, Rectangle
from engine.match_engine import MatchEngine
from screens.electric_effects import ElectricEffects, electric_probe_mode
from screens.mesh_safety import MeshGuard, validate_mesh
from screens.match_screen import MatchScreen
from screens.arena_layers import ArenaLayers
from services.match_settings import MatchSettings


@pytest.fixture(autouse=True)
def graphics():
    EventLoop.ensure_window()


@pytest.mark.parametrize('vertices,indices,stride', [
    ([0.,0.], [0,0,0], 6),
    ([], [0,1,2], 6),
    ([0.]*18, [], 6),
    ([0.]*18, [0,1,3], 6),
    ([0.]*18, [-1,1,2], 6),
    ([0.]*18, [0,1.,2], 6),
    ([0.]*18, [0,1], 6),
    ([float('nan')]+[0.]*17, [0,1,2], 6),
    ([float('inf')]+[0.]*17, [0,1,2], 6),
    ([1e100]+[0.]*17, [0,1,2], 6),
    ([0.]*18, [0,1,2]*21846, 6),
])
def test_invalid_batches_never_touch_graphics(vertices, indices, stride):
    mesh = SimpleNamespace(vertices=[9.]*18, indices=[0,1,2])
    before = mesh.vertices[:], mesh.indices[:]
    guard = MeshGuard('test')
    with pytest.raises(ValueError): validate_mesh(vertices, indices, stride)
    assert not guard.upload(mesh, vertices, indices, stride)
    assert (mesh.vertices, mesh.indices) == before and guard.uploads == 0


def test_upload_clears_old_topology_before_changing_vertex_storage():
    states = []
    class Mesh:
        def __init__(self): self.vertices, self.indices = [0.]*24, [0,1,3]
        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if hasattr(self,'vertices') and hasattr(self,'indices'):
                states.append((len(self.vertices)//6, list(self.indices)))
    mesh = Mesh()
    states.clear()
    MeshGuard('test').upload(mesh, [0.]*18, [0,1,2], 6)
    assert states == [(4, []), (3, []), (3, [0,1,2])]


def test_non_owner_cannot_mutate_electric_or_raster_buffers():
    fx = ElectricEffects()
    layers = ArenaLayers()
    errors = []
    def worker():
        for operation in (fx.clear, lambda:fx.draw(MatchEngine().goal, lambda x,y:(x,y)),
                          lambda:layers.layout(MatchEngine().goal, lambda x,y:(x,y))):
            try: operation()
            except RuntimeError as error: errors.append(str(error))
    thread = Thread(target=worker)
    thread.start(); thread.join()
    assert len(errors) == 3 and all('owner thread' in e for e in errors)
    assert fx.guard.uploads == 0


def test_nan_projection_retains_last_valid_electric_batch():
    fx = ElectricEffects()
    goal = MatchEngine().goal
    fx.draw(goal, lambda x,y:(x,y))
    previous = list(fx.mesh.vertices), list(fx.mesh.indices)
    fx.draw(goal, lambda x,y:(float('nan'), y))
    assert (list(fx.mesh.vertices), list(fx.mesh.indices)) == previous
    assert 'Nonfinite' in fx.guard.last_error


@pytest.mark.parametrize('size', [(320,640), (450,800), (720,1280)])
def test_real_initial_and_animated_electric_batches_are_finite_and_in_range(size):
    view = MatchScreen(settings=MatchSettings(dict(id='h',name='Home',logo=''),dict(id='a',name='Away',logo=''),
                                             theme='electric_blue'), size=size)
    try:
        for frame in range(45):
            view.update(1/30)
            fx = view.electric_effects
            count = validate_mesh(fx.mesh.vertices, fx.mesh.indices, 6)
            assert count > 0 and fx.canvas.shader.success
            for _, mesh, textures in view.arena_layers.loaded:
                assert validate_mesh(mesh.vertices, mesh.indices, 4) == 194
                assert textures and mesh.texture in textures
    finally:
        view.dispose()


@pytest.mark.parametrize('mode', ['full','png_only','triangle','no_png','deferred'])
def test_probe_modes_preserve_physics_and_expected_drawing_order(monkeypatch, mode):
    import screens.match_screen as screen
    monkeypatch.setattr(screen, 'electric_probe_mode', lambda:mode)
    view = MatchScreen(settings=MatchSettings(dict(id='h',name='Home',logo=''),dict(id='a',name='Away',logo=''),
                                             theme='electric_blue'), size=(450,800))
    try:
        fx = view.electric_effects
        assert view.center_arena == (225,392) and view.radius == 450*.37
        assert fx is not None  # No permanent feature removal.
        assert len(view.arena_layers.loaded) == (0 if mode == 'no_png' else 1)
        if mode == 'png_only':
            assert fx.canvas not in view.canvas.children
        elif mode == 'deferred':
            assert fx.canvas not in view._electric_slot.children
            view._log_first_present()
            assert fx.canvas in view._electric_slot.children
            assert view.canvas.children.index(view._electric_slot) < view.canvas.children.index(view.goal_frame)
        else:
            assert view.canvas.children.index(fx.canvas) < view.canvas.children.index(view.goal_frame)
        if mode == 'triangle':
            assert len(fx.mesh.vertices) == 18 and list(fx.mesh.indices) == [0,1,2]
    finally:
        view.dispose()
    assert not fx.mesh.indices and view._first_present is None


def test_minimal_triangle_uses_real_shader_and_draws_pixels():
    fx = ElectricEffects('triangle')
    fbo = Fbo(size=(128,128))
    with fbo:
        Color(0,0,0,1)
        Rectangle(size=(128,128))
    fbo.add(fx.canvas)
    fx.draw(MatchEngine().goal, lambda x,y:(64+x*.1,64+y*.1))
    fbo.draw()
    assert max(fbo.pixels[2::4]) > 50


def test_probe_config_invalid_or_missing_never_disables_full_effects(tmp_path):
    path = tmp_path/'probe.json'
    assert electric_probe_mode(path) == 'full'
    for text in ('[]', 'broken', '{"mode":"bad"}'):
        path.write_text(text, encoding='utf8')
        assert electric_probe_mode(path) == 'full'
    path.write_text('{"mode":"triangle"}', encoding='utf8')
    assert electric_probe_mode(path) == 'triangle'
