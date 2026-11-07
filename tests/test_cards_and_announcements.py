import random
from math import hypot
import pytest
from kivy.clock import Clock
from engine.cards import CardEvent, create_card_schedule
from engine.match_engine import MatchEngine
from screens.match_screen import MatchScreen
from services.match_settings import MatchSettings
from config import FIXED_DT


def test_card_limits_spacing_random_teams_and_rare_red():
    yellow_counts, reds, teams = [], 0, set()
    for seed in range(1000):
        schedule = create_card_schedule(random.Random(seed), ('Home', 'Away'))
        yellow_counts.append(sum(c.kind == 'yellow_card' for c in schedule))
        red_count = sum(c.kind == 'red_card' for c in schedule)
        assert 0 <= yellow_counts[-1] <= 5 and red_count <= 1
        assert all(1 <= c.minute <= 90 for c in schedule)
        assert all(b.minute-a.minute >= 7 for a, b in zip(schedule, schedule[1:]))
        teams.update(c.team for c in schedule)
        reds += red_count
    assert min(yellow_counts) == 0 and max(yellow_counts) == 5
    assert teams == {'Home', 'Away'}
    assert .04 < reds/1000 < .12


def test_cards_record_exact_football_minute_once_and_restart_clears():
    e = MatchEngine(seed=12, duration=10)
    e.state = 'playing'
    e.card_schedule = [CardEvent('yellow_card', 'FB', 5), CardEvent('red_card', 'GS', 31),
                       CardEvent('yellow_card', 'GS', 80)]
    previous = 0
    while e.state == 'playing':
        e.advance(FIXED_DT)
        if len(e.cards) > previous:
            assert e.cards[-1].minute == e.minute
            previous = len(e.cards)
    assert e.cards == e.card_schedule
    events = [event for event in e.events if event[1] in ('yellow_card', 'red_card')]
    assert len(events) == 3
    e.advance(2)
    assert len(e.cards) == 3
    e.restart()
    assert not e.cards and e._next_card == 0


def test_cards_do_not_change_any_physics_or_goals():
    a, b = MatchEngine(seed=29), MatchEngine(seed=29, cards_enabled=False)
    for _ in range(60*60):
        a.advance(1/60)
        b.advance(1/60)
        assert [(d.x, d.y, d.vx, d.vy) for d in a.disks] == [(d.x, d.y, d.vx, d.vy) for d in b.disks]
    assert a.random.getstate() == b.random.getstate()
    assert a.goals == b.goals and a.scores == b.scores
    assert a.goal.angle == b.goal.angle
    assert not b.cards


def test_card_schedule_is_render_rate_independent():
    outcomes = []
    for fps in (30, 60, 120):
        e = MatchEngine(seed=17, duration=10)
        for _ in range(14*fps):
            e.advance(1/fps)
        outcomes.append(e.cards)
    assert outcomes[0] == outcomes[1] == outcomes[2]


@pytest.fixture
def view():
    settings = MatchSettings({'id': 'h', 'name': 'W'*40, 'logo': ''},
                             {'id': 'a', 'name': 'Away', 'logo': ''})
    view = MatchScreen(settings=settings, size=(450, 800))
    yield view
    view.dispose()


def test_goal_card_queue_grows_fades_and_keeps_close_goals(view):
    a, e = view.announcements, view.engine
    started = []
    a.on_start = lambda kind, team: started.append((kind, team))
    e.emit('goal', 0, 0, e.teams[0])
    e.emit('yellow_card', 0, 0, e.teams[1])
    e.emit('goal', 0, 0, e.teams[1])
    a.sync(e)
    a.advance(.05)
    small = a.text.font_size
    a.advance(.25)
    assert a.text.font_size > small and a.text.text == 'GOOL!'
    assert a.opacity == 1
    a.advance(1.3)
    assert 0 < a.opacity < 1
    a.advance(.21)
    assert a.active[0] == 'yellow_card' and a.text.text == e.teams[1]
    a.advance(1.5)
    assert a.active[0] == 'goal'
    a.advance(2)
    assert a.idle and a.opacity == 0
    assert [kind for kind, _ in started] == ['goal', 'yellow_card', 'goal']
    a.sync(e)
    assert a.idle  # Same engine events are never replayed.


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280)])
def test_announcements_hud_and_arena_geometry(view, size):
    view.size = size
    view.layout_scene()
    w, h = size
    assert view.center_arena == (w/2, h*.49)
    assert view.radius == pytest.approx(min(w*.37, h*.30))
    a, e = view.announcements, view.engine
    e.emit('goal', 0, 0, e.teams[0])
    a.sync(e)
    a.advance(.3)
    assert a.y > view.center_arena[1]+view.radius*1.25
    assert a.top < min(label.y for label in view.team_names)
    assert a.text.font_size <= a.height
    for i, indicator in enumerate(view.card_indicators):
        logo = view.header_logos[i].mask
        if i == 0:
            assert indicator.right < logo.pos[0]
        else:
            assert indicator.x > logo.pos[0]+logo.size[0]
    e.cards = [CardEvent('yellow_card', e.teams[0], 20), CardEvent('red_card', e.teams[1], 40)]
    view.draw_scene()
    assert view.card_indicators[0].counts == (1, 0)
    assert view.card_indicators[1].counts == (0, 1)


def test_results_group_card_minutes_without_empty_sections(view):
    h, a = view.engine.teams
    cards = [CardEvent('yellow_card', h, 60), CardEvent('yellow_card', h, 10), CardEvent('red_card', a, 42)]
    panel = view.result_panel
    panel.set_result({h: 2, a: 0}, [(h, 35), (h, 7)], cards)
    assert panel.minutes[h] == [7, 35]
    assert panel.card_minutes[h] == {'yellow_card': [10, 60], 'red_card': []}
    assert panel.card_minutes[a] == {'yellow_card': [], 'red_card': [42]}
    assert [row.text.text for row in panel.card_rows[0]] == ["10' SARI", "60' SARI"]
    assert [row.text.text for row in panel.card_rows[1]] == ["42' KIRMIZI"]
    assert panel.card_rows[0][0].icon_color.rgba == pytest.approx((1, .81, .15, 1))
    assert panel.card_rows[1][0].icon_color.rgba == pytest.approx((1, .2, .2, 1))
    panel.set_result({h: 0, a: 0}, [], [])
    assert [label.text for label in panel.goal_labels] == ['Gol atılmadı', 'Gol atılmadı']
    assert panel.card_rows == [[], []]


def test_presentation_keeps_widget_count_and_engine_state(view):
    a, e = view.announcements, view.engine
    widgets, instructions = len(view.children), len(a.canvas.children)
    before = [vars(d).copy() for d in e.disks]
    e.emit('red_card', 0, 0, e.teams[0])
    a.sync(e)
    for _ in range(240):
        a.advance(1/120)
    assert len(view.children) == widgets and len(a.canvas.children) == instructions
    assert [vars(d) for d in e.disks] == before
    e.restart()
    a.sync(e)
    assert a.idle


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280)])
def test_many_goals_and_cards_stay_in_final_scroll(view, size):
    view.size = size
    e = view.engine
    h, a = e.teams
    e.goals = [(h, i % 90+1) for i in range(120)]
    e.cards = [CardEvent('yellow_card', h, 10), CardEvent('yellow_card', h, 25), CardEvent('red_card', a, 80)]
    e.scores = {h: 120, a: 0}
    e.state = 'finished'
    view.draw_scene()
    for _ in range(5):
        Clock.tick()
    panel = view.result_panel
    assert panel.goal_labels[0].height > panel.goal_scrolls[0].height
    assert panel.top <= view.height and panel.y >= 0
    assert panel.goal_scrolls[0].right < panel.goal_scrolls[1].x
    assert panel.card_minutes[a]['red_card'] == [80]


@pytest.mark.parametrize('theme', ['fire_arena', 'electric_blue', 'emerald_arena'])
def test_ambient_effects_are_bounded_and_physics_independent(theme):
    from kivy.graphics import Fbo
    from services.arena_themes import get_theme
    from screens.match_effects import MatchEffects
    with Fbo(size=(64, 64)):
        effects = MatchEffects(get_theme(theme).effects)
    e = MatchEngine(seed=14)
    e.state = 'playing'
    before = e.random.getstate(), [vars(d).copy() for d in e.disks]
    visible = False
    for _ in range(300):
        effects.update(e, 1/120)
        visible |= bool(effects.flashes or effects.particles)
        assert len(effects.flashes) <= 8 and len(effects.particles) <= 48
    assert visible
    assert before == (e.random.getstate(), [vars(d) for d in e.disks])
