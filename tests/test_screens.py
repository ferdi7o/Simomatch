"""Real Kivy widgets/OpenGL, fake chooser only at the platform boundary."""
import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from screens.router import AppRouter
from services.team_store import TeamStore
from services.media import load_texture


class FakePicker:
    selected = None

    def pick(self, kind, callback):
        callback(self.selected, '')


@pytest.fixture
def router(tmp_path):
    root = AppRouter(TeamStore(tmp_path / 'data'), FakePicker(), size=(450, 800))
    yield root
    root.dispose()


def settle():
    for _ in range(3):
        Clock.tick()


def populate(root):
    a = root.store.save('Mor Takım')
    b = root.store.save('Neon Takım')
    return a, b


def test_menu_navigation_and_match_clock_lifecycle(router):
    assert router.current == 'menu' and router.match_view is None
    router.get_screen('menu').team_button.dispatch('on_release')
    assert router.current == 'teams'
    router.back()
    assert router.current == 'menu'
    a, b = populate(router)
    router.get_screen('menu').match_button.dispatch('on_release')
    setup = router.get_screen('setup')
    setup.spinners[0].text, setup.spinners[1].text = a['name'], b['name']
    setup.sliders[0].value, setup.sliders[1].value = 22, 44
    setup.duration_input.text = '70'
    setup.start_match()
    assert router.current == 'match'
    view = router.match_view
    assert view.engine.duration == 70 and view.engine.radii == (22, 44)
    router.back()
    elapsed = view.engine.countdown
    settle()
    assert router.current == 'setup'
    assert view.engine.countdown == elapsed
    setup.start_match()
    assert router.match_view is not view
    router.dispose()


def test_back_from_team_creation_returns_to_setup(router):
    router.go('setup')
    router.go('teams')
    router.back()
    assert router.current == 'setup'
    router.back()
    assert router.current == 'menu'


def test_form_validation_and_team_crud(router, png_file):
    router.go('setup')
    setup = router.get_screen('setup')
    setup.start_match()
    assert 'en az iki' in setup.status.text and router.current == 'setup'
    router.go('teams')
    team_screen = router.get_screen('teams')
    team_screen.name_input.text = 'Deneme'
    router.picker.selected = str(png_file)
    team_screen.pick('image')
    assert team_screen.preview.texture is not None
    team_screen.save()
    team = router.store.teams[0]
    assert team['name'] == 'Deneme' and team['logo']
    team_screen.edit(team['id'])
    team_screen.name_input.text = 'Yeni ad'
    team_screen.save()
    assert router.store.get(team['id'])['name'] == 'Yeni ad'
    router.store.save('Başka')
    router.go('setup')
    setup.spinners[0].text = setup.spinners[1].text = 'Yeni ad'
    setup.start_match()
    assert 'farklı' in setup.status.text and router.current == 'setup'
    team_screen.delete(team['id'])
    assert router.store.get(team['id']) is None


@pytest.mark.parametrize('size', [(300, 533), (320, 640), (450, 800), (720, 1280), (1080, 1920)])
def test_responsive_geometry(router, size):
    populate(router)
    router.size = size
    router.go('setup')
    setup = router.get_screen('setup')
    setup.spinners[0].text, setup.spinners[1].text = 'Mor Takım', 'Neon Takım'
    settle()
    left, right = setup.columns.children[::-1]
    assert left.right <= right.x
    assert left.width > 90 and right.width > 90
    assert setup.start_button.y >= 0 and setup.start_button.top <= size[1]
    setup.start_match()
    settle()
    view = router.match_view
    assert view.field.size[0] == view.field.size[1]
    assert view.radius*2 == pytest.approx(size[0]*.74)
    assert view.center_arena[1]+view.radius*1.17 < view.minute_label.y
    assert view.back_button.top < view.restart_button.y
    for logo, name in zip(view.header_logos, view.team_names):
        assert logo.mask.size[0] == pytest.approx(2*1.7*min(size[0]*.065, size[1]*.04))
        assert logo.mask.pos[1] >= name.top
        assert logo.mask.pos[1]+logo.mask.size[1] <= size[1]
        assert logo.mask.pos[0] >= 0
        assert logo.mask.pos[0]+logo.mask.size[0] <= size[0]
    assert view.engine.radii == (60, 60)
    assert view.team_names[0].right < view.team_names[1].x
    assert all(label.y > view.center_arena[1]+view.radius*1.3 for label in view.team_names)


def test_broken_images_fall_back_and_textures_are_circular(router, tmp_path, png_file):
    broken = tmp_path / 'bad.png'
    broken.write_bytes(b'not an image')
    assert load_texture(broken) is None
    assert load_texture(tmp_path / 'missing.png') is None
    a = router.store.save('Logolu', logo=png_file)
    b = router.store.save('Diğer')
    router.go('setup')
    setup = router.get_screen('setup')
    setup.spinners[0].text, setup.spinners[1].text = a['name'], b['name']
    setup.start_match()
    view = router.match_view
    logo = view.disk_shapes[0]
    texture = logo.image.texture
    assert texture.size == (48, 32)  # Original aspect ratio, no square crop.
    assert logo.image.size[0]/logo.image.size[1] == pytest.approx(1.5)
    from kivy.graphics import Ellipse
    assert isinstance(logo.mask, Ellipse)
    assert logo.mask.size[0] == pytest.approx(view.engine.disks[0].radius*view.scale*2)
    assert view.header_logos[0].texture is texture
    assert view.team_labels[0].text == ''


def test_long_names_and_custom_background_are_supported(router, png_file):
    a = router.store.save('A'*40, logo=png_file)
    b = router.store.save('B'*40)
    router.go('setup')
    setup = router.get_screen('setup')
    assert [s.value for s in setup.sliders] == [60, 60]
    setup.spinners[0].text, setup.spinners[1].text = a['name'], b['name']
    setup.background_path = str(png_file)
    setup.start_match()
    settle()
    view = router.match_view
    assert view.background.texture is not None
    assert all(label.shorten and label.width < view.width*.31 for label in view.team_names)
    view.engine.state = 'playing'
    count, widgets = len(view.canvas.children), len(view.children)
    for _ in range(60):
        view.update(1/60)
    assert len(view.canvas.children) == count and len(view.children) == widgets
