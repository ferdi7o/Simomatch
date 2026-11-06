import json
import pytest
from services.team_store import TeamStore


def test_save_reload_copy_edit_delete(tmp_path, png_file):
    music = tmp_path / 'goal.mp3'
    music.write_bytes(b'ID3\x04\0\0\0\0\0\0')
    store = TeamStore(tmp_path / 'data')
    team = store.save('  Mor   Takım  ', logo=png_file, music=music)
    assert team['name'] == 'Mor Takım'
    logo_path, music_path = store.asset_path(team['logo']), store.asset_path(team['music'])
    assert logo_path.read_bytes() == png_file.read_bytes()
    assert music_path.read_bytes() == music.read_bytes()
    png_file.unlink()
    music.unlink()
    store = TeamStore(store.root)
    assert store.get(team['id']) == team
    assert store.asset_path(team['logo']).is_file()
    updated = store.save('Yeni İsim', team_id=team['id'])
    assert updated['logo'] == team['logo'] and updated['music'] == team['music']
    updated = store.save('Yeni İsim', logo='', team_id=team['id'])
    assert updated['logo'] == ''
    store.delete(team['id'])
    assert TeamStore(store.root).teams == []


def test_duplicate_names_and_validation(tmp_path):
    store = TeamStore(tmp_path)
    team = store.save('  Test  Takım ')
    with pytest.raises(ValueError, match='zaten'):
        store.save('test takım')
    assert store.save('TEST TAKIM', team_id=team['id'])['id'] == team['id']
    for name in ('', '   ', 'a'*41):
        with pytest.raises(ValueError):
            store.save(name)


def test_invalid_media_does_not_partially_save(tmp_path, png_file):
    store = TeamStore(tmp_path / 'data')
    bad_music = tmp_path / 'bad.mp3'
    bad_music.write_bytes(b'not audio')
    with pytest.raises(ValueError):
        store.save('Fail', logo=png_file, music=bad_music)
    assert store.teams == []
    assert list(store.assets.iterdir()) == []
    with pytest.raises(ValueError):
        store.save('Fail', logo=tmp_path / 'missing.png')


def test_corrupt_json_is_recoverable_and_backed_up(tmp_path):
    (tmp_path / 'teams.json').write_text('{broken', encoding='utf-8')
    store = TeamStore(tmp_path)
    assert store.warning and store.teams == []
    store.save('Yeni')
    assert next(tmp_path.glob('teams.backup.*.json')).read_text() == '{broken'
    assert TeamStore(tmp_path).teams[0]['name'] == 'Yeni'


def test_missing_and_untrusted_asset_paths_are_safe(tmp_path, png_file):
    store = TeamStore(tmp_path / 'data')
    assert store.asset_path('../logo.png') is None
    assert store.asset_path(str(png_file)) is None
    assert store.asset_path('assets/missing.png') is None


def test_atomic_failure_preserves_previous_json(tmp_path, monkeypatch):
    store = TeamStore(tmp_path)
    original = store.save('İlk')
    data = store.path.read_bytes()
    from pathlib import Path
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(Path, 'replace', fail)
    with pytest.raises(OSError):
        store.save('İkinci')
    assert store.teams == [original]
    assert store.path.read_bytes() == data
