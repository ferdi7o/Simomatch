"""Callback API: pick(kind, callback(path, error)). No audio playback here."""
from pathlib import Path
from uuid import uuid4
import os


class DesktopFilePicker:
    def pick(self, kind, callback):
        try:
            selected = self._select(kind)
        except Exception as exc:
            callback(None, f'Dosya seçici açılamadı: {exc}')
            return
        callback(selected or None, '')

    def _select(self, kind):
        return self._windows_dialog(kind) if os.name == 'nt' else self._tk_dialog(kind)

    @staticmethod
    def _windows_dialog(kind):
        """Native Unicode picker; no Tcl/Tk installation required on Windows."""
        import ctypes as c
        from ctypes import wintypes as w
        class OpenFileName(c.Structure):
            _fields_ = [
                ('lStructSize', w.DWORD), ('hwndOwner', w.HWND), ('hInstance', w.HINSTANCE),
                ('lpstrFilter', w.LPCWSTR), ('lpstrCustomFilter', w.LPWSTR),
                ('nMaxCustFilter', w.DWORD), ('nFilterIndex', w.DWORD),
                ('lpstrFile', w.LPWSTR), ('nMaxFile', w.DWORD), ('lpstrFileTitle', w.LPWSTR),
                ('nMaxFileTitle', w.DWORD), ('lpstrInitialDir', w.LPCWSTR),
                ('lpstrTitle', w.LPCWSTR), ('Flags', w.DWORD), ('nFileOffset', w.WORD),
                ('nFileExtension', w.WORD), ('lpstrDefExt', w.LPCWSTR),
                ('lCustData', w.LPARAM), ('lpfnHook', c.c_void_p), ('lpTemplateName', w.LPCWSTR),
                ('pvReserved', c.c_void_p), ('dwReserved', w.DWORD), ('FlagsEx', w.DWORD)]
        buffer = c.create_unicode_buffer(32768)
        options = OpenFileName()
        options.lStructSize = c.sizeof(OpenFileName)
        user = c.WinDLL('user32', use_last_error=True)
        user.GetActiveWindow.restype = w.HWND
        options.hwndOwner = user.GetActiveWindow()
        options.lpstrFile = c.cast(buffer, w.LPWSTR)
        options.nMaxFile = len(buffer)
        options.lpstrFilter = ('PNG / JPG\0*.png;*.jpg;*.jpeg\0\0' if kind == 'image'
                              else 'MP3\0*.mp3\0\0')
        options.nFilterIndex = 1
        options.lpstrTitle = 'Dosya seç'
        options.Flags = 0x80000 | 0x1000 | 0x800 | 0x8 | 0x4
        dialog = c.WinDLL('comdlg32', use_last_error=True)
        dialog.GetOpenFileNameW.argtypes = [c.POINTER(OpenFileName)]
        dialog.GetOpenFileNameW.restype = w.BOOL
        if dialog.GetOpenFileNameW(c.byref(options)):
            return buffer.value
        error = dialog.CommDlgExtendedError()
        if error:
            raise OSError(f'Windows dosya seçici hatası: {error}')
        return None

    @staticmethod
    def _tk_dialog(kind):
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        try:
            root.withdraw()
            types = [('Takım görseli', '*.png *.jpg *.jpeg')] if kind == 'image' else [('Gol müziği', '*.mp3')]
            return filedialog.askopenfilename(title='Dosya seç', filetypes=types)
        finally:
            root.destroy()


class AndroidFilePicker:
    """Storage Access Framework adapter; imports are deferred until Android use.

    A content:// URI is copied immediately to private staging storage. It is
    never treated as a filesystem path. Needs python-for-android + pyjnius.
    """
    request_code = 7031

    def __init__(self, data_dir):
        self.staging = Path(data_dir) / 'imports'
        self.pending = None

    def pick(self, kind, callback):
        if self.pending:
            callback(None, 'Dosya seçimi zaten açık.')
            return
        try:
            from android import activity
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType('image/*' if kind == 'image' else 'audio/mpeg')
            self.pending = (kind, callback)
            activity.bind(on_activity_result=self._result)
            autoclass('org.kivy.android.PythonActivity').mActivity.startActivityForResult(intent, self.request_code)
        except Exception as exc:
            self.pending = None
            try:
                from android import activity
                activity.unbind(on_activity_result=self._result)
            except (ImportError, AttributeError):
                pass
            callback(None, f'Android dosya seçimi kullanılamıyor: {exc}')

    def _result(self, request, result, intent):
        if request != self.request_code or not self.pending:
            return
        from android import activity
        from kivy.clock import Clock
        from jnius import autoclass
        activity.unbind(on_activity_result=self._result)
        kind, callback = self.pending
        self.pending = None
        path, error = None, ''
        source = target = channel = None
        destination = None
        try:
            if result == -1 and intent is not None:
                resolver = autoclass('org.kivy.android.PythonActivity').mActivity.getContentResolver()
                uri = intent.getData()
                mime = str(resolver.getType(uri))
                suffix = { 'image/png': '.png', 'image/jpeg': '.jpg', 'audio/mpeg': '.mp3' }.get(mime)
                if not suffix or (kind == 'image') != mime.startswith('image/'):
                    raise ValueError('PNG/JPG veya MP3 dosyası seçin.')
                self.staging.mkdir(parents=True, exist_ok=True)
                destination = self.staging / (uuid4().hex + suffix)
                source = resolver.openInputStream(uri)
                target = autoclass('java.io.FileOutputStream')(str(destination))
                channel = autoclass('java.nio.channels.Channels').newChannel(source)
                output = target.getChannel()
                count = 0
                while count <= 32*1024*1024:
                    transferred = output.transferFrom(channel, count, 1024*1024)
                    if transferred == 0:
                        break
                    count += transferred
                if count > 32*1024*1024:
                    raise ValueError('Dosya 32 MB sınırını aşıyor.')
                path = str(destination)
        except Exception as exc:
            error = f'Dosya okunamadı: {exc}'
        finally:
            for stream in (channel, source, target):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
            if error and destination:
                destination.unlink(missing_ok=True)
        Clock.schedule_once(lambda dt: callback(path, error), 0)


def create_file_picker(platform, data_dir):
    return AndroidFilePicker(data_dir) if platform == 'android' else DesktopFilePicker()
