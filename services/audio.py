"""Preloaded independent Kivy Sound voices; no file reads on collision paths.

Each pool slot owns its own Sound instance (SDL2 mixer channel). A busy effect
pool drops an extra hit rather than restarting an in-flight sound. Team music
uses separate per-team pools, music-only fades and generation-safe stop callbacks.
"""
from pathlib import Path
from time import monotonic
from math import isfinite
import logging
from services.music_backend import can_seek, max_music_start

log = logging.getLogger(__name__)

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
        self.seek_timer = None
        self.seek_status = "idle"
        self.error = ""

    def stop(self):
        self.generation += 1
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.seek_timer:
            self.seek_timer.cancel()
            self.seek_timer = None
        if self.fade_timer:
            self.fade_timer.cancel()
            self.fade_timer = None
        try:
            # Android MediaPlayer.stop() calls prepare(); never do that for an
            # already idle, preloaded effect before each collision playback.
            if self.busy or self.seek_status == 'pending':
                self.sound.stop()
            self.sound.state = 'stop'
        except Exception:
            pass
        if self.seek_status == 'pending':
            self.seek_status = 'stopped'

    def play(self, volume, schedule, seconds=None, now=monotonic, fade_seconds=0.,
             start_seconds=0., on_error=None):
        self.stop()
        self.error, self.seek_status = '', 'idle'
        generation = self.generation

        def fail(exc):
            self.stop()  # Abort a muted, pending seek as well as audible playback.
            self.error, self.seek_status = str(exc), 'failed'
            log.warning('Music playback/seek failed: %s', exc)
            if on_error:
                on_error(str(exc))
            return False

        def begin():
            started = now()
            self.sound.volume = volume
            if seconds is None:
                return
            fade_duration = max(0., min(fade_seconds, seconds))
            def expire(dt):
                if generation == self.generation:
                    try:
                        if fade_duration:
                            self.sound.volume = 0.
                    except Exception as exc:
                        log.warning('Could not finish music fade: %s', exc)
                    finally:
                        self.stop()
            self.timer = schedule(expire, seconds)
            if fade_duration:
                fade_start = seconds-fade_duration
                def fade(dt):
                    if generation != self.generation or not self.busy:
                        return
                    progress = max(0., min(1., (now()-started-fade_start)/fade_duration))
                    try:
                        self.sound.volume = volume*(1-progress*progress*(3-2*progress))
                    except Exception as exc:
                        fail(exc)
                        return
                    if progress >= 1:
                        self.stop()
                    else:
                        self.fade_timer = schedule(fade, 1/60)
                self.fade_timer = schedule(fade, fade_start)

        try:
            if not isfinite(start_seconds) or start_seconds < 0:
                raise ValueError('Invalid music start time')
            if seconds is not None:
                length = float(self.sound.length)
                if start_seconds > max_music_start(length, seconds)+1e-6:
                    raise ValueError('Music start exceeds the available clip length')
                seconds = min(seconds, length-start_seconds)
            needs_seek = bool(start_seconds or getattr(self.sound, 'requires_seek_verification', False))
            self.sound.volume = 0. if needs_seek else volume
            self.sound.play()
            if needs_seek:
                if not can_seek(self.sound) or not callable(getattr(self.sound, 'get_pos', None)):
                    raise RuntimeError('This audio provider cannot perform verified seek')
                self.seek_status = 'pending'
                self.sound.seek(start_seconds)
                requested = now()
                def check_seek(dt=0):
                    if generation != self.generation:
                        return
                    try:
                        if getattr(self.sound, 'seek_error', ''):
                            raise RuntimeError(self.sound.seek_error)
                        position = float(self.sound.get_pos())
                        # Verify position, not just an exception-free seek call.
                        elapsed = 0. if getattr(self.sound, 'seeks_paused', False) else now()-requested
                        if (getattr(self.sound, 'seek_ready', True)
                                and abs(position-start_seconds-elapsed) <= .3):
                            self.seek_status = 'verified'
                            resume = getattr(self.sound, 'resume_after_seek', None)
                            if resume:
                                resume()
                            begin()
                        elif now()-requested >= 1.5:
                            fail(RuntimeError('Seek position was not reached'))
                        else:
                            self.seek_timer = schedule(check_seek, .03)
                    except Exception as exc:
                        fail(exc)
                check_seek()
            else:
                begin()
            return self.seek_status != 'failed'
        except Exception as exc:
            return fail(exc)

    @property
    def busy(self):
        try:
            return self.seek_status == 'pending' or self.sound.state == 'play'
        except Exception:
            return False

    def close(self):
        self.stop()
        try:
            self.sound.unload()
        except Exception:
            pass


class AudioManager:
    def __init__(self, sounds_dir=None, loader=None, schedule=None, now=monotonic, music_loader=None):
        injected_loader = loader is not None
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
        if music_loader is None and not injected_loader:
            from services.music_backend import load_music
            music_loader = lambda path: load_music(path, loader)
        self.music_loader = music_loader or loader
        self.preview_pool, self.preview_path = [], ""
        self.root = Path(sounds_dir or Path(__file__).resolve().parents[1] / 'assets' / 'sounds')
        self.effects_volume, self.music_volume = .32, .28
        self.music_seconds = 5.
        self.music_fade_seconds = 1.5
        self.pools, self.last_play, self.diagnostics = {}, {}, {}
        self.sessions = []
        for name, filename in SOUND_FILES.items():
            self.pools[name] = self._load_pool(self.root / filename, 3 if name in COLLISION_SOUNDS else 2)
        self._configure_mixer_channels()

    def _configure_mixer_channels(self):
        # SDL_mixer can default to only 8 channels. Reserve capacity for the
        # existing bounded voice pools, including cards + concurrent goals.
        if not any(type(v.sound).__module__.endswith('audio_sdl2') for pool in self.pools.values() for v in pool):
            return
        import ctypes
        for library in ('SDL2_mixer.dll', 'libSDL2_mixer.so', 'libSDL2_mixer.dylib'):
            try:
                mixer = ctypes.CDLL(library)
                mixer.Mix_AllocateChannels.argtypes = [ctypes.c_int]
                mixer.Mix_AllocateChannels.restype = ctypes.c_int
                if mixer.Mix_AllocateChannels(-1) < 32:
                    mixer.Mix_AllocateChannels(32)
                return
            except (OSError, AttributeError):
                continue

    def _load_pool(self, path, count, music=False):
        if not path or not Path(path).is_file():
            self.diagnostics[str(path)] = 'Dosya bulunamadı'
            return []
        voices = []
        for _ in range(count):
            try:
                sound = (self.music_loader if music else self.loader)(str(path))
                if sound is not None:
                    if not isfinite(float(sound.length)) or sound.length <= 0:
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

    def _play_pool(self, pool, volume, seconds=None, reuse=False, fade_seconds=0., start_seconds=0.):
        voice = next((v for v in pool if not v.busy), None)
        if voice is None and pool and reuse:
            voice = pool[0]  # Only steals a voice from the same team's pool.
        return bool(voice and voice.play(max(0., min(1., volume)), self.schedule,
                                        seconds, self.now, fade_seconds, start_seconds,
                                        lambda message: self.diagnostics.update(music=message)))

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

    def prepare_preview(self, path):
        if str(path or '') != self.preview_path:
            self.stop_preview(unload=True)
            self.preview_path = str(path or '')
            self.preview_pool = self._load_pool(path, 1, music=True) if path else []
        return self.preview_pool[0].sound.length if self.preview_pool else 0.

    def preview_music(self, path, start_seconds=0.):
        self.prepare_preview(path)
        self.stop_preview()
        return self._play_pool(self.preview_pool, self.music_volume, self.music_seconds,
                               fade_seconds=self.music_fade_seconds, start_seconds=start_seconds)

    def stop_preview(self, unload=False):
        for voice in self.preview_pool:
            voice.close() if unload else voice.stop()
        if unload:
            self.preview_pool, self.preview_path = [], ''

    def create_session(self, teams=(), store=None):
        session = MatchAudio(self, teams, store)
        self.sessions.append(session)
        return session

    def close(self):
        self.stop_preview(unload=True)
        for session in list(self.sessions):
            session.close()
        for pool in self.pools.values():
            for voice in pool:
                voice.close()


class MatchAudio:
    def __init__(self, manager, teams, store):
        self.manager = manager
        self.music, self.music_starts = {}, {}
        self.round_id, self.last_event = None, 0
        self.closed = False
        self.defer_cards = False
        for team in teams:
            path = store.asset_path(team.get('music', '')) if store else None
            self.music[team['name']] = manager._load_pool(path, 2, music=True) if path else []
            self.music_starts[team['name']] = team.get('goal_music_start_seconds', 0.)

    def goal(self, team):
        self.manager.play('goal')
        return self.manager._play_pool(self.music.get(team, []), self.manager.music_volume,
                                       self.manager.music_seconds, reuse=True,
                                       fade_seconds=self.manager.music_fade_seconds,
                                       start_seconds=self.music_starts.get(team, 0.))

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
            elif kind in ('yellow_card', 'red_card'):
                if not self.defer_cards:
                    self.manager.play(kind)
            elif kind in COLLISION_SOUNDS:
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
