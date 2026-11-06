"""Large disks and speed caps with motion resolved inside each fixed tick."""
from math import hypot
import pytest
from config import MAX_SPEED, MIN_SPEED, DISK_RADIUS, FIXED_DT, START_SPEED_MIN, START_SPEED_MAX
from engine.match_engine import MatchEngine
from engine.goal import Goal


def active(radii):
    engine = MatchEngine(seed=14, radii=radii)
    engine.state = 'playing'
    engine.goal = Goal(angle=0, angular_speed=0)
    engine.disks[1].x, engine.disks[1].y = 0, -200
    return engine


@pytest.mark.parametrize('radius', [18, 60, 80])
def test_fast_wall_cannot_be_crossed(radius):
    e = active((radius, radius))
    d = e.disks[0]
    d.x, d.y, d.vx, d.vy = -400+radius+3, 0, -MAX_SPEED, 0
    e.step(1/30)
    assert e.last_substeps > 2
    assert d.vx > 0
    assert hypot(d.x, d.y)+radius <= 400+1e-6
    assert any(event[1] == 'wall' for event in e.events)


@pytest.mark.parametrize('radius', [18, 60, 80])
@pytest.mark.parametrize('angular_speed', [-.48, 0, .48])
def test_fast_post_contact_is_not_a_goal(radius, angular_speed):
    e = active((radius, radius))
    e.goal.angular_speed = angular_speed
    x, y = e.goal.posts[0]
    d = e.disks[0]
    d.x, d.y = x-radius-e.goal.post_radius-3, y
    d.vx, d.vy = MAX_SPEED, 0
    e.step(1/30)
    assert e.post_hits > 0
    assert d.vx < 0
    assert not e.goals


@pytest.mark.parametrize('radius', [18, 60, 80])
def test_large_fast_disk_can_still_score_through_opening(radius):
    e = active((radius, radius))
    d, other = e.disks
    d.x, d.y, d.vx, d.vy = 200, 0, MAX_SPEED, 0
    other.x, other.y, other.vx, other.vy = -150, -200, 0, -400
    e.advance(.45)
    assert e.scores[d.team] == 1
    assert len(e.goals) == 1


def test_large_disks_do_not_stick_against_wall():
    e = active((80, 80))
    a, b = e.disks
    # Use the solid side, away from the opening.
    a.x, b.x = -160, -320
    a.y = b.y = 0
    a.vx, a.vy, b.vx, b.vy = -680, 0, -340, 0
    e.advance(.15)
    assert hypot(a.x-b.x, a.y-b.y) >= a.radius+b.radius-1e-5
    assert a.vx > 0 and b.vx > 0


@pytest.mark.parametrize('radii', [(60, 60), (18, 80), (80, 80)])
def test_fast_disks_exchange_momentum_without_sticking(radii):
    e = active(radii)
    a, b = e.disks
    a.x, b.x = -radii[0]-3, radii[1]+3
    a.y = b.y = 0
    a.vx, a.vy, b.vx, b.vy = MAX_SPEED, 0, -MAX_SPEED, 0
    e.step(1/30)
    assert a.vx < 0 and b.vx > 0
    assert hypot(a.x-b.x, a.y-b.y) >= sum(radii)
    assert any(event[1] == 'disk' for event in e.events)


@pytest.mark.parametrize('scorer_index', [0, 1])
def test_large_scorer_respawns_and_opponent_keeps_trajectory(scorer_index):
    e = active((60, 80))
    scorer, other = e.disks[scorer_index], e.disks[1-scorer_index]
    scorer.x = e.goal.line_distance+scorer.radius+1
    scorer.y, scorer.vx, scorer.vy = 0, MAX_SPEED, 0
    other.x, other.y, other.vx, other.vy = -160, -100, 800, 200
    expected = (other.x+other.vx*FIXED_DT, other.y+other.vy*FIXED_DT, other.vx, other.vy)
    e.step(FIXED_DT)
    assert (scorer.x, scorer.y) == (0, 0)
    assert e.scores[scorer.team] == 1 and e.flash > 0
    assert (other.x, other.y, other.vx, other.vy) == pytest.approx(expected)
    e.step(FIXED_DT)
    assert e.scores[scorer.team] == 1


def test_new_defaults_speed_cap_and_randomness():
    a, b = MatchEngine(seed=1), MatchEngine(seed=2)
    assert a.radii == (DISK_RADIUS, DISK_RADIUS) == (60, 60)
    assert all(START_SPEED_MIN <= d.speed <= START_SPEED_MAX for d in a.disks)
    assert a.disks[0].vx != b.disks[0].vx
    a.state = 'playing'
    a.disks[0].vx = 1e6
    a.step(FIXED_DT)
    assert all(MIN_SPEED-1e-6 <= d.speed <= MAX_SPEED+1e-6 for d in a.disks)


@pytest.mark.parametrize('seed', range(3))
def test_maximum_disks_remain_bounded_for_complete_match(seed):
    e = MatchEngine(seed=seed, radii=(80, 80))
    for _ in range(60*120):
        e.advance(FIXED_DT)
        for disk in e.disks:
            assert hypot(disk.x, disk.y) < 482
            assert disk.speed <= MAX_SPEED+1e-6
    assert e.state == 'finished'
