"""Seekable independent MP3 voices without changing collision/effect providers."""
from math import isfinite
from pathlib import Path
import logging

log = logging.getLogger(__name__)


def max_music_start(length, seconds=5.):
    return max(0., float(length)-seconds) if isfinite(float(length)) else 0.


class AndroidMusic:
    supports_seek = True
    requires_seek_verification = True
    seeks_paused = True

    def __init__(self, path):
        from jnius import autoclass, PythonJavaClass, java_method
        self.path, self._state, self._volume = str(path), 'stop', .28
        self.player = autoclass('android.media.MediaPlayer')()
        self._seek_pending, self._queued_seek, self.released = False, None, False
        self.seek_error = ''
        class Completion(PythonJavaClass):
            __javainterfaces__ = ['android/media/MediaPlayer$OnSeekCompleteListener']
            __javacontext__ = 'app'
            def __init__(self, owner):
                super().__init__()
                self.owner = owner
            @java_method('(Landroid/media/MediaPlayer;)V')
            def onSeekComplete(self, player):
                owner = self.owner
                if owner and not owner.released:
                    try:
                        owner._seek_complete()
                    except Exception as exc:
                        owner.seek_error = str(exc)
                        log.warning('MediaPlayer seek callback failed: %s', exc)
        self.listener = Completion(self)
        try:
            self.player.setDataSource(self.path)
            self.player.prepare()
            self.length = self.player.getDuration()/1000.
            self.sdk = autoclass('android.os.Build$VERSION').SDK_INT
            self.player.setOnSeekCompleteListener(self.listener)
        except Exception:
            self.player.release()
            raise
        self.loop = False

    @property
    def state(self):
        return 'play' if self._state == 'play' and self.player.isPlaying() else 'stop'

    @state.setter
    def state(self, value):
        self._state = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = float(value)
        self.player.setVolume(self._volume, self._volume)

    def play(self):
        self.player.setLooping(False)
        self.player.start()
        self._state = 'play'

    def seek(self, seconds):
        self.seek_error = ''
        if self._seek_pending:
            self._queued_seek = seconds  # Serialize seeks; old completion cannot confirm a new one.
        else:
            self._request_seek(seconds)

    @property
    def seek_ready(self):
        return not self._seek_pending

    def _seek_complete(self):
        if self._queued_seek is not None:
            target, self._queued_seek = self._queued_seek, None
            self._request_seek(target)
        else:
            self._seek_pending = False

    def _request_seek(self, seconds):
        millis = int(round(seconds*1000))
        self._seek_pending = True
        try:
            if self._state == 'play':
                self.player.pause()
            if self.sdk >= 26:
                self.player.seekTo(millis, 3)  # SEEK_CLOSEST, Java long milliseconds.
            else:
                self.player.seekTo(millis)
        except Exception:
            self._seek_pending = False
            raise

    def resume_after_seek(self):
        self.player.start()

    def get_pos(self):
        return self.player.getCurrentPosition()/1000.

    def stop(self):
        self._queued_seek = None
        if self._state == 'play':
            self.player.pause()
        self._state = 'stop'

    def unload(self):
        self.stop()
        self.released = True
        self.player.setOnSeekCompleteListener(None)
        self.listener.owner = None
        self.player.release()


class WindowsMusic:
    """Independent SDL_mixer PCM slices; SoundSDL2 itself has no seek method.

    Decode once on preload. A seek changes the frame-aligned PCM buffer view,
    not the shared SDL music channel; each voice gets its own sample channel.
    """
    supports_seek = True

    def __init__(self, path):
        import ctypes as c
        from time import monotonic
        self.c, self.now = c, monotonic
        class Chunk(c.Structure):
            _fields_ = [('allocated', c.c_int), ('abuf', c.POINTER(c.c_ubyte)),
                        ('alen', c.c_uint32), ('volume', c.c_ubyte)]
        ptr = c.POINTER(Chunk)
        self.sdl, self.mix = c.CDLL('SDL2.dll'), c.CDLL('SDL2_mixer.dll')
        self.sdl.SDL_RWFromFile.argtypes = [c.c_char_p, c.c_char_p]
        self.sdl.SDL_RWFromFile.restype = c.c_void_p
        self.mix.Mix_LoadWAV_RW.argtypes = [c.c_void_p, c.c_int]
        self.mix.Mix_LoadWAV_RW.restype = ptr
        self.mix.Mix_QuickLoad_RAW.argtypes = [c.POINTER(c.c_ubyte), c.c_uint32]
        self.mix.Mix_QuickLoad_RAW.restype = ptr
        self.mix.Mix_FreeChunk.argtypes = [ptr]
        self.mix.Mix_GetChunk.argtypes = [c.c_int]
        self.mix.Mix_GetChunk.restype = ptr
        self.mix.Mix_PlayChannelTimed.argtypes = [c.c_int, ptr, c.c_int, c.c_int]
        self.mix.Mix_PlayChannelTimed.restype = c.c_int
        self.mix.Mix_VolumeChunk.argtypes = [ptr, c.c_int]
        self.mix.Mix_QuerySpec.argtypes = [c.POINTER(c.c_int), c.POINTER(c.c_ushort), c.POINTER(c.c_int)]
        rate, fmt, channels = c.c_int(), c.c_ushort(), c.c_int()
        if not self.mix.Mix_QuerySpec(c.byref(rate), c.byref(fmt), c.byref(channels)):
            raise RuntimeError('SDL audio device is not initialized')
        self.rate, self.frame_bytes = rate.value, (fmt.value & 255)//8*channels.value
        self.path, self.view, self.channel = str(Path(path).resolve()), None, -1
        self.base = self.mix.Mix_LoadWAV_RW(self.sdl.SDL_RWFromFile(self.path.encode('utf-8'), b'rb'), 1)
        if not self.base:
            raise RuntimeError('SDL could not decode the MP3')
        self.length = self.base.contents.alen/(self.rate*self.frame_bytes)
        self._volume, self.offset, self.started, self.loop = .28, 0., 0., False

    @property
    def state(self):
        return 'play' if self.owns_channel() and self.mix.Mix_Playing(self.channel) else 'stop'

    def owns_channel(self):
        if self.channel < 0 or not self.view:
            return False
        current = self.mix.Mix_GetChunk(self.channel)
        return bool(current and self.c.addressof(current.contents) == self.c.addressof(self.view.contents))

    @state.setter
    def state(self, value):
        pass  # Voice.stop() already halts this voice's channel.

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = value
        if self.view:
            self.mix.Mix_VolumeChunk(self.view, round(value*128))

    def _start(self, seconds):
        self.stop()
        frame = int(seconds*self.rate)
        offset = frame*self.frame_bytes
        remaining = self.base.contents.alen-offset
        if remaining <= 0:
            raise ValueError('PCM offset is beyond the sound')
        address = self.c.addressof(self.base.contents.abuf.contents)+offset
        self.view = self.mix.Mix_QuickLoad_RAW(self.c.cast(address, self.c.POINTER(self.c.c_ubyte)), remaining)
        if not self.view:
            raise RuntimeError('SDL PCM view allocation failed')
        self.mix.Mix_VolumeChunk(self.view, round(self._volume*128))
        self.channel = self.mix.Mix_PlayChannelTimed(-1, self.view, 0, -1)
        if self.channel < 0:
            raise RuntimeError('No free SDL sample channel')
        self.offset, self.started = frame/self.rate, self.now()

    def play(self):
        self._start(0.)

    def seek(self, seconds):
        self._start(seconds)

    def get_pos(self):
        return min(self.length, self.offset+self.now()-self.started)

    def stop(self):
        if self.owns_channel():
            self.mix.Mix_HaltChannel(self.channel)
        self.channel = -1
        if self.view:
            self.mix.Mix_FreeChunk(self.view)
            self.view = None

    def unload(self):
        self.stop()
        if self.base:
            self.mix.Mix_FreeChunk(self.base)
            self.base = None


def load_music(path, fallback):
    from kivy.utils import platform
    if platform == 'android':
        return AndroidMusic(path)
    if platform == 'win':
        try:
            return WindowsMusic(path)
        except Exception:
            # Preserve zero-offset playback when native PCM access is unavailable.
            # Voice rejects nonzero offsets on a provider whose seek is a no-op.
            return fallback(path)
    return fallback(path)


def can_seek(sound):
    if hasattr(sound, 'supports_seek'):
        return sound.supports_seek
    method = getattr(sound, 'seek', None)
    if not callable(method):
        return False
    from kivy.core.audio import Sound
    return getattr(method, '__func__', None) is not Sound.seek
