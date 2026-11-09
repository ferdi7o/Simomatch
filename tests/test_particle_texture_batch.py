from threading import Thread
import gc
import pytest
from kivy.base import EventLoop
from kivy.graphics import Fbo, Color, Rectangle, RenderContext
from engine.match_engine import MatchEngine
from screens.particle_texture_batch import ParticleTextureBatch
from screens.fire_particles import FireParticles
from screens.electric_effects import ElectricEffects
from screens.mesh_safety import validate_mesh
from services.arena_gpu_probe import ArenaProbe, particle_renderer, read_arena_probe


@pytest.fixture(autouse=True)
def graphics(): EventLoop.ensure_window()


def test_android_auto_and_independent_explicit_renderers():
    probe = ArenaProbe()
    assert particle_renderer(probe,'fire','android') == 'texture'
    assert particle_renderer(probe,'electric','android') == 'texture'
    assert particle_renderer(probe,'fire','win') == 'custom'
    assert particle_renderer(ArenaProbe(fire_renderer='custom'),'fire','android') == 'custom'
    assert particle_renderer(ArenaProbe(fire_renderer='texture'),'fire','win') == 'texture'
    assert particle_renderer(ArenaProbe(custom_shader=False),'electric','android') == 'flat_probe'


@pytest.mark.parametrize('kind',[FireParticles,ElectricEffects])
def test_texture_path_never_constructs_custom_rendercontext(kind,monkeypatch):
    import screens.fire_particles as fire
    import screens.electric_effects as electric
    def forbidden(*_,**__): raise AssertionError('Custom GL path must not execute')
    monkeypatch.setattr(fire,'RenderContext',forbidden)
    monkeypatch.setattr(electric,'RenderContext',forbidden)
    effect = kind(renderer='texture')
    assert not isinstance(effect.canvas,RenderContext)
    engine = MatchEngine()
    effect.update(engine,.1); effect.draw(engine.goal,lambda x,y:(x,y))
    assert validate_mesh(effect.mesh.vertices,effect.mesh.indices,4) > 0
    assert effect.texture_batch.texture.size == (128,128)


def draw(kind,renderer,angle=0,seconds=.1):
    effect = kind(renderer=renderer)
    fbo = Fbo(size=(256,256))
    with fbo:
        Color(.04,.06,.08,1); Rectangle(size=(256,256))
    fbo.add(effect.canvas)
    engine = MatchEngine(seed=7)
    engine.goal.angle = angle
    effect.update(engine,seconds)
    effect.draw(engine.goal,lambda x,y:(128+x*.2,128+y*.2))
    fbo.draw()
    return effect,fbo


@pytest.mark.parametrize('kind',[FireParticles,ElectricEffects])
@pytest.mark.parametrize('angle',[0,.7,2.3])
def test_stock_texture_output_matches_existing_vertex_colors_and_goal_gap(kind,angle):
    original,reference = draw(kind,'custom',angle)
    compatible,result = draw(kind,'texture',angle)
    a,b = reference.pixels,result.pixels
    differences = [abs(x-y) for x,y in zip(a,b)]
    assert sum(differences)/len(differences) < .15
    # Eight-bit color interpolation should differ only slightly; triangles
    # split for valid affine tiles may produce tiny edge-rasterization changes.
    assert sum(value > 12 for value in differences) < 30
    assert max(b[2::4]) > 20 or max(b[0::4]) > 20


def test_arbitrary_three_color_triangle_subdivides_without_changing_geometry():
    batch = ParticleTextureBatch('test')
    vertices = [0,0,1,0,0,1, 10,0,0,1,0,.5, 0,10,0,0,1,0]
    assert batch.upload(vertices,[0,1,2])
    assert len(batch.mesh.indices) == 12  # Four exact subtriangles.
    area = 0
    v = batch.mesh.vertices
    for i in range(0,len(v),12):
        ax,ay,bx,by,cx,cy = v[i],v[i+1],v[i+4],v[i+5],v[i+8],v[i+9]
        area += abs((bx-ax)*(cy-ay)-(by-ay)*(cx-ax))*.5
    assert area == pytest.approx(50)


def test_invalid_batch_keeps_last_mesh_and_reload_palette():
    batch = ParticleTextureBatch('test')
    valid = [0,0,1,.5,0,.5, 10,0,1,.5,0,.5, 0,10,1,.5,0,0]
    assert batch.upload(valid,[0,1,2])
    old = list(batch.mesh.vertices),list(batch.mesh.indices),batch.active
    palette = bytes(batch.buffers[batch.active][2])
    valid[0] = float('nan')
    assert not batch.upload(valid,[0,1,2])
    assert (list(batch.mesh.vertices),list(batch.mesh.indices),batch.active) == old
    assert bytes(batch.buffers[batch.active][2]) == palette
    batch._reload(batch.texture)
    assert bytes(batch.texture.pixels) == palette


def test_reload_and_worker_thread_never_touch_gl_outside_owner():
    batch = ParticleTextureBatch('test')
    errors = []
    def worker():
        for call in (batch.clear,lambda:batch._reload(batch.texture)):
            try: call()
            except RuntimeError as error: errors.append(str(error))
    thread = Thread(target=worker); thread.start(); thread.join()
    assert len(errors) == 2


@pytest.mark.parametrize('kind',[FireParticles,ElectricEffects])
def test_texture_objects_and_buffers_are_reused_through_animation_and_clear(kind):
    effect = kind(renderer='texture')
    engine = MatchEngine()
    identities = id(effect.canvas),id(effect.mesh),id(effect.texture_batch.texture)
    buffers = tuple(id(pixels) for _,_,pixels in effect.texture_batch.buffers)
    for _ in range(90):
        effect.update(engine,1/30)
        effect.draw(engine.goal,lambda x,y:(x,y))
        assert not effect.guard.last_error
    assert identities == (id(effect.canvas),id(effect.mesh),id(effect.texture_batch.texture))
    assert buffers == tuple(id(pixels) for _,_,pixels in effect.texture_batch.buffers)
    gc.collect()
    effect.clear()
    assert not effect.mesh.indices


def test_renderer_configuration_does_not_disable_other_theme(tmp_path):
    path = tmp_path/'probe.json'
    path.write_text('{"fire_renderer":"texture","electric_renderer":"custom"}',encoding='utf8')
    probe = read_arena_probe(path)
    assert particle_renderer(probe,'fire','win') == 'texture'
    assert particle_renderer(probe,'electric','android') == 'custom'
