"""Real SDL2 WAV/MP3 load + overlap check, no user data writes.

Runs at a low volume and exits after checking independent 5-second timers.
This checks provider states, not sound quality from physical speakers.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['KIVY_HOME'] = str(ROOT / '.kivy_runtime')
from kivy.clock import Clock
from types import SimpleNamespace
from services.audio import AudioManager


def run():
    import time
    manager = AudioManager()
    manager.effects_volume = .08
    manager.music_volume = .06
    try:
        assert not manager.diagnostics, manager.diagnostics
        assert all(manager.pools.values())
        import tempfile
        probe_dir = ROOT / '.smoke_runtime'
        probe_dir.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=probe_dir, suffix='.mp3', delete=False) as probe:
            probe.write(b'not a valid audio file')
            probe_path = Path(probe.name)
        try:
            assert not manager._load_pool(probe_path, 2)
            assert str(probe_path) in manager.diagnostics
            print('REAL BACKEND: corrupt MP3 rejected without crashing')
        finally:
            probe_path.unlink(missing_ok=True)
        sounds = ROOT / 'assets' / 'sounds'
        teams = ({'name': 'Home', 'music': str(sounds / 'goal.mp3')},
                 {'name': 'Away', 'music': str(sounds / 'goal.mp3')})
        session = manager.create_session(teams, SimpleNamespace(asset_path=lambda path: Path(path)))
        assert session.goal('Home') and session.goal('Away')
        assert session.music['Home'][0].busy and session.music['Away'][0].busy
        assert sum(v.busy for v in manager.pools['goal']) == 2
        if sys.platform == 'win32':
            import ctypes
            mixer = ctypes.CDLL('SDL2_mixer.dll')
            mixer.Mix_Playing.argtypes = [ctypes.c_int]
            mixer.Mix_Playing.restype = ctypes.c_int
            assert mixer.Mix_Playing(-1) >= 4
            print('SDL MIXER: at least 4 native mixer channels active simultaneously')
        manager.play('wall')
        assert manager.pools['wall'][0].busy
        print('REAL BACKEND: all 11 files decoded; WAV + MP3 and four MP3 voices overlap')
        session.stop_team('Home')
        assert not session.music['Home'][0].busy and session.music['Away'][0].busy
        began = time.monotonic()
        deadline = began+5.2
        observed_fade = False
        while time.monotonic() < deadline:
            Clock.tick()
            elapsed = time.monotonic()-began
            volume = session.music['Away'][0].sound.volume
            if elapsed < 3.4:
                assert abs(volume-manager.music_volume) < .001
            if 4.2 < elapsed < 4.4:
                assert 0 < volume < manager.music_volume
                observed_fade = True
        assert observed_fade
        assert all(not v.busy for pool in session.music.values() for v in pool)
        assert session.music['Away'][0].sound.volume == 0
        print('REAL BACKEND: independent stop, 3.5s fade start, volume reduction and 5s stop passed')
    finally:
        manager.close()


if __name__ == '__main__':
    run()
