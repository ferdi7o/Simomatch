"""Optional raster/sprite ring layers. No procedural 'realistic' fire/lightning.

Artists supply transparent full-ring PNG/WebP atlases. Textures and up to 64
frame regions are loaded once; at most 3 meshes render, with a live goal gap.
"""
from math import sin, cos, pi, radians
from pathlib import Path
from kivy.graphics import Color, Mesh
from services.media import load_texture


class ArenaLayers:
    MAX_LAYERS = 3
    MAX_FRAMES = 64
    MAX_ATLAS_EDGE = 4096
    MAX_ATLAS_PIXELS = 4*1024*1024
    SEGMENTS = 96

    def __init__(self, definitions=(), loader=load_texture, root=None):
        self.time = 0.
        self.loaded, self.missing_assets, self.diagnostics = [], [], {}
        self.layer_colors = []
        root = Path(root or Path(__file__).resolve().parents[1])
        self.indices = [j for i in range(self.SEGMENTS)
                        for j in (2*i, 2*i+1, 2*i+2, 2*i+1, 2*i+3, 2*i+2)]
        for definition in definitions[:self.MAX_LAYERS]:
            path = root / definition.image
            try:
                if path.suffix.lower() not in ('.png', '.webp'):
                    raise ValueError('Efekt katmanı PNG/WebP olmalıdır.')
                if (not all(isinstance(n, int) and n > 0 for n in (definition.columns, definition.rows, definition.frames))
                        or definition.frames > min(self.MAX_FRAMES, definition.columns*definition.rows)
                        or definition.fps <= 0 or not 0 < definition.inner_scale < definition.outer_scale <= 1.3):
                    raise ValueError('Geçersiz atlas veya görsel ölçek ayarı.')
                texture = loader(path)
                if texture is None:
                    raise ValueError('Efekt görseli bulunamadı veya çözülemedi.')
                if max(texture.size) > self.MAX_ATLAS_EDGE or texture.width*texture.height > self.MAX_ATLAS_PIXELS:
                    raise ValueError('Efekt atlası en fazla 4096 kenar ve 4 megapiksel olmalıdır.')
                if texture.width % definition.columns or texture.height % definition.rows:
                    raise ValueError('Atlas ölçüleri satır/sütun sayısına bölünmelidir.')
                width, height = texture.width//definition.columns, texture.height//definition.rows
                if definition.source_radius_pixels < 0 or (definition.source_center_pixels and
                        (len(definition.source_center_pixels) != 2 or
                         not 0 <= definition.source_center_pixels[0] < width or
                         not 0 <= definition.source_center_pixels[1] < height)):
                    raise ValueError('Geçersiz kaynak halka kalibrasyonu.')
                frames = tuple(texture.get_region((i % definition.columns)*width,
                               (definition.rows-1-i//definition.columns)*height, width, height)
                               for i in range(definition.frames))
                color = Color(1, 1, 1, max(0, min(1, definition.opacity)))
                mesh = Mesh(vertices=[], indices=self.indices, texture=frames[0], mode='triangles')
                self.loaded.append((definition, mesh, frames))
                self.layer_colors.append(color)
            except Exception as exc:
                self.missing_assets.append(str(path))
                self.diagnostics[str(path)] = str(exc)

    def advance(self, dt):
        self.time += max(0., dt)

    def layout(self, goal, project):
        """Read geometry only; omit the exact physical opening from every mesh."""
        start = goal.angle+goal.half_angle
        length = 2*pi-2*goal.half_angle
        for (definition, mesh, frames), color in zip(self.loaded, self.layer_colors):
            mesh.texture = frames[int(self.time*definition.fps) % len(frames)]
            uv = mesh.texture.tex_coords
            phase = radians(definition.rotation_degrees)*self.time
            pulse = max(0., min(1., definition.pulse_depth))
            color.a = max(0., min(1., definition.opacity))*(1-pulse*.5+pulse*.5*sin(self.time*2*pi*definition.pulse_hz))
            width, height = mesh.texture.size
            source_radius = definition.source_radius_pixels or min(width, height)*.5/definition.outer_scale
            center_x, center_y = definition.source_center_pixels or (width/2, height/2)
            vertices = []
            for i in range(self.SEGMENTS+1):
                angle = start+length*i/self.SEGMENTS
                for scale in (definition.inner_scale, definition.outer_scale):
                    x, y = project(goal.radius*scale*cos(angle), goal.radius*scale*sin(angle))
                    # Uniform source-pixel scale: transparent margins and a
                    # non-square texture must never stretch the physical ring.
                    u = (center_x+source_radius*scale*cos(angle-phase))/width
                    v = 1-(center_y-source_radius*scale*sin(angle-phase))/height
                    # Atlas regions may have flipped UV coordinates.
                    tu = (1-v)*((1-u)*uv[0]+u*uv[2])+v*((1-u)*uv[6]+u*uv[4])
                    tv = (1-v)*((1-u)*uv[1]+u*uv[3])+v*((1-u)*uv[7]+u*uv[5])
                    vertices.extend((x, y, tu, tv))
            mesh.vertices = vertices
