from types import SimpleNamespace
import pytest
from kivy.app import App
from kivy.base import EventLoop
from kivy.clock import Clock
from screens.router import AppRouter
from services.team_store import TeamStore
from main import SimomatchApp


@pytest.fixture
def root(tmp_path):
    EventLoop.ensure_window()
    audio = SimpleNamespace(events=[], closed=False)
    audio.play = lambda key: audio.events.append(key)
    audio.close = lambda: setattr(audio, 'closed', True)
    router = AppRouter(TeamStore(tmp_path), None, audio=audio, size=(450, 800))
    yield router
    router.dispose()


def settle():
    for _ in range(3):
        Clock.tick()


@pytest.mark.parametrize('button,destination', [('match_button', 'setup'), ('team_button', 'teams')])
def test_navigation_click_audio_single_action_and_animation_restart(root, button, destination):
    menu = root.get_screen('menu')
    settle()
    assert menu.emblem.clock_event.is_triggered
    initial = menu.emblem.clock_event
    menu.on_enter()
    assert menu.emblem.clock_event is initial
    getattr(menu, button).dispatch('on_release')
    getattr(menu, button).dispatch('on_release')
    assert root.current == destination
    assert root.audio.events == ['button']
    assert not initial.is_triggered
    frozen = menu.emblem.time
    settle()
    assert menu.emblem.time == frozen
    root.back()
    assert root.current == 'menu' and menu.emblem.clock_event.is_triggered
    settle()
    assert menu.emblem.time > frozen


def test_exit_cancel_does_not_change_records_and_reuses_one_dialog(root):
    root.store.save('Kayıtlı takım')
    before = root.store.path.read_bytes()
    menu = root.get_screen('menu')
    menu.exit_button.dispatch('on_release')
    dialog = menu.exit_dialog
    assert dialog is not None and not dialog.auto_dismiss
    menu.request_exit()
    assert menu.exit_dialog is dialog
    menu.cancel_button.dispatch('on_release')
    assert menu.exit_dialog is None and not menu._closing
    assert root.current == 'menu' and menu.emblem.clock_event.is_triggered
    assert root.store.path.read_bytes() == before
    assert root.audio.events == ['button', 'button']


def test_confirm_calls_app_stop_once_and_cleanup_leaves_records_intact(root, monkeypatch):
    root.store.save('Saklanacak takım')
    before = root.store.path.read_bytes()
    menu = root.get_screen('menu')
    calls = []
    fake_app = SimpleNamespace(router=root, audio=root.audio, on_keyboard=lambda *_: None)
    def stop():
        calls.append('stop')
        SimomatchApp.on_stop(fake_app)
    fake_app.stop = stop
    monkeypatch.setattr(App, 'get_running_app', staticmethod(lambda: fake_app))
    menu.request_exit()
    menu.confirm_button.dispatch('on_release')
    menu.confirm_exit()
    assert calls == ['stop'] and root.audio.closed
    assert menu.exit_dialog is None and not menu.emblem.clock_event.is_triggered
    assert root.store.path.read_bytes() == before


def test_back_key_uses_same_confirmation_and_non_menu_navigation(root):
    app = SimpleNamespace(router=root)
    assert SimomatchApp.on_keyboard(app, None, 27)
    assert root.get_screen('menu').exit_dialog
    assert SimomatchApp.on_keyboard(app, None, 27)
    assert root.get_screen('menu').exit_dialog is None
    root.go('setup')
    assert SimomatchApp.on_keyboard(app, None, 27)
    assert root.current == 'menu'
    assert not SimomatchApp.on_keyboard(app, None, 65)


def test_pause_resume_and_dispose_cancel_clock_without_canvas_growth(root):
    menu = root.get_screen('menu')
    app = SimpleNamespace(router=root)
    count = len(menu.emblem.canvas.children)
    original = menu.emblem.disks[0][1].pos
    for _ in range(90):
        menu.emblem.advance(1/30)
    assert menu.emblem.disks[0][1].pos != original
    assert len(menu.emblem.canvas.children) == count
    assert SimomatchApp.on_pause(app)
    assert not menu.emblem.clock_event.is_triggered
    SimomatchApp.on_resume(app)
    assert menu.emblem.clock_event.is_triggered
    root.dispose()
    assert not menu.emblem.clock_event.is_triggered


@pytest.mark.parametrize('size', [(320, 640), (450, 800), (720, 1280), (1080, 1920)])
def test_centered_responsive_layout_has_no_overlaps(root, size):
    root.size = size
    settle()
    menu = root.get_screen('menu')
    widgets = [menu.emblem, menu.title_label, menu.tagline, menu.match_button,
               menu.team_button, menu.exit_button, menu.footer]
    for widget in widgets:
        assert widget.center_x == pytest.approx(size[0]/2)
        assert widget.x >= 0 and widget.right <= size[0]
        assert 0 <= widget.y < widget.top <= size[1]
    for upper, lower in zip(widgets, widgets[1:]):
        assert lower.top < upper.y
    assert menu.match_button.width == menu.team_button.width == menu.exit_button.width
    assert menu.match_button.height >= 44
    menu.request_exit()
    assert menu.exit_dialog.width < size[0] and menu.exit_dialog.height < size[1]
