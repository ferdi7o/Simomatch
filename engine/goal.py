"""Rotating goal: a chord between two posts is the scoring line."""
from dataclasses import dataclass
from math import cos, sin, tan
from config import ARENA_RADIUS, GOAL_HALF_ANGLE, GOAL_SPEED, POST_RADIUS


@dataclass
class Goal:
    angle: float = 1.5707963267948966
    angular_speed: float = GOAL_SPEED
    half_angle: float = GOAL_HALF_ANGLE
    radius: float = ARENA_RADIUS
    post_radius: float = POST_RADIUS

    def update(self, dt):
        self.angle = (self.angle + self.angular_speed * dt) % (2 * 3.141592653589793)

    @property
    def posts(self):
        return [(self.radius * cos(self.angle + offset),
                 self.radius * sin(self.angle + offset))
                for offset in (-self.half_angle, self.half_angle)]

    def local(self, disk):
        c, s = cos(self.angle), sin(self.angle)
        return disk.x * c + disk.y * s, -disk.x * s + disk.y * c

    @property
    def line_distance(self):
        return self.radius * cos(self.half_angle)

    def in_opening(self, disk):
        """Removed wall arc, using precisely the post angles drawn by Canvas.

        Do not subtract the disk radius from this sector. Clearance is the
        Euclidean disk/post distance handled by Arena, not a tangent-width
        test applied before/after the disk even reaches the goal line.
        """
        outward, tangent = self.local(disk)
        return outward > 0 and abs(tangent) <= outward*tan(self.half_angle)

    def fully_crossed(self, disk):
        outward, _ = self.local(disk)
        return self.in_opening(disk) and outward - disk.radius > self.line_distance
