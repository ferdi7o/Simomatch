"""Audio routing/timers without requiring speakers or a codec in unit tests."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from services.audio import AudioManager, SOUND_FILES
from engine.match_engine import MatchEngine
from config import FIXED_DT, MAX_SPEED

ROOT = Path(__file__).resolve().parents[1]


class FakeSound:
    def __init__(self, path):
        self.path, self.state, self.length = path, 'stop', 10.
        self.plays = self.stops = 0
        self.volume, self.loop = 1., False

    def play(self):
        self.state = 'play'
        self.plays += 1

    def stop(self):
        self.state = 'stop'
        self.stops += 1

    def unload(self):
        self.state = 'stop'


class FakeTimer:
    def __init__(self, callback, seconds):
        self.callback, self.seconds, self.cancelled = callback, seconds, False

    def cancel(self):
        self.cancelled = True


@pytest.fixture
def audio(tmp_path):
    for filename in SOUND_FILES.values():
        (tmp_path / filename).write_bytes(b'test')
    loaded, timers, now = [], [], [0.]
    def load(path):
        sound = FakeSound(path)
        loaded.append(sound)
        return sound
    def schedule(callback, seconds):
        timer = FakeTimer(callback, seconds)
        timers.append(timer)
        return timer
    manager = AudioManager(tmp_path, loader=load, schedule=schedule, now=lambda: now[0])
    yield SimpleNamespace(manager=manager, timers=timers, now=now, loaded=loaded, root=tmp_path)
    manager.close()


def test_all_named_assets_exist_and_have_expected_formats():
    assert len(SOUND_FILES) == 11
    for filename in SOUND_FILES.values():
        path = ROOT / 'assets' / 'sounds' / filename
        assert path.is_file() and path.stat().st_size > 0
        data = path.read_bytes()[:12]
        if path.suffix == '.wav':
            assert data[:4] == b'RIFF' and data[8:12] == b'WAVE'
        else:
            assert path.suffix == '.mp3'
            assert data[:3] == b'ID3' or (data[0] == 255 and data[1] & 224 == 224)


def test_effects_preload_once_cooldown_and_independent_voices(audio):
    m = audio.manager
    count = len(audio.loaded)
    assert m.play('disk')
    assert not m.play('disk')
    audio.now[0] = .05
    assert not m.play('disk')
    audio.now[0] = .101
    assert m.play('disk')
    assert len(audio.loaded) == count
    assert sum(v.sound.state == 'play' for v in m.pools['disk']) == 2
    assert m.play('wall')
    assert m.pools['disk'][0].sound is not m.pools['wall'][0].sound
    assert all(v.sound.volume == .32 for v in m.pools['disk'][:2])


def test_idle_preloaded_effect_is_not_reset_before_play(audio):
    m = audio.manager
    sound = m.pools['disk'][0].sound
    assert m.play('disk') and sound.stops == 0
    m.stop_effect('disk')
    assert sound.stops == 1 and sound.state == 'stop'


def music_session(audio):
    a, b = audio.root / 'home.mp3', audio.root / 'away.mp3'
    a.write_bytes(b'ID3')
    b.write_bytes(b'ID3')
    teams = ({'name': 'Home', 'music': str(a)}, {'name': 'Away', 'music': str(b)})
    store = SimpleNamespace(asset_path=lambda path: Path(path))
    return audio.manager.create_session(teams, store)


def test_correct_team_music_overlaps_goal_and_other_team(audio):
    session = music_session(audio)
    assert session.goal('Home')
    home = session.music['Home'][0]
    assert home.sound.path.endswith('home.mp3') and home.busy
    assert not session.music['Away'][0].busy
    assert session.goal('Away')
    away = session.music['Away'][0]
    assert away.sound.path.endswith('away.mp3') and away.busy
    assert home.busy
    assert sum(v.busy for v in audio.manager.pools['goal']) == 2
    assert home.timer.seconds == away.timer.seconds == 5.
    assert home.fade_timer.seconds == away.fade_timer.seconds == 3.5
    away_timeout = away.timer
    session.stop_team('Home')
    assert not home.busy and away.busy
    away_timeout.callback(5)
    assert not away.busy


def test_old_music_timeout_cannot_stop_reused_voice(audio):
    session = music_session(audio)
    session.goal('Home')
    old = session.music['Home'][0].timer
    old_fade = session.music['Home'][0].fade_timer
    session.goal('Home')
    session.goal('Home')  # Two slots full: reuse only this team's first slot.
    assert old.cancelled
    old.callback(5)  # Simulate an already queued stale callback.
    old_fade.callback(3.5)
    assert session.music['Home'][0].busy
    assert all(not v.busy for v in session.music['Away'])


def test_music_fades_at_3_5_and_stops_at_5_restoring_next_play(audio):
    session = music_session(audio)
    session.goal('Home')
    voice = session.music['Home'][0]
    base = audio.manager.music_volume
    timeout = voice.timer
    assert voice.fade_timer.seconds == 3.5
    audio.now[0] = 3.499
    assert voice.sound.volume == base and voice.busy
    audio.now[0] = 3.5
    voice.fade_timer.callback(3.5)
    assert voice.sound.volume == base and voice.busy
    audio.now[0] = 4.25
    voice.fade_timer.callback(.75)
    assert voice.sound.volume == pytest.approx(base*.5)
    assert voice.busy
    audio.now[0] = 4.99
    voice.fade_timer.callback(.74)
    assert 0 < voice.sound.volume < base*.001
    audio.now[0] = 5.
    timeout.callback(5)
    assert voice.sound.volume == 0 and not voice.busy
    assert voice.timer is None and voice.fade_timer is None
    session.goal('Home')
    assert voice.busy and voice.sound.volume == base


def test_staggered_team_fades_and_effect_volume_are_independent(audio):
    session = music_session(audio)
    session.goal('Home')
    home = session.music['Home'][0]
    audio.now[0] = 1.
    session.goal('Away')
    away = session.music['Away'][0]
    audio.now[0] = 4.25
    home.fade_timer.callback(.75)
    assert home.sound.volume == pytest.approx(audio.manager.music_volume*.5)
    assert away.sound.volume == audio.manager.music_volume
    assert audio.manager.pools['goal'][0].sound.volume == audio.manager.effects_volume
    audio.now[0] = 5.
    home.timer.callback(5)
    away.fade_timer.callback(.5)
    assert not home.busy and away.busy
    assert 0 < away.sound.volume < audio.manager.music_volume


def test_goal_event_selects_only_scoring_team_and_is_not_replayed(audio):
    session = music_session(audio)
    e = MatchEngine(teams=('Home', 'Away'))
    session.update(e)
    e.emit('goal', 450, 0, 'Away')
    session.update(e)
    assert session.music['Away'][0].busy
    assert all(not v.busy for v in session.music['Home'])
    plays = sum(v.sound.plays for v in session.music['Away'])
    session.update(e)
    assert sum(v.sound.plays for v in session.music['Away']) == plays


def test_full_effect_pool_drops_hit_without_restarting_active_voice(audio):
    m = audio.manager
    for index in range(3):
        audio.now[0] = index*.11
        assert m.play('wall')
    before = [(v.sound.plays, v.sound.stops) for v in m.pools['wall']]
    audio.now[0] += .11
    assert not m.play('wall')
    assert before == [(v.sound.plays, v.sound.stops) for v in m.pools['wall']]


def test_missing_and_corrupt_files_are_safe(tmp_path):
    m = AudioManager(tmp_path, loader=lambda path: None, schedule=lambda *args: None)
    assert not m.play('goal') and m.diagnostics
    (tmp_path / 'goal.mp3').write_bytes(b'broken')
    m = AudioManager(tmp_path, loader=lambda path: (_ for _ in ()).throw(ValueError('bad codec')),
                     schedule=lambda *args: None)
    assert not m.play('goal')
    assert 'bad codec' in str(m.diagnostics)
    session = m.create_session([{'name': 'Team', 'music': 'missing.mp3'}],
                               SimpleNamespace(asset_path=lambda path: None))
    assert not session.goal('Team')
    m.close()


def test_match_events_consumed_once_and_lifecycle_stops_audio(audio):
    m = audio.manager
    session = m.create_session()
    e = MatchEngine(seed=12)
    session.update(e)
    assert m.pools['countdown'][0].busy
    e.advance(3)
    session.update(e)
    assert m.pools['start'][0].busy and not m.pools['countdown'][0].busy
    e.emit('wall', 1, 1)
    session.update(e)
    plays = sum(v.sound.plays for v in m.pools['wall'])
    audio.now[0] += .2
    session.update(e)
    assert sum(v.sound.plays for v in m.pools['wall']) == plays
    e.emit('yellow_card', 0, 0)
    e.emit('red_card', 0, 0)
    session.update(e)
    assert m.pools['yellow_card'][0].busy and m.pools['red_card'][0].busy
    e.advance(55)
    session.update(e)
    assert m.pools['end'][0].busy
    session.close()
    assert all(not v.busy for name, pool in m.pools.items() if name != 'button' for v in pool)


def test_same_physical_disk_contact_emits_one_event():
    e = MatchEngine(seed=8)
    e.state = 'playing'
    a, b = e.disks
    a.x, b.x, a.y, b.y = -61, 61, 0, 0
    a.vx, a.vy, b.vx, b.vy = MAX_SPEED, 0, -MAX_SPEED, 0
    e.advance(FIXED_DT*3)
    assert len([event for event in e.events if event[1] in ('disk', 'soft')]) == 1


def test_grazing_collision_uses_soft_sound_event():
    e = MatchEngine(seed=8)
    e.state = 'playing'
    a, b = e.disks
    a.x, b.x, a.y, b.y = -59.99, 59.99, 0, 0
    a.vx, a.vy, b.vx, b.vy = 100, 900, -100, 900
    e.advance(FIXED_DT)
    assert any(event[1] == 'soft' for event in e.events)


def test_volume_setting_is_clamped(audio):
    audio.manager.set_effects_volume(3)
    assert audio.manager.effects_volume == 1
    audio.manager.set_effects_volume(-1)
    assert audio.manager.effects_volume == 0


def test_leaving_match_closes_audio_and_cancels_music_timers(audio, tmp_path):
    from screens.router import AppRouter
    from services.team_store import TeamStore
    from services.match_settings import MatchSettings
    store = TeamStore(tmp_path / 'teams')
    music = audio.root / 'music.mp3'
    music.write_bytes(b'ID3')
    a = store.save('Home', music=music)
    b = store.save('Away', music=music)
    router = AppRouter(store, SimpleNamespace(), audio=audio.manager)
    router.go('setup')
    router.start_match(MatchSettings(a, b))
    session = router.match_view.audio_session
    session.goal('Home')
    timer = audio.timers[-1]
    router.back()
    assert session.closed and timer.cancelled
    assert not audio.manager.sessions
    router.dispose()
