"""Rotating goal: a chord between two posts is the scoring line."""
from dataclasses import dataclass
from math import cos, sin, tan, asin, sqrt, isfinite
from config import (ARENA_RADIUS, GOAL_HALF_ANGLE, GOAL_SPEED, POST_RADIUS,
                    GOAL_SIZE_PERCENT, MIN_GOAL_SIZE_PERCENT, MAX_GOAL_SIZE_PERCENT,
                    GOAL_INSET_RATIO)


@dataclass
class Goal:
    angle: float = 1.5707963267948966
    angular_speed: float = GOAL_SPEED
    half_angle: float = GOAL_HALF_ANGLE
    radius: float = ARENA_RADIUS
    post_radius: float = POST_RADIUS
    size_percent: float = GOAL_SIZE_PERCENT
    inset_ratio: float = 0.

    @classmethod
    def sized(cls, percent=GOAL_SIZE_PERCENT, **kwargs):
        """Scale chord width exactly; share inset post geometry with scoring.

        Keep radius as the arena radius for decorative layers. Only the goal
        posts/line move inward. Angular masks use the new post angles.
        """
        if not isfinite(percent) or not MIN_GOAL_SIZE_PERCENT <= percent <= MAX_GOAL_SIZE_PERCENT:
            raise ValueError('Kale boyutu %60–150 arasında olmalıdır.')
        scale = percent/100
        return cls(half_angle=asin(sin(GOAL_HALF_ANGLE)*scale/(1-GOAL_INSET_RATIO)),
                   post_radius=POST_RADIUS*sqrt(scale), size_percent=percent,
                   inset_ratio=GOAL_INSET_RATIO, **kwargs)

    @property
    def post_circle_radius(self):
        return self.radius*(1-self.inset_ratio)

    def update(self, dt):
        self.angle = (self.angle + self.angular_speed * dt) % (2 * 3.141592653589793)

    @property
    def posts(self):
        return [(self.post_circle_radius * cos(self.angle + offset),
                 self.post_circle_radius * sin(self.angle + offset))
                for offset in (-self.half_angle, self.half_angle)]

    def local(self, disk):
        c, s = cos(self.angle), sin(self.angle)
        return disk.x * c + disk.y * s, -disk.x * s + disk.y * c

    @property
    def line_distance(self):
        return self.post_circle_radius * cos(self.half_angle)

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
