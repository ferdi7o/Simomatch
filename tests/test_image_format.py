"""No optional image libraries or removed standard modules required."""
import ast
import os
from pathlib import Path
import struct
import subprocess
import sys
import textwrap
import pytest
from services.image_format import image_format

ROOT = Path(__file__).resolve().parents[1]
# PEP 594 / 3.13 removals, tkinter.tix, and earlier 3.12 removals
# that also cannot be used on the target Python 3.14 runtime.
REMOVED = set('aifc audioop cgi cgitb chunk crypt imghdr mailcap msilib nis nntplib '
              'ossaudiodev pipes sndhdr spwd sunau telnetlib uu xdrlib lib2to3 '
              'imp distutils asyncore asynchat'.split()) | {'tkinter.tix'}


def test_real_png_is_detected_from_content_even_with_wrong_extension(png_file, tmp_path):
    assert image_format(png_file) == 'png'
    disguised = tmp_path/'wrong.jpg'
    disguised.write_bytes(png_file.read_bytes())
    assert image_format(disguised) == 'png'


@pytest.mark.parametrize('marker,payload', [(b'\xff\xe0', b'JFIF\0'), (b'\xff\xe1', b'Exif\0\0'),
                                          (b'\xff\xdb', b'\0'*12), (b'\xff\xff\xdb', b'\0'*12)])
def test_jpeg_signatures_support_jfif_exif_and_no_app_marker(tmp_path, marker, payload):
    path = tmp_path/'jpeg.bin'
    path.write_bytes(b'\xff\xd8'+marker+b'\0\x10'+payload)
    assert image_format(path) == 'jpeg'


@pytest.mark.parametrize('chunk', [b'VP8 ', b'VP8L', b'VP8X'])
def test_webp_container_requires_known_image_chunk(tmp_path, chunk):
    path = tmp_path/'image.webp'
    path.write_bytes(b'RIFF'+struct.pack('<I', 20)+b'WEBP'+chunk+struct.pack('<I', 8)+b'\0'*8)
    assert image_format(path) == 'webp'


@pytest.mark.parametrize('header', [b'', b'\x89PNG', b'\x89PNG\r\n\x1a\n', b'GIF89a'+b'\0'*30,
                                    b'\xff\xd8', b'\xff\xd8\xff', b'\xff\xd8\xff\0',
                                    b'\xff\xd8\xff\xd9', b'RIFF'+b'\0'*4+b'WAVEfmt '+b'\0'*12,
                                    b'RIFF'+b'\0'*4+b'WEBPVP8 '+b'\0'*12,
                                    b'RIFF'+struct.pack('<I', 30)+b'WEBPFAKE'+b'\0'*12])
def test_invalid_unknown_and_truncated_signatures_return_none(tmp_path, header):
    path = tmp_path/'looks_valid.png'
    path.write_bytes(header)
    assert image_format(path) is None


def test_png_header_must_have_ihdr_and_nonzero_dimensions(tmp_path, png_file):
    path = tmp_path/'bad.png'
    data = bytearray(png_file.read_bytes())
    data[12:16] = b'FAKE'
    path.write_bytes(data)
    assert image_format(path) is None
    data = bytearray(png_file.read_bytes())
    data[16:20] = b'\0'*4
    path.write_bytes(data)
    assert image_format(path) is None


def test_missing_directory_and_unreadable_paths_are_safe(tmp_path, monkeypatch):
    assert image_format(tmp_path/'missing.png') is None
    assert image_format(tmp_path) is None
    assert image_format(None) is None
    def denied(*args, **kwargs):
        raise PermissionError('test access denied')
    monkeypatch.setattr(Path, 'open', denied)
    assert image_format(tmp_path/'private.png') is None


def test_signature_reader_never_reads_the_whole_image(png_file, monkeypatch):
    header = png_file.read_bytes()[:32]
    calls = []
    class Stream:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            calls.append(size)
            return header
    monkeypatch.setattr(Path, 'open', lambda *args, **kwargs: Stream())
    assert image_format('any.png') == 'png'
    assert calls == [32]


def test_fake_extension_is_rejected_by_all_image_import_paths(tmp_path):
    from services.backgrounds import BackgroundPreferences
    from services.custom_backgrounds import CustomBackgroundStore
    from services.team_store import TeamStore
    path = tmp_path/'renamed.png'
    path.write_bytes(b'GIF89a'+b'\0'*40)
    for save in (lambda: BackgroundPreferences(tmp_path/'legacy').import_image(path),
                 lambda: CustomBackgroundStore(tmp_path/'app').add(path),
                 lambda: TeamStore(tmp_path/'teams').save('Wrong format', logo=path)):
        with pytest.raises(ValueError):
            save()
    assert path.exists()


def test_header_only_corrupt_png_still_fails_background_decoder(tmp_path, png_file):
    from kivy.base import EventLoop
    from services.custom_backgrounds import CustomBackgroundStore
    EventLoop.ensure_window()
    path = tmp_path/'truncated.png'
    path.write_bytes(png_file.read_bytes()[:32])
    assert image_format(path) == 'png'  # Signature is not a full integrity check.
    store = CustomBackgroundStore(tmp_path/'app')
    with pytest.raises(ValueError):
        store.add(path)
    assert store.rows == []


def project_sources():
    yield from ROOT.glob('*.py')
    for name in ('services', 'screens', 'engine', 'tools', 'tests'):
        yield from (ROOT/name).rglob('*.py')


def test_project_has_no_direct_imports_of_removed_standard_modules():
    violations = []
    for path in project_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]+[node.module+'.'+alias.name for alias in node.names]
            elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
                if ((isinstance(node.func, ast.Name) and node.func.id == '__import__') or
                        (isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module')):
                    names = [node.args[0].value] if isinstance(node.args[0].value, str) else []
            for name in names:
                if name in REMOVED or name.split('.')[0] in REMOVED:
                    violations.append(f'{path.relative_to(ROOT)}:{node.lineno}: {name}')
    assert not violations, '\n'.join(violations)


def test_android_import_chain_works_when_removed_modules_are_unavailable(tmp_path, png_file):
    # Fresh interpreter prevents cached imports from concealing an accidental
    # dependency; this simulates missing modules, not a real Python 3.14 device.
    script = textwrap.dedent('''
        import sys
        from pathlib import Path
        class MissingModules:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in REMOVED or fullname == 'tkinter.tix':
                    raise ModuleNotFoundError('Removed standard module: '+fullname)
        sys.meta_path.insert(0, MissingModules())
        import main
        from services.team_store import TeamStore
        from services.custom_backgrounds import CustomBackgroundStore
        from screens.router import AppRouter
        directory, image = Path(sys.argv[1]), Path(sys.argv[2])
        teams = TeamStore(directory/'teams')
        teams.save('A', logo=image)
        teams.save('B')
        library = CustomBackgroundStore(directory/'app')
        library.add(image)
        root = AppRouter(teams, None, background_data_dir=directory/'app')
        root.go('setup')
        assert len(root.get_screen('setup').custom_tiles) == 1
        root.dispose()
        print('REMOVED_MODULE_STARTUP_OK')
    ''')
    script = 'REMOVED = '+repr(REMOVED)+'\n'+script
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), str(png_file)],
                            cwd=ROOT, env=dict(os.environ), capture_output=True, text=True,
                            errors='replace', timeout=60)
    assert result.returncode == 0, result.stdout+'\n'+result.stderr
    assert 'REMOVED_MODULE_STARTUP_OK' in result.stdout
