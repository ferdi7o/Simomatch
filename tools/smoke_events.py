"""Isolated visual goal/card check, creates screenshots only in .smoke_runtime."""
import sys
import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
from kivy.clock import Clock
from kivy.core.window import Window
from engine.cards import CardEvent
from services.audio import AudioManager
from services.match_settings import MatchSettings
from screens.match_screen import MatchScreen


class EventSmoke(main.SimomatchApp):
    def build(self):
        self.output = ROOT / '.smoke_runtime'
        self.output.mkdir(exist_ok=True)
        logo = str(self.output/'test_logo.png')
        a = {'id': 'h', 'name': 'Ev Sahibi Uzun Takım Adı', 'logo': logo}
        b = {'id': 'a', 'name': 'Deplasman Spor', 'logo': logo}
        self.audio = AudioManager()
        self.theme = os.environ.get('SIMOMATCH_SMOKE_THEME', 'neon_purple')
        self.view = MatchScreen(settings=MatchSettings(a, b, theme=self.theme), audio=self.audio,
                                store=SimpleNamespace(asset_path=lambda path: Path(path) if path else None))
        e = self.view.engine
        e.state = 'playing'
        e.advance = lambda dt: None  # Visual fixture only; no user match/data.
        return self.view

    def on_start(self):
        Clock.schedule_once(self.begin, 0)

    def begin(self, dt):
        Window.size = (450, 800)
        actions = [(1., self.goal), (1.2, self.cards), (1.4, lambda: self.shot('goal450')),
                   (3.2, lambda: self.shot('card450')), (6.4, self.finish),
                   (6.6, lambda: self.shot('final450')),
                   (6.8, lambda: setattr(Window, 'size', (320, 640))),
                   (7.1, lambda: self.shot('final320')),
                   (7.3, lambda: setattr(Window, 'size', (720, 1280))),
                   (7.6, lambda: self.shot('final720')), (7.9, self.stop)]
        for delay, callback in actions:
            Clock.schedule_once(lambda dt, fn=callback: fn(), delay)

    def goal(self):
        e = self.view.engine
        e.goals = [(e.teams[0], 12)]
        e.scores[e.teams[0]] = 1
        e.emit('goal', 0, 0, e.teams[0])

    def cards(self):
        e = self.view.engine
        e.cards = [CardEvent('yellow_card', e.teams[0], 24), CardEvent('red_card', e.teams[1], 62)]
        for card in e.cards:
            e.emit(card.kind, 0, 0, card.team)

    def finish(self):
        self.view.engine.state = 'finished'
        self.view.engine.final_elapsed = 4

    def shot(self, name):
        self.view.export_to_png(str(self.output/f'events_{self.theme}_{name}.png'))

    def on_stop(self):
        self.view.dispose()
        self.audio.close()
        print('EVENT SMOKE OK')


if __name__ == '__main__':
    EventSmoke().run()
