import pytest
from services.file_picker import DesktopFilePicker, AndroidFilePicker, create_file_picker


@pytest.mark.parametrize('selection', ['', 'C:/logos/team.png'])
def test_desktop_picker_selection_and_cancel(monkeypatch, selection):
    monkeypatch.setattr(DesktopFilePicker, '_select', lambda self, kind: selection)
    results = []
    DesktopFilePicker().pick('image', lambda *args: results.append(args))
    assert results == [(selection or None, '')]


def test_desktop_picker_error_returns_message(monkeypatch):
    def fail(*args):
        raise RuntimeError('dialog unavailable')
    monkeypatch.setattr(DesktopFilePicker, '_select', fail)
    results = []
    DesktopFilePicker().pick('music', lambda *args: results.append(args))
    assert results[0][0] is None and 'dialog unavailable' in results[0][1]


def test_picker_platform_boundary(tmp_path):
    assert isinstance(create_file_picker('win', tmp_path), DesktopFilePicker)
    assert isinstance(create_file_picker('android', tmp_path), AndroidFilePicker)
