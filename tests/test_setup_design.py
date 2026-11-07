"""Real layout and interactions, isolated storage and file picker."""
import pytest
from kivy.base import EventLoop
from kivy.clock import Clock
from screens.router import AppRouter
from services.team_store import TeamStore
from services.arena_themes import THEMES
from screens.setup_controls import DurationInput, ThemeTile, RingPreview


class Picker:
    selected = None
    def pick(self, kind, callback):
        assert kind == 'image'
        callback(self.selected, '')


@pytest.fixture
def form(tmp_path):
    EventLoop.ensure_window()
    root = AppRouter(TeamStore(tmp_path), Picker(), size=(450, 800))
    root.store.save(('Ev sahibi çok uzun takım ismi ' * 2)[:40])
    root.store.save(('Deplasman çok uzun takım ismi ' * 2)[:40])
    root.store.save('Üçüncü takım')
    root.go('setup')
    yield root.get_screen('setup')
    root.get_screen('setup').on_pre_leave()
    root.dispose()


def settle():
    for _ in range(4):
        Clock.tick()


def test_logos_picker_selection_excludes_opponent_and_updates_immediately(form, png_file):
    team = form.router.store.save('Logolu', logo=png_file)
    form.on_pre_enter()
    form.open_team_picker(0)
    assert len(form.picker_rows) == 4
    form.choose_team(0, team['name'])
    assert form.previews[0].texture.size == (48, 32)
    assert form.previews[0].fit_mode == 'contain'
    assert form.logo_placeholders[0].opacity == 0
    form.open_team_picker(1)
    assert sum(row.disabled for row in form.picker_rows) == 1
    form.choose_team(1, team['name'])
    assert form.selected_ids[1] is None
    assert 'farklı' in form.status.text
    other = next(t for t in form.router.store.teams if t['id'] != team['id'])
    form.choose_team(1, other['name'])
    assert form.selected_ids == [team['id'], other['id']]
    assert form.team_names[1].text == other['name']


def test_duration_buttons_bounds_direct_entry_and_independent_logo_values(form):
    assert form.duration_input.text == '55'
    form.plus_button.dispatch('on_release')
    assert form.duration_input.text == '60'
    form.minus_button.dispatch('on_release')
    assert form.duration_input.text == '55'
    form.duration_input.text = '10'
    form.minus_button.dispatch('on_release')
    assert form.duration_input.text == '10'
    form.duration_input.text = '600'
    form.plus_button.dispatch('on_release')
    assert form.duration_input.text == '600'
    form.duration_input.text = ''
    form.duration_input.insert_text('abc')
    assert form.duration_input.text == ''
    form.duration_input.insert_text('601')
    assert form.duration_input.text == ''
    form.duration_input.insert_text('125')
    assert form.duration_input.text == '125'
    form.duration_input.text = '1'
    form.duration_input.commit(form.duration_input, False)
    assert form.duration_input.text == '10'
    form.sliders[0].value = 18
    form.sliders[1].value = 80
    assert form.size_labels[0].text.endswith('18')
    assert form.size_labels[1].text.endswith('80')


@pytest.mark.parametrize('theme', list(THEMES))
def test_gallery_selection_and_all_settings_transfer(form, theme):
    teams = form.router.store.teams
    for i in range(2):
        form.choose_team(i, teams[i]['name'])
    form.theme_tiles[theme].dispatch('on_release')
    assert form.theme.text == theme
    assert sum(tile.selected for tile in form.theme_tiles.values()) == 1
    assert form.theme_tiles[theme].selected
    form.sliders[0].value, form.sliders[1].value = 25, 75
    form.duration_input.text = '120'
    form.goal_speed_slider.value = 145
    form.goal_size_slider.value = 135
    form.start_button.dispatch('on_release')
    engine = form.router.match_view.engine
    assert engine.radii == (25, 75) and engine.duration == 120
    assert engine.goal_speed_degrees == 145 and engine.goal_size_percent == 135
    assert engine.state == 'countdown' and engine.countdown == 3
    assert form.router.match_view.settings.theme == theme


def test_custom_background_preview_remove_and_bad_path(form, png_file, tmp_path):
    form.router.picker.selected = str(png_file)
    form.pick_background()
    assert form.background_path != str(png_file)
    from pathlib import Path
    assert Path(form.background_path).read_bytes() == png_file.read_bytes()
    assert Path(form.background_path).parent == form.router.store.root/'custom_backgrounds'
    assert form.background_preview.texture and form.background_preview.opacity == 1
    form.remove_background.dispatch('on_release')
    assert form.background_path == '' and form.background_preview.texture is None
    form.router.picker.selected = str(tmp_path/'absent.png')
    form.pick_background()
    assert form.background_path == '' and 'okunamadı' in form.status.text


def test_missing_preview_has_canvas_fallback_and_back_returns_menu(form):
    tile = ThemeTile('missing', 'Önizleme', None, ((.4, .2, 1),), lambda key: None)
    assert any(isinstance(child, RingPreview) for child in tile.children)
    form.back_button.dispatch('on_release')
    assert form.router.current == 'menu'


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280), (1080, 1920)])
def test_responsive_cards_sliders_and_fixed_action_remain_accessible(form, size):
    form.router.size = size
    settle()
    left, right = reversed(form.columns.children)
    assert left.width == pytest.approx(right.width)
    assert left.right < right.x
    assert form.start_button.y >= 16
    assert form.start_button.top < form.scroll.y
    assert form.start_button.width < size[0]
    for card in form.team_cards:
        children = list(reversed(card.children))
        for a, b in zip(children, children[1:]):
            assert b.top <= a.y+.1
    for slider in (*form.sliders, form.goal_speed_slider, form.goal_size_slider):
        assert slider.width > 80 and slider.height >= 30
        assert slider.track.points[0] >= slider.x
        assert slider.track.points[2] <= slider.x+slider.width
        assert slider.thumb.pos[1]+slider.thumb.size[1]/2 == pytest.approx(slider.y+slider.height/2)
    for preview, placeholder, card in zip(form.previews, form.logo_placeholders, form.team_cards):
        assert card.x <= preview.x < preview.right <= card.right
        assert card.y < preview.y < preview.top < card.top
        assert preview.center == pytest.approx(placeholder.center)
    assert form.theme_scroll.do_scroll_x and not form.theme_scroll.do_scroll_y
    assert form.theme_scroll.children[0].width >= 5*116
    for scroll in (0, .5, 1):
        form.scroll.scroll_y = scroll
        settle()
        assert 0 <= form.start_button.y < form.start_button.top <= size[1]
