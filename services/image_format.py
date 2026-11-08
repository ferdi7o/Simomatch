"""Small, dependency-free image signature reader for Python 3.10+.

This identifies the container, not the integrity of every compressed pixel.
Background import/discovery still asks Kivy to decode the image afterwards.
No file names or extensions are used to decide the detected format.
"""
from pathlib import Path


def image_format(path):
    """Return 'png', 'jpeg', 'webp', or None; read at most 32 bytes."""
    try:
        with Path(path).open('rb') as stream:
            header = stream.read(32)
    except (OSError, ValueError, TypeError):
        return None

    if (len(header) >= 24 and header[:8] == b'\x89PNG\r\n\x1a\n'
            and header[8:16] == b'\0\0\0\rIHDR'
            and int.from_bytes(header[16:20], 'big') > 0
            and int.from_bytes(header[20:24], 'big') > 0):
        return 'png'
    # SOI followed by a marker; supports JFIF, Exif and tables-first JPEGs.
    if len(header) >= 4 and header[:3] == b'\xff\xd8\xff':
        marker = next((value for value in header[3:] if value != 0xff), None)
        if marker is not None and marker not in (0x00, 0xd8, 0xd9):
            return 'jpeg'
    # RIFF alone is also used by WAV/AVI. Require WEBP and a known image chunk.
    if (len(header) >= 20 and header[:4] == b'RIFF' and header[8:12] == b'WEBP'
            and header[12:16] in (b'VP8 ', b'VP8L', b'VP8X')
            and int.from_bytes(header[4:8], 'little') >= 12
            and int.from_bytes(header[16:20], 'little') > 0):
        return 'webp'
    return None
