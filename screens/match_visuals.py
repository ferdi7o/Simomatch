"""Reusable Canvas drawings: no widgets or new instructions during rendering."""
from math import pi, sin, cos, radians
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
    def __init__(self, palette=None, glow_strength=1., decorative_speed_degrees=22., pulse_hz=.8):
        self.palette = tuple(palette or NEON)
        self.glow_strength = glow_strength
        self.decorative_speed = radians(decorative_speed_degrees)
        self.pulse_hz, self.time, self.phase = pulse_hz, 0., 0.
        self.segments = []
        self.colors = []
        for index in range(25):
            rgb = self.palette[index % len(self.palette)]
            strokes = []
            colors = []
            for alpha, width in ((.055, 9), (.17, 4), (.95, 1.25)):
                colors.append(Color(*rgb, min(1., alpha*(glow_strength if width > 2 else 1))))
                strokes.append(Line(width=width))
            self.segments.append(strokes)
            self.colors.append(colors)

    def advance(self, dt):
        """Render time only. Never use the goal angle to advance decoration."""
        self.time += max(0., dt)
        self.phase = (self.phase+self.decorative_speed*max(0., dt)) % (2*pi)

    def color_at(self, angle):
        value = ((angle-self.phase)/(2*pi)*len(self.palette)) % len(self.palette)
        index, fraction = int(value), value % 1
        a, b = self.palette[index], self.palette[(index+1) % len(self.palette)]
        return tuple(x+(y-x)*fraction for x, y in zip(a, b))

    def layout(self, goal, project, scale):
        # Every arc shares exact post angles, so no glow crosses the mouth.
        start = goal.angle+goal.half_angle
        length = 2*pi-2*goal.half_angle
        for index, strokes in enumerate(self.segments):
            angle = start+length*(index+.5)/len(self.segments)
            rgb = self.color_at(angle)
            pulse = .85+.15*sin(self.time*2*pi*self.pulse_hz+angle*3)
            for color, alpha in zip(self.colors[index], (.055, .17, .95)):
                color.rgba = (*rgb, min(1., alpha*pulse*(self.glow_strength if alpha < .9 else 1)))
            points = []
            for i in range(9):
                angle = start+length*(index+i/8)/len(self.segments)
                points.extend(project(goal.radius*cos(angle), goal.radius*sin(angle)))
            for stroke, width in zip(strokes, (9, 4, 1.25)):
                stroke.points = points
                stroke.width = max(.65, width*scale*2)
