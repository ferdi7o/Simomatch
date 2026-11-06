import pytest
from kivy.graphics import Fbo
from kivy.graphics.texture import Texture
from engine.match_engine import MatchEngine
from screens.match_visuals import LogoDrawing, NeonRing
from screens.match_effects import MatchEffects


def test_transparent_logo_alpha_and_aspect_are_preserved():
    texture = Texture.create(size=(8, 4), colorfmt='rgba')
    row = bytes([255, 0, 0, 0])*4 + bytes([255, 0, 0, 255])*4
    texture.blit_buffer(row*4, colorfmt='rgba', bufferfmt='ubyte')
    texture.mag_filter = texture.min_filter = 'nearest'
    fbo = Fbo(size=(64, 64), with_stencilbuffer=True)
    with fbo:
        logo = LogoDrawing(texture, (.2, .3, .8))
    logo.layout(32, 32, 24)
    fbo.draw()
    pixels = fbo.pixels
    alpha = lambda x, y: pixels[(y*64+x)*4+3]
    assert alpha(20, 32) == 0  # Transparent source remains transparent.
    assert alpha(44, 32) == 255
    assert alpha(4, 32) == 0  # No backing circle or border outside the logo.
    assert logo.image.size[0]/logo.image.size[1] == 2


def test_effect_pools_are_bounded_fade_and_do_not_change_physics():
    fbo = Fbo(size=(64, 64))
    with fbo:
        effects = MatchEffects()
    e = MatchEngine(seed=44)
    e.state = 'playing'
    for _ in range(200):
        e.emit('disk', 0, 0)
    before = (e.random.getstate(), [vars(d).copy() for d in e.disks], list(e.events))
    instruction_count = len(fbo.children)
    effects.update(e, .02)
    effects.draw(lambda x, y: (x, y), 1)
    assert len(effects.particles) == 48 and len(effects.flashes) == 8
    assert (e.random.getstate(), [vars(d).copy() for d in e.disks], list(e.events)) == before
    for _ in range(100):
        effects.update(e, 1/120)
        effects.draw(lambda x, y: (x, y), 1)
    assert len(fbo.children) == instruction_count
    assert all(len(t) <= 16 for t in effects.trails)
    e.state = 'finished'
    effects.update(e, .5)
    effects.draw(lambda x, y: (x, y), 1)
    assert not effects.particles and not effects.flashes and not any(effects.trails)
    assert all(color.a == 0 for color, _ in effects.particle_pool+effects.flash_pool)


def test_neon_ring_ends_match_the_physical_posts():
    fbo = Fbo(size=(64, 64))
    with fbo:
        ring = NeonRing()
    e = MatchEngine()
    ring.layout(e.goal, lambda x, y: (x, y), 1)
    p, q = e.goal.posts
    assert ring.segments[0][0].points[:2] == pytest.approx(q)
    assert ring.segments[-1][0].points[-2:] == pytest.approx(p)


def test_respawn_and_restart_clear_trails():
    fbo = Fbo(size=(64, 64))
    with fbo:
        effects = MatchEffects()
    e = MatchEngine(seed=4)
    e.state = 'playing'
    effects.update(e, .02)
    e.disks[0].x += 10
    effects.update(e, .02)
    assert len(effects.trails[0]) == 2
    e.respawn(e.disks[0])
    effects.update(e, .02)
    assert len(effects.trails[0]) == 1
    e.restart()
    effects.update(e, .02)
    assert not any(effects.trails)
