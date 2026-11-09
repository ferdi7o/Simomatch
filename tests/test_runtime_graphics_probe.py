"""Controlled component matrix on Windows GL; not an Adreno reproduction."""
from dataclasses import replace
import gc
import json
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.graphics import Fbo, Mesh, RenderContext, ClearColor, ClearBuffers
from kivy.graphics.texture import Texture
from kivy.uix.image import Image
from services.graphics_probe import GraphicsProbeSettings, GraphicsSelection, plan_for
from services.arena_gpu_probe import ArenaProbe
from services.arena_themes import SpriteLayer, get_theme
from services.match_settings import MatchSettings
from services.team_store import TeamStore
from screens.match_screen import MatchScreen
from screens.router import AppRouter
from screens.graphics_probe_panel import open_probe_panel
from screens.graphics_probe_view import ProbeImage, QuietEffects, check_texture


@pytest.fixture(autouse=True)
def graphics(): EventLoop.ensure_window()


def settings(theme):
    return MatchSettings(dict(id='h',name='Home',logo=''),dict(id='a',name='Away',logo=''),theme=theme)


def test_probe_file_is_independent_atomic_and_survives_restart(tmp_path):
    teams = tmp_path/'teams.json'
    teams.write_bytes(b'original user teams')
    probe = GraphicsProbeSettings(tmp_path)
    assert probe.selection('fire_arena') == GraphicsSelection()
    assert not probe.path.exists()  # Merely opening setup never writes defaults.
    probe.save('fire_arena',1,'texture'); probe.save('electric_blue',3,'custom')
    reloaded = GraphicsProbeSettings(tmp_path)
    assert reloaded.selection('fire_arena') == GraphicsSelection(1,'texture')
    assert reloaded.selection('electric_blue') == GraphicsSelection(3,'custom')
    reloaded.save('fire_arena',None)
    assert GraphicsProbeSettings(tmp_path).selection('fire_arena').mode is None
    assert reloaded.selection('electric_blue').mode == 3
    assert teams.read_bytes() == b'original user teams'
    assert not list(tmp_path.glob('.graphics_probe_*.tmp'))


def test_failed_atomic_save_retains_previous_selection(tmp_path,monkeypatch):
    probe = GraphicsProbeSettings(tmp_path)
    probe.save('fire_arena',0)
    original = probe.path.read_bytes()
    def fail(*_): raise OSError('disk full')
    monkeypatch.setattr(Path,'replace',fail)
    with pytest.raises(OSError): probe.save('fire_arena',3)
    assert probe.selection('fire_arena').mode == 0 and probe.path.read_bytes() == original
    assert not list(tmp_path.glob('.graphics_probe_*.tmp'))


@pytest.mark.parametrize('contents',['bad','[]','{"fire_arena":null}',
    '{"fire_arena":{"mode":true}}','{"fire_arena":{"mode":5}}'])
def test_malformed_preferences_do_not_enable_an_unintended_mode(tmp_path,contents):
    (tmp_path/'graphics_probe.json').write_text(contents,encoding='utf8')
    assert GraphicsProbeSettings(tmp_path).selection('fire_arena') == GraphicsSelection()


@pytest.mark.parametrize('theme',['fire_arena','electric_blue'])
@pytest.mark.parametrize('mode',range(5))
def test_each_mode_constructs_only_its_declared_components_and_renders(theme,mode,monkeypatch,caplog):
    import screens.match_screen as module
    # These stale switches must not accidentally turn a requested FULL into BASE.
    monkeypatch.setattr(module,'read_arena_probe',lambda:ArenaProbe(raster=False,fire=False,electric=False))
    view = MatchScreen(settings=settings(theme),graphics_selection=GraphicsSelection(mode,'texture'),size=(450,800))
    try:
        plan = view.graphics_plan
        assert plan.active and plan.mode == mode
        assert bool(view.probe_image and view.probe_image.shape) == (mode in (1,3))
        assert len(view.arena_layers.loaded) == int(mode in (2,4))
        effect = view.fire_particles or view.electric_effects
        assert bool(effect) == (mode in (3,4))
        assert isinstance(view.effects,QuietEffects) == (mode < 4)
        if effect:
            assert effect.texture_batch is not None and not isinstance(effect.canvas,RenderContext)
        assert view.center_arena == (225,392) and view.radius == 450*.37
        view.engine.countdown = 0
        view.engine.state = 'playing'
        for _ in range(3): view.update(1/60)
        refs = [id(t) for t in view.arena_layers.source_textures]
        texture = view.probe_image.texture if view.probe_image else None
        gc.collect()
        assert refs == [id(t) for t in view.arena_layers.source_textures]
        if texture: assert view.probe_image.texture is texture
        fbo = Fbo(size=(450,800))
        fbo.add(view.canvas)
        try: fbo.draw()
        finally: fbo.remove(view.canvas)
        assert f'GRAPHICS_PROBE' in caplog.text
        assert 'GRAPHICS_CANVAS_GPU_ENTER' in caplog.text and 'GRAPHICS_CANVAS_GPU_EXIT' in caplog.text
        if mode in (1,2,3,4): assert 'GRAPHICS_IMAGE_READY' in caplog.text
        if mode in (1,3): assert 'GRAPHICS_IMAGE_GPU_ENTER' in caplog.text
        if mode in (2,4): assert 'RASTER_GPU_ENTER' in caplog.text
        if mode in (3,4): assert 'GRAPHICS_EFFECT_READY' in caplog.text
        # FBO draws are not a real Window flip; verify the existing flip callback
        # boundary separately without claiming Android frame presentation.
        view._log_first_present()
        assert 'GRAPHICS_FIRST_FRAME' in caplog.text
    finally: view.dispose()
    assert not view.clock_event.is_triggered and view._first_present is None


@pytest.mark.parametrize('theme',['neon_purple','rainbow_neon'])
def test_working_themes_ignore_probe_modes_and_renderer_overrides(theme):
    original = MatchScreen(settings=settings(theme),size=(450,800))
    probe = MatchScreen(settings=settings(theme),graphics_selection=GraphicsSelection(0,'custom'),size=(450,800))
    try:
        assert not probe.graphics_plan.active and not probe.probe_image
        assert probe.theme is original.theme
        assert probe.radius == original.radius and probe.center_arena == original.center_arena
        assert len(probe.arena_layers.loaded) == len(original.arena_layers.loaded)
        assert type(probe.effects) == type(original.effects)
    finally:
        original.dispose(); probe.dispose()


def test_reduced_modes_do_not_construct_particle_meshes_or_rendercontexts(monkeypatch):
    import screens.match_screen as module
    def forbidden(*args,**kwargs): raise AssertionError('Disabled component was constructed')
    monkeypatch.setattr(module,'FireParticles',forbidden)
    monkeypatch.setattr(module,'ElectricEffects',forbidden)
    for theme in ('fire_arena','electric_blue'):
        for mode in (0,1,2):
            view = MatchScreen(settings=settings(theme),graphics_selection=GraphicsSelection(mode))
            view.dispose()


@pytest.mark.parametrize('theme',['fire_arena','electric_blue'])
@pytest.mark.parametrize('mode',[0,1])
def test_base_and_image_only_never_create_extra_mesh_or_custom_shader(theme,mode,monkeypatch,caplog):
    import screens.arena_layers as raster
    import screens.fire_particles as fire
    import screens.electric_effects as electric
    calls = []
    def forbidden(*args,**kwargs):
        calls.append(True)
        raise AssertionError('Forbidden extra GPU component')
    for module in (raster,fire,electric):
        monkeypatch.setattr(module,'Mesh',forbidden)
    for module in (fire,electric):
        monkeypatch.setattr(module,'RenderContext',forbidden)
    view = MatchScreen(settings=settings(theme),graphics_selection=GraphicsSelection(mode,'custom'))
    try:
        assert not calls
        assert not view.arena_layers.loaded and not view.fire_particles and not view.electric_effects
        assert not view.gpu_probe.raster and not view.gpu_probe.fire and not view.gpu_probe.electric
        assert not view.gpu_probe.custom_shader
        line = next(line for line in caplog.text.splitlines() if 'ARENA_GPU_PROBE' in line)
        assert 'source=runtime' in line and f'mode={mode}' in line
        assert 'raster=False fire=False electric=False custom_shader=False' in line
        if mode == 0:
            assert view.probe_image is None
        else:
            assert isinstance(view.probe_image.widget,Image)
            assert view.probe_image.widget.texture is view.probe_image.texture
            assert list(view.canvas.children).count(view.probe_image.widget.canvas) == 1
            assert 'renderer=KivyImage' in caplog.text
    finally: view.dispose()


@pytest.mark.parametrize('renderer',['auto','custom','texture','flat_probe'])
@pytest.mark.parametrize('theme',['fire_arena','electric_blue'])
def test_effect_renderer_is_selectable_without_changing_component_matrix(theme,renderer):
    view = MatchScreen(settings=settings(theme),graphics_selection=GraphicsSelection(3,renderer))
    try:
        effect = view.fire_particles or view.electric_effects
        assert view.probe_image and not view.arena_layers.loaded
        if renderer == 'texture': assert effect.texture_batch is not None
        elif renderer == 'flat_probe': assert not effect.custom_shader and effect.texture_batch is None
        elif renderer == 'custom': assert effect.custom_shader and isinstance(effect.canvas,RenderContext)
    finally: view.dispose()


def test_png_reference_preserves_source_aspect_and_physical_center():
    texture = Texture.create(size=(200,100))
    definition = SpriteLayer('injected.png',source_radius_pixels=40,source_center_pixels=(80,60))
    fbo = Fbo(size=(256,256))
    with fbo:
        image = ProbeImage(definition,'fire_arena',1,loader=lambda _:texture)
    goal = SimpleNamespace(radius=40)
    image.layout(goal,lambda x,y:(120+x,140+y))
    assert tuple(image.shape.size) == (200,100)
    assert tuple(image.shape.pos) == (40,100)
    # Calibrated source center maps to exactly (120,140).
    assert image.shape.pos[0]+80 == 120 and image.shape.pos[1]+100-60 == 140
    assert image.shape.texture is texture and image.texture is texture


def test_standard_kivy_image_actually_draws_the_texture_without_raster_mesh():
    texture = Texture.create(size=(4,4))
    texture.blit_buffer(bytes([255,0,0,255])*16,colorfmt='rgba',bufferfmt='ubyte')
    image = ProbeImage(SpriteLayer('injected.png',source_radius_pixels=2,source_center_pixels=(2,2)),
                       'fire_arena',1,loader=lambda _:texture)
    image.layout(SimpleNamespace(radius=16),lambda x,y:(32+x,32+y))
    Clock.tick()
    Builder.sync()  # Real Window rendering flushes lazy KV bindings too.
    fbo = Fbo(size=(64,64),with_stencilbuffer=True)
    with fbo:
        ClearColor(0,0,0,1); ClearBuffers()
    fbo.add(image.widget.canvas)
    fbo.draw()
    index = (32*64+32)*4
    assert fbo.pixels[index] > 200 and fbo.pixels[index+1] < 5
    fbo.remove(image.widget.canvas)


@pytest.mark.parametrize('texture',[None,SimpleNamespace(size=(0,100)),
    SimpleNamespace(size=(float('inf'),100)),SimpleNamespace(size=(10,10),tex_coords=[float('nan')]*8)])
def test_missing_or_bad_image_is_rejected_without_a_draw_instruction(texture,caplog):
    fbo = Fbo(size=(64,64))
    with fbo:
        image = ProbeImage(SpriteLayer('missing.png'),'fire_arena',1,loader=lambda _:texture)
    assert image.shape is None
    assert 'GRAPHICS_IMAGE_REJECTED' in caplog.text
    fbo.draw()


def test_probe_view_rejects_worker_graphics_access_before_writes(caplog):
    view = MatchScreen(settings=settings('electric_blue'),graphics_selection=GraphicsSelection(1))
    errors = []
    def worker():
        for method in (view.draw_scene,view.layout_scene,lambda:view.update(.1),view.dispose):
            try: method()
            except RuntimeError: errors.append(True)
    try:
        thread = Thread(target=worker); thread.start(); thread.join()
        assert len(errors) == 4 and not view._disposed
        assert 'GRAPHICS_THREAD_REJECTED' in caplog.text
    finally: view.dispose()


def test_ui_changes_modes_between_matches_without_rebuilding_and_closes_dialog(tmp_path):
    router = AppRouter(TeamStore(tmp_path),None)
    try:
        setup = router.get_screen('setup')
        setup.theme.text = 'fire_arena'
        open_probe_panel(setup)
        setup.probe_mode_buttons[1].dispatch('on_release')
        assert setup.graphics_probe.selection('fire_arena').mode == 1
        router.start_match(settings('fire_arena'))
        old = router.match_view
        assert old.graphics_plan.mode == 1 and old.probe_image
        router.go('setup')
        open_probe_panel(setup)
        setup.probe_mode_buttons[3].dispatch('on_release')
        router.start_match(settings('fire_arena'))
        assert old._disposed and not old.clock_event.is_triggered
        assert router.match_view.graphics_plan.mode == 3 and router.match_view.fire_particles
        assert not router.match_view.arena_layers.loaded
        router.go('setup')
        setup.theme.text = 'electric_blue'
        assert setup.graphics_probe.selection('electric_blue').mode is None
        open_probe_panel(setup)
        router.go('menu')
        assert setup.probe_dialog is None
    finally: router.dispose()


def test_ui_effect_path_is_saved_with_mode_and_can_restore_production(tmp_path):
    router = AppRouter(TeamStore(tmp_path),None)
    try:
        setup = router.get_screen('setup')
        setup.theme.text = 'electric_blue'
        open_probe_panel(setup)
        setup.probe_renderer_button.dispatch('on_release')  # auto -> texture
        setup.probe_mode_buttons[3].dispatch('on_release')
        assert GraphicsProbeSettings(setup.graphics_probe.path.parent).selection('electric_blue') == GraphicsSelection(3,'texture')
        router.start_match(settings('electric_blue'))
        assert router.match_view.electric_effects.texture_batch is not None
        router.go('setup')
        setup.graphics_probe.save('electric_blue',None)
        router.start_match(settings('electric_blue'))
        assert not router.match_view.graphics_plan.active
        assert router.match_view.arena_layers.loaded and router.match_view.electric_effects
    finally: router.dispose()


@pytest.mark.parametrize('size',[(320,640),(450,800),(720,1280),(1080,1920)])
def test_probe_control_remains_scroll_accessible_and_selected_png_tracks_resize(tmp_path,size):
    router = AppRouter(TeamStore(tmp_path),None,size=size)
    try:
        setup = router.get_screen('setup')
        setup.size = size; setup.theme.text = 'fire_arena'
        for _ in range(3): Clock.tick()
        assert setup.graphics_probe_button.parent is setup.content
        assert not setup.graphics_probe_button.disabled and setup.graphics_probe_button.height > 0
        view = MatchScreen(settings=settings('fire_arena'),graphics_selection=GraphicsSelection(1),size=size)
        try:
            assert view.radius == pytest.approx(size[0]*.37)
            assert view.probe_image.shape.size[0]/view.probe_image.shape.size[1] == pytest.approx(
                view.probe_image.texture.width/view.probe_image.texture.height)
            view.size = (size[0]*.9,size[1]*.9)
            assert view.radius == pytest.approx(size[0]*.9*.37)
        finally: view.dispose()
    finally: router.dispose()
