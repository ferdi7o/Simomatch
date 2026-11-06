"""Preloaded independent Kivy Sound voices; no file reads on collision paths.

Each pool slot owns its own Sound instance (SDL2 mixer channel). A busy effect
pool drops an extra hit rather than restarting an in-flight sound. Team music
uses separate per-team pools, music-only fades and generation-safe stop callbacks.
"""
from pathlib import Path
from time import monotonic

SOUND_FILES = {
    'button': 'button_click.wav', 'wall': 'wall_collision.wav',
    'disk': 'flick.wav', 'soft': 'soft_puck.wav', 'goal': 'goal.mp3',
    'post': 'goalpost_hit.mp3', 'yellow_card': 'yellow_card.wav',
    'red_card': 'red_card.wav', 'countdown': 'play_alarm.wav',
    'start': 'whistle_start.mp3', 'end': 'whistle_end.mp3',
}
COLLISION_SOUNDS = {'wall', 'disk', 'soft', 'post'}


class Voice:
    def __init__(self, sound):
        self.sound, self.timer = sound, None
        self.fade_timer = None
        self.generation = 0

    def stop(self):
        self.generation += 1
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.fade_timer:
            self.fade_timer.cancel()
            self.fade_timer = None
        try:
            # Android MediaPlayer.stop() calls prepare(); never do that for an
            # already idle, preloaded effect before each collision playback.
            if self.busy:
                self.sound.stop()
            self.sound.state = 'stop'
        except Exception:
            pass

    def play(self, volume, schedule, seconds=None, now=monotonic, fade_seconds=0.):
        self.stop()
        generation = self.generation
        started = now()
        try:
            # Restore the requested level even when the previous play faded to 0.
            self.sound.volume = volume
            self.sound.play()
            if seconds is not None:
                fade_seconds = max(0., min(fade_seconds, seconds))
                def expire(dt):
                    if generation == self.generation:
                        try:
                            if fade_seconds:
                                self.sound.volume = 0.
                        except Exception:
                            pass
                        self.stop()
                self.timer = schedule(expire, seconds)
                if fade_seconds:
                    fade_start = seconds-fade_seconds
                    def fade(dt):
                        if generation != self.generation:
                            return  # A queued old callback cannot touch a new play.
                        if not self.busy:
                            return
                        progress = max(0., min(1., (now()-started-fade_start)/fade_seconds))
                        # Smoothstep gives continuous slope at both ends.
                        level = volume*(1-progress*progress*(3-2*progress))
                        try:
                            self.sound.volume = level
                        except Exception:
                            self.stop()
                            return
                        if progress >= 1:
                            self.stop()
                        else:
                            self.fade_timer = schedule(fade, 1/60)
                    self.fade_timer = schedule(fade, fade_start)
            return True
        except Exception:
            self.stop()
            return False

    @property
    def busy(self):
        try:
            return self.sound.state == 'play'
        except Exception:
            return False

    def close(self):
        self.stop()
        try:
            self.sound.unload()
        except Exception:
            pass


class AudioManager:
    def __init__(self, sounds_dir=None, loader=None, schedule=None, now=monotonic):
        if loader is None:
            try:
                from kivy.core.audio import SoundLoader
                loader = SoundLoader.load
            except Exception:
                loader = lambda path: None
        if schedule is None:
            from kivy.clock import Clock
            schedule = Clock.schedule_once
        self.loader, self.schedule, self.now = loader, schedule, now
        self.root = Path(sounds_dir or Path(__file__).resolve().parents[1] / 'assets' / 'sounds')
        self.effects_volume, self.music_volume = .32, .28
        self.music_seconds = 5.
        self.music_fade_seconds = 1.5
        self.pools, self.last_play, self.diagnostics = {}, {}, {}
        self.sessions = []
        for name, filename in SOUND_FILES.items():
            self.pools[name] = self._load_pool(self.root / filename, 3 if name in COLLISION_SOUNDS else 2)

    def _load_pool(self, path, count):
        if not path or not Path(path).is_file():
            self.diagnostics[str(path)] = 'Dosya bulunamadı'
            return []
        voices = []
        for _ in range(count):
            try:
                sound = self.loader(str(path))
                if sound is not None:
                    if sound.length <= 0:
                        self.diagnostics[str(path)] = 'Ses boş, bozuk veya çözücü tarafından desteklenmiyor'
                        sound.unload()
                        break
                    sound.loop = False
                    voices.append(Voice(sound))
                else:
                    self.diagnostics[str(path)] = 'Ses çözücü dosyayı yükleyemedi'
                    break
            except Exception as exc:
                self.diagnostics[str(path)] = str(exc)
                break
        return voices

    def _play_pool(self, pool, volume, seconds=None, reuse=False, fade_seconds=0.):
        voice = next((v for v in pool if not v.busy), None)
        if voice is None and pool and reuse:
            voice = pool[0]  # Only steals a voice from the same team's pool.
        return bool(voice and voice.play(max(0., min(1., volume)), self.schedule,
                                        seconds, self.now, fade_seconds))

    def play(self, name):
        now = self.now()
        cooldown = .10 if name in COLLISION_SOUNDS else (.04 if name == 'button' else 0)
        if now-self.last_play.get(name, float('-inf')) < cooldown:
            return False
        if self._play_pool(self.pools.get(name, []), self.effects_volume):
            self.last_play[name] = now
            return True
        return False

    def stop_effect(self, name):
        for voice in self.pools.get(name, []):
            voice.stop()

    def set_effects_volume(self, value):
        self.effects_volume = max(0., min(1., value))
        for pool in self.pools.values():
            for voice in pool:
                try:
                    voice.sound.volume = self.effects_volume
                except Exception:
                    pass

    def create_session(self, teams=(), store=None):
        session = MatchAudio(self, teams, store)
        self.sessions.append(session)
        return session

    def close(self):
        for session in list(self.sessions):
            session.close()
        for pool in self.pools.values():
            for voice in pool:
                voice.close()


class MatchAudio:
    def __init__(self, manager, teams, store):
        self.manager = manager
        self.music = {}
        self.round_id, self.last_event = None, 0
        self.closed = False
        for team in teams:
            path = store.asset_path(team.get('music', '')) if store else None
            self.music[team['name']] = manager._load_pool(path, 2) if path else []

    def goal(self, team):
        self.manager.play('goal')
        return self.manager._play_pool(self.music.get(team, []), self.manager.music_volume,
                                       self.manager.music_seconds, reuse=True,
                                       fade_seconds=self.manager.music_fade_seconds)

    def stop_team(self, team):
        for voice in self.music.get(team, []):
            voice.stop()

    def stop(self):
        for team in self.music:
            self.stop_team(team)
        for name in SOUND_FILES:
            if name != 'button':
                self.manager.stop_effect(name)
        self.manager.last_play.clear()

    def update(self, engine):
        if self.closed:
            return
        if self.round_id != engine.round_id:
            self.stop()
            self.round_id, self.last_event = engine.round_id, 0
            if engine.state == 'countdown':
                self.manager.play('countdown')
        for serial, kind, x, y, team in engine.events:
            if serial <= self.last_event:
                continue
            self.last_event = serial
            if kind == 'goal':
                self.goal(team)
            elif kind in ('start', 'end'):
                self.manager.stop_effect('countdown')
                self.manager.play(kind)
            elif kind in COLLISION_SOUNDS or kind in ('yellow_card', 'red_card'):
                self.manager.play(kind)

    def close(self):
        if self.closed:
            return
        self.stop()
        for pool in self.music.values():
            for voice in pool:
                voice.close()
        self.closed = True
        if self in self.manager.sessions:
            self.manager.sessions.remove(self)


def play_button_sound(*args):
    """Shared button hook; screens/tests can run without an audio device."""
    from kivy.app import App
    app = App.get_running_app()
    manager = getattr(app, 'audio', None)
    if manager:
        manager.play('button')
