"""Circle collisions with positional correction and elastic impulses."""
from dataclasses import dataclass
from math import hypot
from config import MIN_SPEED, MAX_SPEED, DISK_RADIUS


@dataclass
class Disk:
    team: str
    x: float
    y: float
    vx: float
    vy: float
    radius: float = DISK_RADIUS
    mass: float = 1.0

    @property
    def speed(self):
        return hypot(self.vx, self.vy)

    def limit_speed(self):
        speed = self.speed
        if speed < 1e-10:
            self.vx, self.vy = MIN_SPEED, 0.0
        else:
            factor = max(MIN_SPEED, min(MAX_SPEED, speed)) / speed
            self.vx *= factor
            self.vy *= factor


def collide_disks(a, b):
    """Resolve overlap, then exchange normal momentum only when approaching."""
    dx, dy = b.x - a.x, b.y - a.y
    distance = hypot(dx, dy)
    overlap = a.radius + b.radius - distance
    if overlap < 0:
        return False
    nx, ny = (dx / distance, dy / distance) if distance > 1e-10 else (1., 0.)
    inv_a, inv_b = 1 / a.mass, 1 / b.mass
    correction = (overlap + 1e-6) / (inv_a + inv_b)
    a.x -= nx * correction * inv_a
    a.y -= ny * correction * inv_a
    b.x += nx * correction * inv_b
    b.y += ny * correction * inv_b
    relative = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny
    if relative < 0:
        impulse = -2 * relative / (inv_a + inv_b)
        a.vx -= impulse * inv_a * nx
        a.vy -= impulse * inv_a * ny
        b.vx += impulse * inv_b * nx
        b.vy += impulse * inv_b * ny
    return True


def collide_post(disk, position, velocity, radius):
    dx, dy = disk.x - position[0], disk.y - position[1]
    distance = hypot(dx, dy)
    if distance > disk.radius + radius:
        return False
    nx, ny = (dx / distance, dy / distance) if distance > 1e-10 else (1., 0.)
    disk.x = position[0] + nx * (disk.radius + radius + 1e-6)
    disk.y = position[1] + ny * (disk.radius + radius + 1e-6)
    normal = (disk.vx - velocity[0]) * nx + (disk.vy - velocity[1]) * ny
    if normal < 0:
        disk.vx -= 2 * normal * nx
        disk.vy -= 2 * normal * ny
    return True
