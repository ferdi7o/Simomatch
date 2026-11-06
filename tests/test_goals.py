from math import pi
import pytest
from engine.physics import Disk
from engine.goal import Goal
from engine.arena import Arena
from engine.match_engine import MatchEngine
from config import FIXED_DT, START_SPEED_MIN, START_SPEED_MAX


@pytest.mark.parametrize('angle', [0, pi/2, pi, -pi/2])
def test_coordinates_follow_rotating_goal(angle):
    from math import cos, sin
    g = Goal(angle=angle)
    d = Disk('FB', 470*cos(angle), 470*sin(angle), 0, 0)
    assert g.local(d) == pytest.approx((470, 0), abs=1e-10)
    assert g.fully_crossed(d)


def test_opening_has_no_wall_and_requires_entire_disk():
    g = Goal(angle=0)
    d = Disk('FB', 390, 0, 250, 0)
    assert Arena().resolve(d, g) == 'opening'
    assert not g.fully_crossed(d)
    d.x = g.line_distance + d.radius - .01
    assert not g.fully_crossed(d)
    d.x += .02
    assert g.fully_crossed(d)


def test_post_is_separate_from_goal():
    g = Goal(angle=0, angular_speed=0)
    x, y = g.posts[0]
    d = Disk('FB', x-32, y, 250, 0)
    assert Arena().resolve(d, g) == 'post'
    assert d.vx < 0
    assert not g.fully_crossed(d)


def test_outside_opening_still_bounces():
    d = Disk('GS', 330, 220, 250, 0)
    assert Arena().resolve(d, Goal(angle=0)) == 'wall'
    assert not Goal(angle=0).fully_crossed(d)


def test_scoring_once_respawns_scorer_and_records_team_minute():
    e = MatchEngine(seed=10)
    e.state = 'playing'
    e.goal = Goal(angle=0, angular_speed=0)
    e.disks[0].x = e.goal.line_distance + e.disks[0].radius + 1
    e.disks[0].y = 0
    e.disks[0].vx, e.disks[0].vy = 250, 0
    other = e.disks[1]
    expected = (other.x + other.vx*FIXED_DT, other.y + other.vy*FIXED_DT, other.vx, other.vy)
    e.step(FIXED_DT)
    assert e.scores == {'FB': 1, 'GS': 0}
    assert e.goals == [('FB', 1)]
    assert e.flash > 0
    assert (e.disks[0].x, e.disks[0].y) == (0, 0)
    assert (other.x, other.y, other.vx, other.vy) == pytest.approx(expected)
    e.step(FIXED_DT)
    assert e.scores['FB'] == 1


def test_clockwise_rotation():
    g = Goal(angle=1)
    g.update(.1)
    assert g.angle < 1


def test_post_contact_does_not_increment_score():
    e = MatchEngine(seed=3)
    e.state = 'playing'
    e.goal = Goal(angle=0, angular_speed=0)
    x, y = e.goal.posts[0]
    d = e.disks[1]
    d.x, d.y, d.vx, d.vy = x-32, y, 250, 0
    e.step(FIXED_DT)
    assert e.post_hits == 1
    assert not e.goals
    assert e.scores == {'FB': 0, 'GS': 0}


@pytest.mark.parametrize('other_position', [(0, 0), (20, 10), (-45, 0), (200, 150)])
def test_respawn_avoids_center_opponent_without_changing_it(other_position):
    from math import hypot
    e = MatchEngine(seed=5, radii=(48, 42))
    scorer, other = e.disks
    other.x, other.y = other_position
    snapshot = vars(other).copy()
    e.respawn(scorer)
    assert vars(other) == snapshot
    assert hypot(scorer.x-other.x, scorer.y-other.y) >= scorer.radius+other.radius
    assert hypot(scorer.x, scorer.y)+scorer.radius < e.arena.radius
    assert START_SPEED_MIN <= scorer.speed <= START_SPEED_MAX
    if other_position == (200, 150):
        assert (scorer.x, scorer.y) == (0, 0)


def test_opening_has_no_invisible_wall_before_post_contact():
    # Overlaps the circular radius, but neither physical post. A diagonal
    # inward tangent velocity carries it safely between the posts.
    g = Goal(angle=0, angular_speed=0)
    d = Disk('FB', 338, 50, 1000, -400, radius=60)
    from math import hypot
    assert all(hypot(d.x-x, d.y-y) > d.radius+g.post_radius for x, y in g.posts)
    before = vars(d).copy()
    assert Arena().resolve(d, g) == 'opening'
    assert vars(d) == before


@pytest.mark.parametrize('angle', [0, pi/3, pi/2, pi, 3*pi/2])
@pytest.mark.parametrize('angular_speed', [-.48, 0, .48])
@pytest.mark.parametrize('radius', [60, 80])
def test_diagonal_clear_passage_scores_at_current_rotating_angle(angle, angular_speed, radius):
    from math import cos, sin
    e = MatchEngine(seed=10, radii=(radius, 60))
    e.state = 'playing'
    e.goal = Goal(angle=angle, angular_speed=angular_speed)
    def rotate(x, y):
        return x*cos(angle)-y*sin(angle), x*sin(angle)+y*cos(angle)
    scorer, other = e.disks
    scorer.x, scorer.y = rotate(338, 50) if radius == 60 else rotate(320, 30)
    scorer.vx, scorer.vy = rotate(1000, -400)
    other.x, other.y = rotate(-160, -200)
    other.vx, other.vy = rotate(0, -880)
    for _ in range(30):
        e.advance(FIXED_DT)
        if e.goals:
            break
    assert e.scores['FB'] == 1
    assert len(e.goals) == 1
    assert (scorer.x, scorer.y) == (0, 0)
    e.advance(FIXED_DT)
    assert e.scores['FB'] == 1


@pytest.mark.parametrize('angle', [0, pi/2, pi, 3*pi/2])
@pytest.mark.parametrize('angular_speed', [-.48, .48])
@pytest.mark.parametrize('radius', [60, 80])
def test_max_speed_center_pass_scores_once_with_rotating_goal(angle, angular_speed, radius):
    from math import cos, sin
    from config import MAX_SPEED
    e = MatchEngine(seed=2, radii=(radius, 60))
    e.state = 'playing'
    e.goal = Goal(angle=angle, angular_speed=angular_speed)
    c, s = cos(angle), sin(angle)
    scorer, other = e.disks
    scorer.x, scorer.y = 320*c, 320*s
    scorer.vx, scorer.vy = MAX_SPEED*c, MAX_SPEED*s
    other.x, other.y = -160*c+200*s, -160*s-200*c
    other.vx, other.vy = 880*s, -880*c
    for _ in range(20):
        before = vars(other).copy()
        e.advance(FIXED_DT)
        if e.goals:
            assert other.x == pytest.approx(before['x']+before['vx']*FIXED_DT)
            assert other.y == pytest.approx(before['y']+before['vy']*FIXED_DT)
            assert (other.vx, other.vy) == pytest.approx((before['vx'], before['vy']))
            break
    assert e.scores['FB'] == len(e.goals) == 1
    assert (scorer.x, scorer.y) == (0, 0)
    e.advance(FIXED_DT)
    assert len(e.goals) == 1
