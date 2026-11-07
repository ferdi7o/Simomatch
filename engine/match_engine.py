"""Fixed-step lifecycle, scores and in-memory goal history."""
import random
from math import cos, sin, pi, hypot, isfinite, ceil, radians
from collections import deque
from config import (FIXED_DT, MATCH_SECONDS, COUNTDOWN_SECONDS, FINAL_SECONDS,
                    DISK_RADIUS, MIN_DISK_RADIUS, MAX_DISK_RADIUS, MAX_SPEED,
                    START_SPEED_MIN, START_SPEED_MAX, MIN_SPEED, GOAL_SPEED_DEGREES,
                    MIN_GOAL_SPEED_DEGREES, MAX_GOAL_SPEED_DEGREES)
from engine.physics import Disk, collide_disks
from engine.arena import Arena
from engine.goal import Goal
from engine.cards import create_card_schedule


class MatchEngine:
    def __init__(self, seed=None, duration=MATCH_SECONDS, teams=('FB', 'GS'),
                 radii=(DISK_RADIUS, DISK_RADIUS), goal_speed_degrees=GOAL_SPEED_DEGREES,
                 cards_enabled=True):
        if len(teams) != 2 or len(set(teams)) != 2 or not all(teams):
            raise ValueError('İki farklı takım seçilmelidir.')
        if not isfinite(duration) or duration <= 0:
            raise ValueError('Maç süresi pozitif olmalıdır.')
        if len(radii) != 2 or any(not isfinite(r) or not MIN_DISK_RADIUS <= r <= MAX_DISK_RADIUS for r in radii):
            raise ValueError(f'Disk yarıçapı {MIN_DISK_RADIUS:g}–{MAX_DISK_RADIUS:g} arasında olmalıdır.')
        if not isfinite(goal_speed_degrees) or not MIN_GOAL_SPEED_DEGREES <= goal_speed_degrees <= MAX_GOAL_SPEED_DEGREES:
            raise ValueError('Kale dönüş hızı 30–180 derece/saniye arasında olmalıdır.')
        self.random = random.Random(seed)
        self.card_random = random.Random(f'cards:{seed}' if seed is not None else None)
        self.cards_enabled = cards_enabled
        self.duration = duration
        self.goal_speed_degrees = goal_speed_degrees
        self.teams, self.radii = tuple(teams), tuple(radii)
        self.restart()

    def restart(self):
        self.round_id = getattr(self, 'round_id', 0) + 1
        self.events = deque(maxlen=128)
        self.event_serial = 0
        self._contacts = set()
        self.arena = Arena()
        self.goal = Goal(angular_speed=-radians(self.goal_speed_degrees))
        self.scores = dict.fromkeys(self.teams, 0)
        self.goals = []
        self.cards = []
        self.card_schedule = create_card_schedule(self.card_random, self.teams) if self.cards_enabled else []
        self._next_card = 0
        self.elapsed = self.accumulator = self.final_elapsed = self.flash = 0.0
        self.countdown = COUNTDOWN_SECONDS
        self.state = 'countdown'
        self.post_hits = 0
        self.reset_disks()

    def reset_disks(self):
        self.disks = []
        for team, radius, x in zip(self.teams, self.radii, (-135., 135.)):
            angle = self.random.uniform(0, 2 * pi)
            speed = self.random.uniform(START_SPEED_MIN, START_SPEED_MAX)
            self.disks.append(Disk(team, x, 0., speed * cos(angle), speed * sin(angle), radius))

    def respawn(self, disk):
        """Move only the scorer. Prefer the center; never displace the opponent."""
        other = next(d for d in self.disks if d is not disk)
        clearance = disk.radius + other.radius + 8
        distance = hypot(other.x, other.y)
        disk.x = disk.y = 0.
        if distance < clearance:
            # Closest safe point on the side opposite the opponent.
            nx, ny = (other.x / distance, other.y / distance) if distance > 1e-9 else (1., 0.)
            offset = clearance - distance
            disk.x, disk.y = -nx * offset, -ny * offset
        angle = self.random.uniform(0, 2*pi)
        speed = self.random.uniform(START_SPEED_MIN, START_SPEED_MAX)
        disk.vx, disk.vy = speed*cos(angle), speed*sin(angle)
        self.emit('respawn', disk.x, disk.y, disk.team)

    def emit(self, kind, x, y, team=None):
        """Bounded read-only notifications for render effects; no render RNG here."""
        self.event_serial += 1
        self.events.append((self.event_serial, kind, x, y, team))

    @property
    def minute(self):
        return min(90, 1 + int(89 * self.elapsed / self.duration))

    def advance(self, dt):
        """Keep all accumulated time: render frequency never changes simulation time."""
        if dt < 0:
            raise ValueError('dt must be non-negative')
        self.accumulator += dt
        while self.accumulator + 1e-12 >= FIXED_DT:
            self.accumulator -= FIXED_DT
            self.step(FIXED_DT)

    def step(self, dt):
        self.flash = max(0., self.flash - dt)
        if self.state == 'countdown':
            self.countdown = max(0., self.countdown - dt)
            if self.countdown < 1e-9:
                self.state = 'playing'
                self.emit('start', 0, 0)
            return
        if self.state == 'finished':
            self.final_elapsed += dt
            return
        self.elapsed = min(self.duration, self.elapsed + dt)
        # Limit relative travel to half a post radius, including moving posts.
        # Even at normal speed multiple microsteps run inside each fixed tick.
        for disk in self.disks:
            disk.limit_speed()
        travel = min(min(d.radius for d in self.disks)*.2, self.goal.post_radius*.5)
        relative_speed = 2*MAX_SPEED + abs(self.goal.angular_speed)*self.arena.radius
        substeps = max(2, ceil(relative_speed*dt/travel))
        self.last_substeps = substeps
        self._scored_this_tick = []
        for _ in range(substeps):
            self._integrate(dt/substeps)
        for disk in self._scored_this_tick:
            self.respawn(disk)
        while self._next_card < len(self.card_schedule) and self.card_schedule[self._next_card].minute <= self.minute:
            card = self.card_schedule[self._next_card]
            self.cards.append(card)
            self.emit(card.kind, 0, 0, card.team)
            self._next_card += 1
        if self.elapsed >= self.duration - 1e-9:
            self.elapsed = self.duration
            self.state = 'finished'
            self.emit('end', 0, 0)

    def _integrate(self, dt):
        self.goal.update(dt)
        for disk in self.disks:
            if disk in self._scored_this_tick:
                continue
            disk.x += disk.vx * dt
            disk.y += disk.vy * dt
        a, b = self.disks
        dx, dy = b.x-a.x, b.y-a.y
        distance = hypot(dx, dy)
        normal_speed = -((b.vx-a.vx)*dx + (b.vy-a.vy)*dy)/max(distance, 1e-9)
        contact = not self._scored_this_tick and collide_disks(a, b)
        if contact and normal_speed > 0 and 'disk' not in self._contacts:
            total = a.radius+b.radius
            kind = 'soft' if normal_speed < MIN_SPEED*.65 else 'disk'
            self.emit(kind, a.x+(b.x-a.x)*a.radius/total, a.y+(b.y-a.y)*a.radius/total)
        if contact:
            self._contacts.add('disk')
        else:
            self._contacts.discard('disk')
        for disk in self.disks:
            if disk in self._scored_this_tick:
                continue
            previous_velocity = disk.vx, disk.vy
            event = self.arena.resolve(disk, self.goal)
            self.post_hits += event == 'post'
            key = (event, disk.team)
            if event in ('wall', 'post') and previous_velocity != (disk.vx, disk.vy) and key not in self._contacts:
                distance = hypot(disk.x, disk.y)
                self.emit(event, disk.x*self.arena.radius/distance, disk.y*self.arena.radius/distance, disk.team)
            for kind in ('wall', 'post'):
                self._contacts.discard((kind, disk.team))
            if event in ('wall', 'post'):
                self._contacts.add(key)
            disk.limit_speed()
            if event != 'post' and self.goal.fully_crossed(disk):
                self.scores[disk.team] += 1
                self.goals.append((disk.team, self.minute))
                self.flash = 1.1
                self.emit('goal', disk.x, disk.y, disk.team)
                self._scored_this_tick.append(disk)

    @property
    def can_restart(self):
        return self.state == 'finished' and self.final_elapsed >= FINAL_SECONDS
