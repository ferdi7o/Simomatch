"""Reusable Canvas drawings: no widgets or new instructions during rendering."""
from math import pi, sin, cos
from kivy.graphics import (Color, Ellipse, Rectangle, Line, StencilPush,
                           StencilUse, StencilUnUse, StencilPop)

NEON = [(0.12, 1, .55), (1, .86, .18), (1, .38, .10), (.12, .6, 1), (.9, .98, 1)]


def cover_coordinates(texture, size):
    """Centered UV crop fills a rectangle without stretching the source image."""
    width, height = size
    if width <= 0 or height <= 0:
        return texture.tex_coords
    source_ratio, target_ratio = texture.width/texture.height, width/height
    crop_x, crop_y = min(1., target_ratio/source_ratio), min(1., source_ratio/target_ratio)
    left, bottom = (1-crop_x)/2, (1-crop_y)/2
    corners = list(zip(texture.tex_coords[::2], texture.tex_coords[1::2]))
    def uv(u, v):
        # Respect flipped textures/regions rather than assuming a Y direction.
        return tuple((1-v)*((1-u)*corners[0][i]+u*corners[1][i]) +
                     v*((1-u)*corners[3][i]+u*corners[2][i]) for i in range(2))
    return [value for u, v in ((left, bottom), (left+crop_x, bottom),
                               (left+crop_x, bottom+crop_y), (left, bottom+crop_y))
            for value in uv(u, v)]


class LogoDrawing:
    """Aspect-fit texture clipped by a circle, retaining its original alpha.

    Textured logos have no solid backing or border. The circle is also the
    collision shape; transparent parts do not change the physics geometry.
    """
    def __init__(self, texture, fallback):
        self.texture = texture
        Color(*fallback, 0 if texture else 1)
        self.fallback = Ellipse()
        StencilPush()
        self.mask = Ellipse()
        StencilUse()
        Color(1, 1, 1, 1 if texture else 0)
        self.image = Rectangle(texture=texture)
        StencilUnUse()
        self.unmask = Ellipse()
        StencilPop()

    def layout(self, x, y, radius):
        for shape in (self.fallback, self.mask, self.unmask):
            shape.pos, shape.size = (x-radius, y-radius), (2*radius, 2*radius)
        if self.texture:
            factor = 2*radius/max(self.texture.size)
            width, height = self.texture.width*factor, self.texture.height*factor
            self.image.pos, self.image.size = (x-width/2, y-height/2), (width, height)


class NeonRing:
    """25 short colored arcs, three translucent strokes per arc for soft glow."""
    def __init__(self, palette=None, glow_strength=1.):
        self.palette = tuple(palette or NEON)
        self.glow_strength = glow_strength
        self.segments = []
        for index in range(25):
            rgb = self.palette[index % len(self.palette)]
            strokes = []
            for alpha, width in ((.055, 9), (.17, 4), (.95, 1.25)):
                Color(*rgb, min(1., alpha*(glow_strength if width > 2 else 1)))
                strokes.append(Line(width=width))
            self.segments.append(strokes)

    def layout(self, goal, project, scale):
        # Every arc shares exact post angles, so no glow crosses the mouth.
        start = goal.angle+goal.half_angle
        length = 2*pi-2*goal.half_angle
        for index, strokes in enumerate(self.segments):
            points = []
            for i in range(9):
                angle = start+length*(index+i/8)/len(self.segments)
                points.extend(project(goal.radius*cos(angle), goal.radius*sin(angle)))
            for stroke, width in zip(strokes, (9, 4, 1.25)):
                stroke.points = points
                stroke.width = max(.65, width*scale*2)
