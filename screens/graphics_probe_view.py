"""Minimal unmasked image reference and CPU audits for controlled diagnosis.

No manual FBO, stencil, custom shader or Mesh is introduced by the reference.
The stock Image widget owns its normal KV canvas (including its internal stencil).
All normal scene masking and production rendering stay in their existing paths.
"""
from math import isfinite
from pathlib import Path
from kivy.graphics import Callback
from kivy.uix.image import Image
from services.media import load_texture
from services.graphics_diagnostics import milestone
from services.arena_gpu_probe import first_gpu_marker
from screens.mesh_safety import MeshGuard, validate_mesh


def check_texture(texture):
    if texture is None:
        return 'default/inherited'
    if len(texture.size) != 2 or any(not isfinite(v) or v <= 0 for v in texture.size):
        raise ValueError('Nonpositive/nonfinite texture dimensions')
    uv = texture.tex_coords
    if len(uv) != 8 or not all(isfinite(v) for v in uv):
        raise ValueError('Invalid texture UV coordinates')
    # Never inspect texture.id: that can itself cause lazy GL allocation.
    return f'{type(texture).__name__}:{id(texture)}:{tuple(texture.size)}'


class ProbeImage:
    def __init__(self, definition, theme, mode, loader=load_texture):
        self.guard = MeshGuard('probe_image')
        self.definition, self.texture, self.shape = definition, None, None
        self.widget = None
        self.theme, self.mode = theme, mode
        root = Path(__file__).resolve().parents[1]
        path = root/definition.image
        milestone('GRAPHICS_IMAGE_CREATE_BEGIN',theme=theme,mode=mode,asset=path.name,renderer='KivyImage')
        try:
            texture = loader(path)
            if texture is None: raise ValueError('Image missing or undecodable')
            description = check_texture(texture)
            if max(texture.size) > 4096 or texture.width*texture.height > 4*1024*1024:
                raise ValueError('Image exceeds existing arena atlas limits')
            radius = definition.source_radius_pixels or min(texture.size)*.5/definition.outer_scale
            center = definition.source_center_pixels or (texture.width/2,texture.height/2)
            if not isfinite(radius) or radius <= 0 or len(center) != 2 or not all(isfinite(v) for v in center):
                raise ValueError('Invalid image calibration')
            self.source_radius, self.source_center = radius,center
            self.texture = texture  # Strong reference for the complete view lifetime.
            # Construct outside the match Canvas context. Keep the widget and
            # its stock canvas alive; the view explicitly inserts that canvas
            # once, behind logos/posts. No custom instruction geometry here.
            self.widget = Image(texture=texture,fit_mode='contain',size_hint=(None,None),
                                size=(0,0),color=(1,1,1,definition.opacity))
            self.shape = self.widget
            with self.widget.canvas.before:
                Callback(first_gpu_marker('GRAPHICS_IMAGE_GPU_ENTER',theme=theme,mode=mode))
            with self.widget.canvas.after:
                Callback(first_gpu_marker('GRAPHICS_IMAGE_GPU_EXIT',theme=theme,mode=mode))
            milestone('GRAPHICS_IMAGE_READY',theme=theme,mode=mode,texture=description,
                      renderer='KivyImage',custom_shader=False,mask=False,rotation=False)
        except (ValueError,TypeError,OSError,OverflowError) as error:
            milestone('GRAPHICS_IMAGE_REJECTED',theme=theme,mode=mode,reason=str(error))

    def layout(self, goal, project):
        self.guard.check_thread()
        if self.shape is None: return
        cx,cy = project(0,0)
        edge,_ = project(goal.radius,0)
        unit = (edge-cx)/self.source_radius
        w,h = self.texture.size
        sx,sy = self.source_center
        values = (cx-sx*unit, cy-(h-sy)*unit, w*unit, h*unit)
        if not all(isfinite(v) for v in values) or min(values[2:]) <= 0:
            milestone('GRAPHICS_IMAGE_LAYOUT_REJECTED',theme=self.theme,mode=self.mode)
            return
        self.shape.pos, self.shape.size = values[:2],values[2:]


class QuietEffects:
    """No instructions or particle pools in reduced probe modes."""
    idle = True
    round_id = None
    last_event = 0

    def update(self,engine,dt):
        self.round_id, self.last_event = engine.round_id,engine.event_serial

    def draw(self,project,scale): pass


def audit_view(view):
    """Read-only CPU inspection. This does not prove driver/VBO correctness."""
    for name,texture in [('background',view.background_texture),
                         *[(f'team_{i}',t) for i,t in enumerate(view.logo_textures)]]:
        milestone('GRAPHICS_TEXTURE_CHECK',part=name,texture=check_texture(texture))
    for index,texture in enumerate(view.arena_layers.source_textures):
        milestone('GRAPHICS_TEXTURE_CHECK',part=f'raster_source_{index}',texture=check_texture(texture))
    if view.probe_image and view.probe_image.texture:
        milestone('GRAPHICS_TEXTURE_CHECK',part='image',texture=check_texture(view.probe_image.texture))
    meshes = [(f'arena_raster_{i}',mesh,4) for i,(_,mesh,_) in enumerate(view.arena_layers.loaded)]
    for name,effect in (('fire',view.fire_particles),('electric',view.electric_effects)):
        if effect:
            meshes.append((name,effect.mesh,6 if effect.custom_shader else 4))
            shader = getattr(effect.canvas,'shader',None)
            milestone('GRAPHICS_CONTEXT_CHECK',part=name,canvas=type(effect.canvas).__name__,
                      canvas_ref=id(effect.canvas),mesh_ref=id(effect.mesh),
                      shader_success=shader.success if shader is not None else 'stock',owner=effect.guard.owner)
    for name,mesh,stride in meshes:
        count = validate_mesh(mesh.vertices,mesh.indices,stride)
        milestone('GRAPHICS_MESH_CHECK',mesh=name,vertices=count,indices=len(mesh.indices),stride=stride,
                  max_index=max(mesh.indices,default=-1),texture=check_texture(mesh.texture))
