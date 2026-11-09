import gc
from dataclasses import replace
import pytest
from kivy.base import EventLoop
from kivy.graphics import Fbo, Color, Rectangle
from services.arena_gpu_probe import ArenaProbe, read_arena_probe
from services.match_settings import MatchSettings
from services.arena_themes import get_theme
from screens.match_screen import MatchScreen
from screens.arena_layers import ArenaLayers
from screens.fire_particles import FireParticles
from screens.electric_effects import ElectricEffects
from screens.mesh_safety import validate_mesh
from engine.match_engine import MatchEngine


@pytest.fixture(autouse=True)
def graphics(): EventLoop.ensure_window()


@pytest.mark.parametrize('theme', ['fire_arena','electric_blue','rainbow_neon'])
@pytest.mark.parametrize('probe', [ArenaProbe(raster=False), ArenaProbe(fire=False,electric=False),
                                 ArenaProbe(custom_shader=False), ArenaProbe(trace=True)])
def test_independent_shared_layer_and_shader_probes_preserve_match_geometry(monkeypatch, theme, probe):
    import screens.match_screen as module
    monkeypatch.setattr(module,'read_arena_probe',lambda:probe)
    view = MatchScreen(settings=MatchSettings(dict(id='h',name='H',logo=''),dict(id='a',name='A',logo=''),theme=theme),size=(450,800))
    try:
        assert view.center_arena == (225,392) and view.radius == 450*.37
        assert len(view.arena_layers.loaded) == int(probe.raster)
        assert bool(view.fire_particles) == (theme == 'fire_arena' and probe.fire)
        assert bool(view.electric_effects) == (theme == 'electric_blue' and probe.electric)
        for effect in (view.fire_particles,view.electric_effects):
            if effect:
                assert effect.custom_shader == probe.custom_shader
                assert validate_mesh(effect.mesh.vertices,effect.mesh.indices,6 if probe.custom_shader else 4) > 0
    finally: view.dispose()


@pytest.mark.parametrize('kind',[FireParticles,ElectricEffects])
@pytest.mark.parametrize('custom',[True,False])
def test_shader_and_stock_probe_draw_real_clipped_particle_geometry(kind,custom):
    effect = kind(custom_shader=custom,trace=True)
    fbo = Fbo(size=(256,256))
    with fbo:
        Color(0,0,0,1); Rectangle(size=(256,256))
    fbo.add(effect.canvas)
    engine = MatchEngine()
    effect.update(engine,.1)
    effect.draw(engine.goal,lambda x,y:(128+x*.2,128+y*.2))
    gc.collect()
    fbo.draw()
    assert max(fbo.pixels[0::4]) > 20 or max(fbo.pixels[2::4]) > 20
    effect.clear()
    assert not effect.mesh.vertices


def test_raster_texture_owner_survives_collection_and_trace_brackets_draw(caplog):
    fbo = Fbo(size=(256,256))
    with fbo:
        layers = ArenaLayers(get_theme('rainbow_neon').layers,trace=True)
    layers.layout(MatchEngine().goal,lambda x,y:(128+x*.2,128+y*.2))
    assert layers.source_textures
    gc.collect()
    fbo.draw()
    assert 'RASTER_GPU_ENTER' in caplog.text and 'RASTER_GPU_EXIT' in caplog.text
    assert caplog.text.index('RASTER_GPU_ENTER') < caplog.text.index('RASTER_GPU_EXIT')


def test_bad_or_absent_diagnostic_config_preserves_all_normal_visuals(tmp_path):
    path = tmp_path/'probe.json'
    assert read_arena_probe(path) == ArenaProbe()
    for text in ('bad','[]','{"raster":"false"}'):
        path.write_text(text,encoding='utf8')
        assert read_arena_probe(path) == ArenaProbe()
    path.write_text('{"raster":false,"trace":true}',encoding='utf8')
    assert read_arena_probe(path) == replace(ArenaProbe(),raster=False,trace=True)
