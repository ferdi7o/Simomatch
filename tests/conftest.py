"""Keep all test/runtime output within the project workspace."""
import os
from pathlib import Path
import struct
import zlib
import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ['KIVY_HOME'] = str(ROOT / '.kivy_runtime')
os.environ['KIVY_NO_ARGS'] = '1'


@pytest.fixture
def png_file(tmp_path):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind+data) & 0xffffffff)
    width, height = 48, 32
    rows = b''.join(b'\0' + bytes([160, 70, 240, 255])*width for _ in range(height))
    data = b'\x89PNG\r\n\x1a\n'
    data += chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 6, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
    path = tmp_path / 'logo.png'
    path.write_bytes(data)
    return path
