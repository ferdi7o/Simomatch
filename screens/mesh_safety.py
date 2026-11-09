"""Validate complete CPU batches before touching a Kivy Mesh/VBO."""
from math import isfinite
from threading import get_ident
from services.graphics_diagnostics import milestone

FLOAT32_MAX = 3.4028234663852886e38


def validate_mesh(vertices, indices, stride):
    if stride <= 0 or len(vertices) % stride:
        raise ValueError('Vertex stride mismatch')
    count = len(vertices)//stride
    if bool(count) != bool(indices):
        raise ValueError('Vertices and indices must both be empty or nonempty')
    if count > 65535 or len(indices) > 65535 or len(indices) % 3:
        raise ValueError('Invalid GLES2 triangle batch size')
    if any(not isfinite(v) or abs(v) > FLOAT32_MAX for v in vertices):
        raise ValueError('Nonfinite or overflowing float32 vertex')
    if any(type(i) is not int or not 0 <= i < count for i in indices):
        raise ValueError('Index outside vertex buffer')
    return count


class MeshGuard:
    def __init__(self, name):
        self.name, self.owner = name, get_ident()
        self.uploads, self.last_error = 0, ''

    def check_thread(self):
        if get_ident() != self.owner:
            milestone('GRAPHICS_THREAD_REJECTED',part=self.name,owner=self.owner,caller=get_ident())
            raise RuntimeError(f'{self.name}: graphics access outside owner thread')

    def _reject(self, exc):
        if str(exc) != self.last_error:
            milestone('MESH_REJECTED', mesh=self.name, reason=str(exc))
            self.last_error = str(exc)
        return False

    def upload_colors(self, mesh, vertices, indices, custom_shader=True):
        if custom_shader:
            return self.upload(mesh, vertices, indices, 6)
        # Diagnostic only: same triangles, default Kivy shader/UV format, flat
        # Canvas tint. Never send a six-float layout to the four-float shader.
        self.check_thread()
        try:
            validate_mesh(vertices, indices, 6)
        except (ValueError, TypeError, OverflowError) as exc:
            return self._reject(exc)
        plain = [v for i in range(0, len(vertices), 6) for v in (vertices[i], vertices[i+1], .5, .5)]
        return self.upload(mesh, plain, indices, 4)

    def upload(self, mesh, vertices, indices, stride):
        self.check_thread()
        try:
            count = validate_mesh(vertices, indices, stride)
        except (ValueError, TypeError, OverflowError) as exc:
            return self._reject(exc)  # Retain the last valid batch.
        # Clear old topology first; no index may reference removed vertices even
        # transiently. All assignments occur on the same graphics thread.
        mesh.indices = []
        mesh.vertices = vertices
        mesh.indices = indices
        self.uploads += 1
        if self.uploads <= 4:
            milestone('MESH_VALIDATED', mesh=self.name, upload=self.uploads,
                      vertices=count, indices=len(indices), stride=stride,
                      max_index=max(indices, default=-1))
        self.last_error = ''
        return True
