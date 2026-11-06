from dataclasses import replace
import pytest
from kivy.clock import Clock
from services.arena_themes import THEMES, get_theme
from services.match_settings import MatchSettings
from services.team_store import TeamStore
from screens.match_screen import MatchScreen
from screens.router import AppRouter


def settle():
    for _ in range(5):
        Clock.tick()


def settings(theme='neon_purple'):
    return MatchSettings({'id': 'h', 'name': 'W'*40, 'logo': ''},
                         {'id': 'a', 'name': 'Deplasman '+('Uzun '*6), 'logo': ''}, theme=theme)


@pytest.fixture
def view():
    screen = MatchScreen(settings=settings(), size=(450, 800))
    yield screen
    screen.dispose()


def finish(view, goals):
    view.engine.state = 'finished'
    view.engine.goals = list(goals)
    view.engine.scores = {team: sum(t == team for t, _ in goals) for team in view.engine.teams}
    view.draw_scene()
    settle()
    return view.result_panel


def test_final_minutes_belong_to_correct_team_and_are_sorted(view):
    home, away = view.engine.teams
    panel = finish(view, [(home, 80), (away, 44), (home, 3), (away, 9), (home, 3)])
    assert panel.minutes == {home: [3, 3, 80], away: [9, 44]}
    assert panel.goal_labels[0].text.splitlines() == ['3′', '3′', '80′']
    assert panel.goal_labels[1].text.splitlines() == ['9′', '44′']
    assert panel.score.text == '3 - 2'
    assert [label.text for label in panel.names] == [home, away]
    assert panel.opacity == 1 and not panel.disabled


@pytest.mark.parametrize('counts', [(0, 0), (3, 0), (0, 15), (80, 120)])
@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280)])
def test_final_columns_scroll_without_overflow(view, counts, size):
    view.size = size
    home, away = view.engine.teams
    goals = [(home, (i % 90)+1) for i in range(counts[0])]
    goals += [(away, (i % 90)+1) for i in range(counts[1])]
    panel = finish(view, goals)
    left, right = panel.goal_scrolls
    assert left.right < right.x
    assert panel.y > view.restart_button.top
    assert panel.top < min(label.y for label in view.team_names)
    for i, count in enumerate(counts):
        scroll, label = panel.goal_scrolls[i], panel.goal_labels[i]
        assert scroll.x >= panel.x and scroll.right <= panel.right
        assert scroll.y >= panel.y and scroll.top <= panel.top
        assert label.width == pytest.approx(scroll.width)
        assert panel.names[i].text == view.engine.teams[i]  # Full, wrapped name.
        assert panel.names[i].text_size[0] <= panel.name_scrolls[i].width
        if count == 0:
            assert label.text == 'Gol atılmadı'
        if count > 15:
            assert label.height > scroll.height
            scroll.scroll_y = 0
            view.draw_scene()
            assert scroll.scroll_y == 0  # Render does not reset the scroll.
    view.restart_match()
    assert panel.opacity == 0 and panel.disabled
    assert view.engine.state == 'countdown'


def test_exact_five_theme_ids_and_legacy_names():
    from pathlib import Path
    assert set(THEMES) == {'neon_purple', 'fire_arena', 'electric_blue', 'rainbow_neon', 'emerald_arena'}
    assert get_theme('neon_purple').image_path == Path(__file__).resolve().parents[1]/'assets/backgrounds/neon_purple.png'
    assert settings('Neon mor').theme == 'neon_purple'
    assert settings('Okyanus').theme == 'electric_blue'
    with pytest.raises(ValueError):
        settings('unknown')


@pytest.mark.parametrize('source_size', [(128, 32), (32, 128)])
@pytest.mark.parametrize('screen_size', [(320, 640), (450, 800), (720, 1280)])
def test_background_cover_preserves_aspect_and_center(source_size, screen_size):
    from kivy.graphics.texture import Texture
    from screens.match_visuals import cover_coordinates
    texture = Texture.create(size=source_size)
    texture.flip_vertical()
    uv = cover_coordinates(texture, screen_size)
    u_span, v_span = abs(uv[2]-uv[0]), abs(uv[7]-uv[1])
    assert u_span*source_size[0]/(v_span*source_size[1]) == pytest.approx(screen_size[0]/screen_size[1])
    assert (uv[0]+uv[2])/2 == pytest.approx(.5)
    assert (uv[1]+uv[7])/2 == pytest.approx(.5)


@pytest.mark.parametrize('theme', list(THEMES))
def test_theme_selection_reaches_visuals_without_changing_physics(tmp_path, theme):
    router = AppRouter(TeamStore(tmp_path), None, size=(450, 800))
    try:
        a, b = router.store.save('Ev'), router.store.save('Deplasman')
        router.go('setup')
        form = router.get_screen('setup')
        assert set(form.theme.values) == set(THEMES)
        form.spinners[0].text, form.spinners[1].text = a['name'], b['name']
        form.theme.text = theme
        form.start_match()
        view = router.match_view
        assert router.current == 'match'
        assert view.settings.theme == theme and view.theme == get_theme(theme)
        assert view.ring.palette == THEMES[theme].palette
        assert view.effects.style == THEMES[theme].effects
        from engine.match_engine import MatchEngine
        reference = MatchEngine(seed=43)
        view.engine.random.seed(43)
        view.engine.restart()
        reference.advance(12)
        view.engine.advance(12)
        assert view.engine.goal.posts == reference.goal.posts
        assert view.engine.goal.line_distance == reference.goal.line_distance
        for disk, ref in zip(view.engine.disks, reference.disks):
            assert (disk.x, disk.y, disk.vx, disk.vy) == pytest.approx((ref.x, ref.y, ref.vx, ref.vy))
    finally:
        router.dispose()


def test_theme_background_missing_corrupt_and_present(monkeypatch, png_file, tmp_path):
    original = THEMES['neon_purple']
    for path in (tmp_path/'missing.png', tmp_path/'broken.png', png_file):
        if path.name == 'broken.png':
            path.write_bytes(b'not a PNG')
        monkeypatch.setitem(THEMES, 'neon_purple', replace(original, background_image=str(path)))
        view = MatchScreen(settings=settings(), size=(450, 800))
        try:
            if path == png_file:
                assert view.background_texture is not None
                # Cropped UVs retain image proportions while filling 450x800.
                uv = view.background.tex_coords
                u_span, v_span = abs(uv[2]-uv[0]), abs(uv[7]-uv[1])
                texture = view.background.texture
                assert (u_span*texture.width)/(v_span*texture.height) == pytest.approx(450/800)
                assert view.background_shade.size == pytest.approx(view.size)
            else:
                assert view.background_texture is None
                assert view.background_color.rgba == pytest.approx(original.background_color)
        finally:
            view.dispose()


def test_results_use_the_same_real_logos(png_file, tmp_path):
    store = TeamStore(tmp_path/'teams')
    a, b = store.save('Ev', logo=png_file), store.save('Deplasman', logo=png_file)
    view = MatchScreen(settings=MatchSettings(a, b), store=store)
    try:
        finish(view, [])
        assert all(d.texture is source for d, source in zip(view.result_panel.logos, view.logo_textures))
    finally:
        view.dispose()
