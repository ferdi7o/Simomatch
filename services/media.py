"""Safe image loading. A missing/corrupt file produces a colored fallback."""
from pathlib import Path
from kivy.core.image import Image as CoreImage


def load_texture(path):
    if not path:
        return None
    try:
        path = Path(path)
        if not path.is_file() or path.stat().st_size > 32*1024*1024:
            return None
        image = CoreImage(str(path), nocache=True)
        if image.width > 8192 or image.height > 8192:
            return None
        return image.texture
    except Exception:
        return None
