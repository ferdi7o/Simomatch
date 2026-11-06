import math
import pytest
from engine.physics import Disk, collide_disks
from engine.arena import Arena
from engine.goal import Goal
from engine.match_engine import MatchEngine
from config import MIN_SPEED, MAX_SPEED


def test_elastic_collision_preserves_momentum_and_energy():
    a = Disk('FB', -29, 0, 250, 40)
    b = Disk('GS', 29, 0, -180, -20, mass=2)
    momentum = a.mass*a.vx + b.mass*b.vx
    energy = a.mass*a.speed**2 + b.mass*b.speed**2
    assert collide_disks(a, b)
    assert a.mass*a.vx+b.mass*b.vx == pytest.approx(momentum)
    assert a.mass*a.speed**2+b.mass*b.speed**2 == pytest.approx(energy)
    assert b.x-a.x >= a.radius+b.radius
    assert a.vy == 40 and b.vy == -20


def test_separating_disks_do_not_bounce_again():
    a, b = Disk('FB', -20, 0, -200, 0), Disk('GS', 20, 0, 200, 0)
    collide_disks(a, b)
    assert (a.vx, b.vx) == (-200, 200)


def test_coincident_centers_are_resolved():
    a, b = Disk('FB', 0, 0, 200, 0), Disk('GS', 0, 0, -200, 0)
    collide_disks(a, b)
    assert math.hypot(a.x-b.x, a.y-b.y) >= a.radius+b.radius


def test_wall_reflects_outward_normal_only():
    disk = Disk('FB', -375, 0, -250, 40)
    assert Arena().resolve(disk, Goal(angle=0)) == 'wall'
    assert (disk.x, disk.vx, disk.vy) == (-(Arena.radius-disk.radius), 250, 40)


@pytest.mark.parametrize('velocity', [0, 20, 600])
def test_speed_limits(velocity):
    disk = Disk('FB', 0, 0, velocity, 0)
    disk.limit_speed()
    assert MIN_SPEED <= disk.speed <= MAX_SPEED


def test_render_rates_produce_identical_match():
    engines = []
    for fps in (30, 60, 120):
        e = MatchEngine(seed=42)
        for _ in range(60*fps):
            e.advance(1/fps)
        engines.append(e)
    for e in engines[1:]:
        assert e.scores == engines[0].scores
        assert e.goals == engines[0].goals
        for disk, reference in zip(e.disks, engines[0].disks):
            assert (disk.x, disk.y, disk.vx, disk.vy) == pytest.approx(
                (reference.x, reference.y, reference.vx, reference.vy))
    assert engines[0].state == 'finished'


def test_countdown_finish_and_restart():
    e = MatchEngine(seed=1, duration=1)
    start = [(d.x, d.y) for d in e.disks]
    e.advance(2)
    assert [(d.x, d.y) for d in e.disks] == start
    e.advance(2)
    assert e.state == 'finished' and e.minute == 90
    end = [(d.x, d.y) for d in e.disks]
    e.advance(3.1)
    assert e.can_restart
    assert [(d.x, d.y) for d in e.disks] == end
    e.restart()
    assert e.state == 'countdown' and e.scores == {'FB': 0, 'GS': 0}


@pytest.mark.parametrize('seed', range(10))
def test_complete_matches_have_finite_bounded_disks(seed):
    e = MatchEngine(seed=seed)
    for _ in range(60*120):
        e.advance(1/120)
        for d in e.disks:
            assert all(math.isfinite(v) for v in (d.x, d.y, d.vx, d.vy))
            # A disk can leave the circular wall through the real goal mouth.
            assert math.hypot(d.x, d.y) < e.arena.radius+d.radius+2
            assert MIN_SPEED-1e-8 <= d.speed <= MAX_SPEED+1e-8
    assert e.state == 'finished'
    assert sum(e.scores.values()) == len(e.goals)
