"""Optional visual smoke check: python tools/smoke_ui.py (Windows desktop).

Creates isolated sample teams and screenshots under .smoke_runtime, never edits
the user's data/teams.json. Exits automatically after exercising navigation.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.graphics.fbo import Fbo
from services.team_store import TeamStore


class SmokeApp(main.SimomatchApp):
    def build(self):
        root = super().build()
        self.output = ROOT / '.smoke_runtime'
        self.output.mkdir(exist_ok=True)
        root.store = TeamStore(self.output / 'data')
        if not root.store.teams:
            # A code-generated test texture, not a bundled team logo.
            fbo = Fbo(size=(64, 64))
            with fbo:
                Color(.7, .25, 1, 1)
                Rectangle(pos=(0, 0), size=(64, 64))
                Color(1, .85, .1, 1)
                Rectangle(pos=(18, 8), size=(28, 48))
            fbo.draw()
            logo = self.output / 'test_logo.png'
            fbo.texture.save(str(logo))
            root.store.save('Mor Yıldız', logo=logo)
            root.store.save('Neon Spor', logo=logo)
        return root

    def on_start(self):
        # Schedule relative to the first frame, after provider initialization.
        Clock.schedule_once(self.begin, 0)

    def begin(self, dt):
        Window.size = (450, 800)
        steps = [(0.5, lambda: self.shot('menu')),
                 (0.7, lambda: self.root.get_screen('menu').team_button.dispatch('on_release')),
                 (1.0, lambda: self.shot('teams')),
                 (1.2, self.setup_match), (1.6, lambda: self.shot('setup')),
                 (1.8, lambda: self.root.get_screen('setup').start_match()),
                 (5.0, lambda: self.shot('match')),
                 (5.05, self.contact_effect),
                 (5.15, lambda: self.shot('contact')),
                 (5.2, lambda: self.root.match_view.engine.advance(60)),
                 (5.5, lambda: self.shot('final')),
                 (5.7, lambda: setattr(Window, 'size', (320, 640))),
                 (6.0, lambda: self.shot('small')),
                 (6.2, lambda: setattr(Window, 'size', (720, 1280))),
                 (6.5, lambda: self.shot('large')),
                 (6.7, self.check_restart), (7.0, self.stop)]
        for delay, action in steps:
            Clock.schedule_once(lambda dt, fn=action: fn(), delay + 1)

    def setup_match(self):
        self.root.go('setup')
        setup = self.root.get_screen('setup')
        setup.spinners[0].text, setup.spinners[1].text = [t['name'] for t in self.root.store.teams[:2]]
        setup.sliders[0].value, setup.sliders[1].value = 60, 72

    def contact_effect(self):
        a, b = self.root.match_view.engine.disks
        a.x, b.x = -a.radius-1, b.radius+1
        a.y = b.y = 0
        a.vx, a.vy, b.vx, b.vy = 600, 0, -600, 0

    def shot(self, name):
        # RGBA FBO capture avoids RGB row-alignment issues at width 450.
        self.root.export_to_png(str(self.output / f'neon_{name}.png'))

    def check_restart(self):
        self.root.match_view.restart_button.dispatch('on_release')
        assert self.root.match_view.engine.state == 'countdown'
        self.root.back()
        assert self.root.current == 'setup'
        print('SMOKE OK: menu, teams, setup, match, final, restart, back')


if __name__ == '__main__':
    SmokeApp().run()
