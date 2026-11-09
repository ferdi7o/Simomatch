"""Colored triangles through Kivy's stock x/y/u/v shader, no RenderContext.

Each triangle samples a 2x2 RGBA tile. A fourth color C1+C2-C0 makes bilinear
texture filtering equal barycentric vertex-color interpolation. If that color
falls outside RGBA8, split into four exact subtriangles first. Only RGBA8
quantization is introduced; positions, blending, clipping and order survive.
"""
from kivy.graphics import Canvas, Color, Mesh, Callback
from kivy.graphics.texture import Texture
from screens.mesh_safety import MeshGuard, validate_mesh
from services.arena_gpu_probe import first_gpu_marker
from services.graphics_diagnostics import milestone


class ParticleTextureBatch:
    EDGE = 128  # 4096 reusable 2x2 tiles, 64 KiB uploaded per rendered frame.

    def __init__(self, name, guard=None, trace=False):
        self.guard = guard or MeshGuard(name)
        self.name = name
        self.buffers = [([], [], bytearray(self.EDGE*self.EDGE*4)) for _ in range(2)]
        self.active = 0
        self.tiles = {}
        self.texture = Texture.create(size=(self.EDGE,self.EDGE), colorfmt='rgba', bufferfmt='ubyte')
        self.texture.min_filter = self.texture.mag_filter = 'linear'
        self.texture.wrap = 'clamp_to_edge'
        self.texture.add_reload_observer(self._reload)
        self._reload(self.texture)
        self.canvas = Canvas()
        with self.canvas:
            Color(1,1,1,1)
            if trace:
                Callback(first_gpu_marker(name.upper()+'_TEXTURE_MESH_GPU_ENTER'))
            self.mesh = Mesh(vertices=[], indices=[], texture=self.texture, mode='triangles',
                             fmt=[(b'vPosition',2,'float'),(b'vTexCoords0',2,'float')])
            if trace:
                Callback(first_gpu_marker(name.upper()+'_TEXTURE_MESH_GPU_EXIT'))
        milestone('PARTICLE_RENDERER_READY', effect=name, renderer='texture',
                  custom_shader=False, stride_bytes=16, atlas_edge=self.EDGE)

    def _reload(self, texture):
        self.guard.check_thread()
        texture.blit_buffer(self.buffers[self.active][2], colorfmt='rgba', bufferfmt='ubyte')

    @staticmethod
    def _mid(a, b):
        return tuple((x+y)*.5 for x,y in zip(a,b))

    def _tile(self, colors, pixels):
        # Input and the computed fourth color were range checked. Integer
        # conversion is safe without 32 extra min/max calls for every triangle.
        key = bytes(int(v*255+.5) for color in colors for v in color)
        if key in self.tiles:
            return self.tiles[key]
        slot = len(self.tiles)
        if slot >= (self.EDGE//2)**2:
            raise ValueError('Particle color atlas capacity exceeded')
        x, y = slot % (self.EDGE//2)*2, slot//(self.EDGE//2)*2
        for offset, start in ((0,0),(4,4),(self.EDGE*4,8),(self.EDGE*4+4,12)):
            index = (y*self.EDGE+x)*4+offset
            pixels[index:index+4] = key[start:start+4]
        uv = (((x+.5)/self.EDGE,(y+.5)/self.EDGE),
              ((x+1.5)/self.EDGE,(y+.5)/self.EDGE),
              ((x+.5)/self.EDGE,(y+1.5)/self.EDGE))
        self.tiles[key] = uv
        return uv

    def _emit(self, triangle, out, indices, pixels, split=True):
        colors = [point[2:] for point in triangle]
        # Nearly all flame/glow/core triangles repeat one RGBA corner. Avoid
        # searching an affine patch for this common case.
        if colors[0] == colors[1]:
            candidate = ((0,1,2),colors[2])
        elif colors[0] == colors[2]:
            candidate = ((0,1,2),colors[1])
        elif colors[1] == colors[2]:
            candidate = ((1,2,0),colors[0])
        else:
            candidate = None
            for first in range(3):
                order = (first,(first+1)%3,(first+2)%3)
                c0,c1,c2 = (colors[i] for i in order)
                c3 = tuple(b+c-a for a,b,c in zip(c0,c1,c2))
                if all(-1e-7 <= value <= 1+1e-7 for value in c3):
                    candidate = order,c3
                    break
        if candidate:
            order,c3 = candidate
            c0,c1,c2 = (colors[i] for i in order)
            uv = self._tile((c0,c1,c2,c3),pixels)
            start = len(out)//4
            for i,coords in zip(order,uv):
                out.extend((*triangle[i][:2],*coords))
            indices.extend((start,start+1,start+2))
            return
        if not split:
            raise ValueError('Invalid particle color interpolation')
        a,b,c = triangle
        ab,bc,ca = self._mid(a,b),self._mid(b,c),self._mid(c,a)
        # Each corner's fourth color is the opposite-edge midpoint; the
        # center's fourth color is an original corner. All lie in RGBA range.
        for piece in ((a,ab,ca),(b,bc,ab),(c,ca,bc),(ab,bc,ca)):
            self._emit(piece,out,indices,pixels,split=False)

    def upload(self, vertices, indices):
        self.guard.check_thread()
        inactive = 1-self.active
        out, target_indices, pixels = self.buffers[inactive]
        try:
            validate_mesh(vertices,indices,6)
            if any(not -1e-7 <= vertices[i+j] <= 1+1e-7
                   for i in range(0,len(vertices),6) for j in (2,3,4,5)):
                raise ValueError('Particle RGBA outside normalized range')
            out.clear(); target_indices.clear(); self.tiles.clear()
            points = [tuple(vertices[i:i+6]) for i in range(0,len(vertices),6)]
            for i in range(0,len(indices),3):
                triangle = (points[indices[i]],points[indices[i+1]],points[indices[i+2]])
                self._emit(triangle,out,target_indices,pixels)
            validate_mesh(out,target_indices,4)
        except (ValueError,TypeError,OverflowError) as error:
            return self.guard._reject(error)
        # All CPU preparation succeeded. Previous Mesh lists and palette were
        # kept untouched in the other buffer if validation/capacity failed.
        self.texture.blit_buffer(pixels,colorfmt='rgba',bufferfmt='ubyte')
        self.guard.upload(self.mesh,out,target_indices,4)
        self.active = inactive
        return True

    def clear(self):
        self.guard.upload(self.mesh,[],[],4)
