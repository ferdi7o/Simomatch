"""Circular wall interrupted by the rotating goal opening."""
from math import hypot
from config import ARENA_RADIUS
from engine.physics import collide_post


class Arena:
    radius = ARENA_RADIUS

    def resolve(self, disk, goal):
        post_hit = False
        for x, y in goal.posts:
            velocity = (-goal.angular_speed * y, goal.angular_speed * x)
            post_hit |= collide_post(disk, (x, y), velocity, goal.post_radius)
        if post_hit:
            return 'post'
        distance = hypot(disk.x, disk.y)
        # Only the solid circular arc reflects. The missing arc has no wall;
        # its endpoints are already covered by the two physical post circles.
        if goal.in_opening(disk):
            return 'opening'
        if distance + disk.radius >= self.radius:
            nx, ny = disk.x / distance, disk.y / distance
            disk.x, disk.y = nx * (self.radius - disk.radius), ny * (self.radius - disk.radius)
            speed = disk.vx * nx + disk.vy * ny
            if speed > 0:
                disk.vx -= 2 * speed * nx
                disk.vy -= 2 * speed * ny
            return 'wall'
        return None
