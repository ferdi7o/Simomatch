"""Runtime-only visual isolation; deliberately separate from match/team settings."""
from dataclasses import dataclass
import json
from pathlib import Path
from uuid import uuid4

TARGETS = ('fire_arena', 'electric_blue')
MODES = ('BASE ONLY', 'IMAGE ONLY', 'IMAGE + RASTER', 'IMAGE + EFFECT', 'FULL')
RENDERERS = ('auto', 'texture', 'custom', 'flat_probe')


@dataclass(frozen=True)
class GraphicsSelection:
    mode: int | None = None
    renderer: str = 'auto'


@dataclass(frozen=True)
class GraphicsPlan:
    active: bool = False
    mode: int = 4
    image: bool = True
    common: bool = True
    effect: bool = True
    baseline: bool = False

    @property
    def simple_image(self):
        return self.active and self.image and not self.common


def plan_for(theme, selection=None):
    if theme not in TARGETS or selection is None or selection.mode is None:
        return GraphicsPlan()
    mode = selection.mode
    if type(mode) is not int or not 0 <= mode <= 4:
        raise ValueError('Graphics probe mode must be 0..4')
    return GraphicsPlan(True, mode, mode != 0, mode in (2,4), mode in (3,4), mode < 4)


class GraphicsProbeSettings:
    """Small independent atomic file. A crash must not lose the chosen test mode."""
    def __init__(self, directory):
        self.path = Path(directory)/'graphics_probe.json'
        try:
            data = json.loads(self.path.read_text(encoding='utf8'))
        except (OSError, ValueError):
            data = {}
        self.data = data if isinstance(data,dict) else {}

    def selection(self, theme):
        value = self.data.get(theme, {}) if theme in TARGETS else {}
        if not isinstance(value,dict): value = {}
        mode = value.get('mode')
        if type(mode) is not int or not 0 <= mode <= 4: mode = None
        renderer = value.get('renderer','auto')
        if renderer not in RENDERERS: renderer = 'auto'
        return GraphicsSelection(mode,renderer)

    def save(self, theme, mode, renderer='auto'):
        if theme not in TARGETS or (mode is not None and (type(mode) is not int or not 0 <= mode <= 4)):
            raise ValueError('Invalid graphics isolation selection')
        if renderer not in RENDERERS: raise ValueError('Invalid effect renderer')
        data = dict(self.data)
        data[theme] = dict(mode=mode,renderer=renderer)
        temporary = self.path.with_name('.graphics_probe_'+uuid4().hex+'.tmp')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary.write_text(json.dumps(data),encoding='utf8')
            temporary.replace(self.path)
            self.data = data
        finally:
            temporary.unlink(missing_ok=True)
