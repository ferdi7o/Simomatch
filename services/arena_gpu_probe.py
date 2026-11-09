"""Packaged diagnostic controls. Normal production visuals remain the default."""
from dataclasses import dataclass, fields
from pathlib import Path
import json
from services.graphics_diagnostics import milestone


@dataclass(frozen=True)
class ArenaProbe:
    raster: bool = True
    fire: bool = True
    electric: bool = True
    custom_shader: bool = True
    trace: bool = False
    fire_renderer: str = 'auto'
    electric_renderer: str = 'auto'


def read_arena_probe(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[1]/'assets/arena_gpu_probe.json'
    try:
        data = json.loads(path.read_text(encoding='utf8'))
        values = {}
        if isinstance(data,dict):
            for f in fields(ArenaProbe):
                value = data.get(f.name)
                if f.name.endswith('_renderer'):
                    if value in ('auto','texture','custom'): values[f.name] = value
                elif type(value) is bool:
                    values[f.name] = value
        return ArenaProbe(**values)
    except (OSError, ValueError, TypeError):
        return ArenaProbe()


def particle_renderer(probe, effect, platform=None):
    if not probe.custom_shader:
        return 'flat_probe'  # Retain the explicit old diagnostic switch.
    if platform is None:
        from kivy.utils import platform
    choice = getattr(probe, effect+'_renderer')
    return ('texture' if platform == 'android' else 'custom') if choice == 'auto' else choice


def first_gpu_marker(event, **details):
    """Callback used only in trace builds: logs, never touches OpenGL state."""
    seen = False
    def mark(*_):
        nonlocal seen
        if not seen:
            seen = True
            milestone(event, **details)
    return mark
