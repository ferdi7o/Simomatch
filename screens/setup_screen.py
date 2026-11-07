from pathlib import Path
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from screens.common import Page, button, caption
from services.media import load_texture
from services.match_settings import MatchSettings, THEMES
from config import (DISK_RADIUS, MIN_DISK_RADIUS, MAX_DISK_RADIUS, GOAL_SPEED_DEGREES,
                    MIN_GOAL_SPEED_DEGREES, MAX_GOAL_SPEED_DEGREES,
                    GOAL_SIZE_PERCENT, MIN_GOAL_SIZE_PERCENT, MAX_GOAL_SIZE_PERCENT)


class SetupScreen(Page):
    def __init__(self, router, **kwargs):
        super().__init__(router, 'MAÇ OLUŞTUR', **kwargs)
        self.selected_ids = [None, None]
        self.background_path = ''
        self.spinners, self.previews, self.sliders, self.size_labels = [], [], [], []
        columns = BoxLayout(size_hint_y=None, height=dp(300), spacing=dp(12))
        for index, title in enumerate(('EV SAHİBİ', 'DEPLASMAN')):
            column = BoxLayout(orientation='vertical', spacing=dp(8))
            column.add_widget(caption(title, bold=True, color=(.75, .5, 1, 1)))
            spinner = Spinner(text='Takım seç', size_hint_y=None, height=dp(44), font_size=dp(13),
                              background_normal='', background_color=(.16, .12, .24, 1))
            spinner.bind(text=lambda widget, value, i=index: self.select(i, value))
            self.spinners.append(spinner)
            column.add_widget(spinner)
            preview = Image(fit_mode='contain', color=(1, 1, 1, 0))
            preview.bind(texture=lambda w, texture: setattr(w, 'color', (1, 1, 1, 1 if texture else 0)))
            self.previews.append(preview)
            column.add_widget(preview)
            size_label = caption(f'Logo / top: {DISK_RADIUS:g}', height=32)
            self.size_labels.append(size_label)
            column.add_widget(size_label)
            slider = Slider(min=MIN_DISK_RADIUS, max=MAX_DISK_RADIUS, value=DISK_RADIUS,
                            step=1, size_hint_y=None, height=dp(42))
            slider.bind(value=lambda widget, value, i=index: self.set_size(i, value))
            self.sliders.append(slider)
            column.add_widget(slider)
            columns.add_widget(column)
        self.columns = columns
        self.content.add_widget(columns)
        self.content.add_widget(caption('MAÇ SÜRESİ · SANİYE', bold=True))
        self.duration_input = TextInput(text='55', multiline=False, input_filter='int',
                                        size_hint_y=None, height=dp(44))
        self.content.add_widget(self.duration_input)
        self.goal_speed_label = caption(f'KALE DÖNÜŞ HIZI · {GOAL_SPEED_DEGREES:g}°/s', bold=True)
        self.content.add_widget(self.goal_speed_label)
        self.goal_speed_slider = Slider(min=MIN_GOAL_SPEED_DEGREES, max=MAX_GOAL_SPEED_DEGREES,
                                        value=GOAL_SPEED_DEGREES, step=1, size_hint_y=None, height=dp(42))
        self.goal_speed_slider.bind(value=lambda _, value: setattr(
            self.goal_speed_label, 'text', f'KALE DÖNÜŞ HIZI · {value:.0f}°/s'))
        self.content.add_widget(self.goal_speed_slider)
        self.goal_size_label = caption(f'KALE BOYUTU · %{GOAL_SIZE_PERCENT:g}', bold=True)
        self.content.add_widget(self.goal_size_label)
        self.goal_size_slider = Slider(min=MIN_GOAL_SIZE_PERCENT, max=MAX_GOAL_SIZE_PERCENT,
                                      value=GOAL_SIZE_PERCENT, step=1, size_hint_y=None, height=dp(42))
        self.goal_size_slider.bind(value=lambda _, value: setattr(
            self.goal_size_label, 'text', f'KALE BOYUTU · %{value:.0f}'))
        self.content.add_widget(self.goal_size_slider)
        self.content.add_widget(caption('ARENA TEMASI', bold=True))
        self.theme = Spinner(text='neon_purple', values=tuple(THEMES), size_hint_y=None, height=dp(42),
                             background_normal='', background_color=(.16, .12, .24, 1))
        self.content.add_widget(self.theme)
        self.content.add_widget(button('ÖZEL GÖRSEL SEÇ', self.pick_background, secondary=True))
        self.background_label = caption('Tema kullanılacak', height=42)
        self.content.add_widget(self.background_label)
        self.content.add_widget(button('Görseli kaldır / temaya dön', self.clear_background, secondary=True))
        self.start_button = button('MAÇI BAŞLAT', self.start_match)
        # Keep the main action visible while settings scroll on small phones.
        self.shell.add_widget(self.start_button, index=1)
        self.content.add_widget(button('TAKIM OLUŞTUR', lambda: router.go('teams'), secondary=True))

    def on_pre_enter(self, *_):
        teams = self.router.store.teams
        self.by_name = {t['name']: t for t in teams}
        for i, spinner in enumerate(self.spinners):
            spinner.values = tuple(self.by_name)
            saved = self.router.store.get(self.selected_ids[i])
            spinner.text = saved['name'] if saved else 'Takım seç'
            self.select(i, spinner.text)
        self.status.text = 'Maç için en az iki takım oluşturun.' if len(teams) < 2 else 'İki farklı takım seçin; boyutlarını bağımsız ayarlayın.'

    def select(self, index, name):
        team = getattr(self, 'by_name', {}).get(name)
        self.selected_ids[index] = team['id'] if team else None
        self.previews[index].texture = load_texture(self.router.store.asset_path(team['logo'])) if team else None
        if team and team.get('logo') and self.previews[index].texture is None:
            self.status.text = 'Takım logosu okunamadı; maçta renkli disk kullanılacak.'

    def set_size(self, index, value):
        self.size_labels[index].text = f'Logo / top: {value:.0f}'

    def pick_background(self):
        def selected(path, error):
            if error:
                self.status.text = error
            elif path:
                if load_texture(path) is None:
                    self.status.text = 'Arka plan okunamadı. PNG/JPG görsel seçin.'
                    return
                self.background_path = path
                self.background_label.text = Path(path).name
        self.router.picker.pick('image', selected)

    def clear_background(self):
        self.background_path = ''
        self.background_label.text = 'Tema kullanılacak'

    def start_match(self):
        try:
            if len(self.router.store.teams) < 2:
                raise ValueError('Maç için en az iki takım oluşturun.')
            teams = [self.router.store.get(key) for key in self.selected_ids]
            if not all(teams):
                raise ValueError('Ev sahibi ve deplasman takımlarını seçin.')
            if self.background_path and load_texture(self.background_path) is None:
                raise ValueError('Özel arka plan bulunamadı veya bozuk; yeniden seçin ya da kaldırın.')
            try:
                duration = float(self.duration_input.text)
            except ValueError:
                raise ValueError('Maç süresini saniye olarak girin (10–600).') from None
            settings = MatchSettings(*teams, radii=tuple(s.value for s in self.sliders),
                                     duration=duration, theme=self.theme.text,
                                     background=self.background_path,
                                     goal_speed_degrees=self.goal_speed_slider.value,
                                     goal_size_percent=self.goal_size_slider.value)
            self.router.start_match(settings)
        except (ValueError, OSError) as exc:
            self.status.text = str(exc) if str(exc) else 'Geçerli bir maç süresi girin.'
