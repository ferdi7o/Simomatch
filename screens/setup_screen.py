from pathlib import Path
from math import floor, ceil
from kivy.clock import Clock
from kivy.graphics import Color
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from screens.common import Page
from screens.setup_controls import (BG, ACCENT, MUTED, Surface, Action, label,
                                    ChoiceValue, NeonSlider, DurationInput, ThemeTile, TeamRow, SettingHeading,
                                    BackgroundTile)
from services.media import load_texture
from services.match_settings import MatchSettings, THEMES
from services.backgrounds import BACKGROUNDS, DEFAULT_BACKGROUND, BackgroundPreferences, TEXTURES
from services.custom_backgrounds import CustomBackgroundStore
from config import (DISK_RADIUS, MIN_DISK_RADIUS, MAX_DISK_RADIUS, GOAL_SPEED_DEGREES,
                    MIN_GOAL_SPEED_DEGREES, MAX_GOAL_SPEED_DEGREES,
                    GOAL_SIZE_PERCENT, MIN_GOAL_SIZE_PERCENT, MAX_GOAL_SIZE_PERCENT)


class SetupScreen(Page):
    def __init__(self, router, **kwargs):
        super().__init__(router, 'MAÇ OLUŞTUR', **kwargs)
        self.selected_ids = [None, None]
        data_dir = getattr(router, 'background_data_dir', getattr(router.store, 'root', None))
        self.preferences = BackgroundPreferences(data_dir)
        legacy = BackgroundPreferences(getattr(router.store, 'root', None))
        if self.preferences.path and not self.preferences.path.exists():
            self.preferences.data.update(legacy.data)
        self.custom_store = CustomBackgroundStore(data_dir)
        migrated = {}
        for base in dict.fromkeys(path for path in (self.preferences.root, legacy.root) if path):
            migrated.update(self.custom_store.migrate(base/'backgrounds'))
        old_path = self.preferences.custom_path() or legacy.custom_path()
        selected = self.custom_store.get(self.preferences.data.get('custom_background_id', ''))
        if not selected:
            selected = migrated.get(old_path)
        self.selected_custom_id = selected['id'] if selected else ''
        self._loading_preferences = True
        self.background_path = ''
        self.custom_background_path = str(self.custom_store.owned_path(selected)) if selected else self.preferences.custom_path()
        if self.preferences.data.get('use_custom'):
            self.background_path = self.custom_background_path
        self.team_dialog = None
        self.delete_dialog = None
        self.spinners, self.previews, self.sliders, self.size_labels = [], [], [], []
        self.team_names, self.team_cards = [], []
        self.logo_placeholders = []
        # Restyle only this Page instance. Other menus keep their existing UI.
        next(instruction for instruction in self.canvas.before.children if isinstance(instruction, Color)).rgba = BG
        self.shell.spacing = dp(9)
        self.content.spacing = dp(9)
        self.status.height = dp(36)
        self.status.font_size = dp(11)
        self.status.color = MUTED
        header = self.shell.children[-1]
        header.clear_widgets()
        self.back_button = Action('Geri', lambda: router.go('menu', remember=False),
                                  size_hint_x=None, width=dp(54), height=dp(36))
        header.add_widget(self.back_button)
        header.add_widget(label('MAÇ OLUŞTUR', height=36, bold=True, halign='center', font_size=dp(18)))
        header.add_widget(Widget(size_hint_x=None, width=dp(54)))
        header.height = dp(36)
        columns = BoxLayout(size_hint_y=None, height=dp(274), spacing=dp(10))
        for index, title in enumerate(('EV SAHİBİ', 'DEPLASMAN')):
            column = Surface(orientation='vertical', padding=dp(10), spacing=dp(4))
            column.add_widget(label(title, height=22, bold=True, color=ACCENT, halign='center', font_size=dp(11)))
            preview = Image(fit_mode='contain', color=(1, 1, 1, 0), pos_hint={'x': 0, 'y': 0})
            preview.bind(texture=lambda w, texture: setattr(w, 'color', (1, 1, 1, 1 if texture else 0)))
            self.previews.append(preview)
            logo_area = FloatLayout()
            logo_area.add_widget(preview)
            placeholder = label('TAKIM', size_hint=(1, 1), halign='center',
                                bold=True, color=MUTED, font_size=dp(20), pos_hint={'x': 0, 'y': 0})
            self.logo_placeholders.append(placeholder)
            logo_area.add_widget(placeholder)
            column.add_widget(logo_area)
            name_label = label('Takım seçin', height=32, halign='center', bold=True)
            self.team_names.append(name_label)
            column.add_widget(name_label)
            choice = ChoiceValue(text='Takım seç')
            choice.bind(text=lambda widget, value, i=index: self.select(i, value))
            self.spinners.append(choice)
            column.add_widget(Action('TAKIM DEĞİŞTİR', lambda i=index: self.open_team_picker(i),
                                     height=dp(34), font_size=dp(10)))
            size_label = label(f'LOGO BOYUTU · {DISK_RADIUS:g}', height=24, font_size=dp(10), color=MUTED)
            self.size_labels.append(size_label)
            column.add_widget(size_label)
            slider = NeonSlider(min=MIN_DISK_RADIUS, max=MAX_DISK_RADIUS, value=DISK_RADIUS,
                                step=1, size_hint_y=None, height=dp(36))
            slider.bind(value=lambda widget, value, i=index: self.set_size(i, value))
            self.sliders.append(slider)
            column.add_widget(slider)
            columns.add_widget(column)
            self.team_cards.append(column)
        self.columns = columns
        self.content.add_widget(columns)

        duration_card = Surface(orientation='vertical', size_hint_y=None, height=dp(100),
                                padding=dp(12), spacing=dp(4))
        duration_card.add_widget(label('MAÇ SÜRESİ · SANİYE', height=20, bold=True, font_size=dp(11), color=MUTED))
        row = BoxLayout(spacing=dp(12))
        self.minus_button = Action('-', lambda: self.adjust_duration(-5), size_hint=(None, 1), width=dp(44))
        self.plus_button = Action('+', lambda: self.adjust_duration(5), size_hint=(None, 1), width=dp(44))
        self.duration_input = DurationInput()
        row.add_widget(self.minus_button)
        row.add_widget(self.duration_input)
        row.add_widget(self.plus_button)
        duration_card.add_widget(row)
        self.content.add_widget(duration_card)

        # These remain adjacent children, preserving order and value contracts.
        self.goal_speed_label = SettingHeading(f'KALE DÖNÜŞ HIZI · {GOAL_SPEED_DEGREES:g}°/s')
        self.content.add_widget(self.goal_speed_label)
        self.goal_speed_slider = NeonSlider(min=MIN_GOAL_SPEED_DEGREES, max=MAX_GOAL_SPEED_DEGREES,
                                           value=GOAL_SPEED_DEGREES, step=1, size_hint_y=None, height=dp(34))
        self.goal_speed_slider.bind(value=lambda _, value: setattr(
            self.goal_speed_label, 'text', f'KALE DÖNÜŞ HIZI · {value:.0f}°/s'))
        self.content.add_widget(self.goal_speed_slider)
        self.goal_size_label = SettingHeading(f'KALE BOYUTU · %{GOAL_SIZE_PERCENT:g}')
        self.content.add_widget(self.goal_size_label)
        self.goal_size_slider = NeonSlider(min=MIN_GOAL_SIZE_PERCENT, max=MAX_GOAL_SIZE_PERCENT,
                                          value=GOAL_SIZE_PERCENT, step=1, size_hint_y=None, height=dp(34))
        self.goal_size_slider.bind(value=lambda _, value: setattr(
            self.goal_size_label, 'text', f'KALE BOYUTU · %{value:.0f}'))
        self.content.add_widget(self.goal_size_slider)
        self.content.add_widget(label('ARENA TEMASI', height=24, bold=True))
        saved_theme = self.preferences.data.get('arena_theme', 'neon_purple')
        self.theme = ChoiceValue(text=saved_theme if saved_theme in THEMES else 'neon_purple', values=list(THEMES))
        self.theme.bind(text=self.update_theme)
        self.theme_tiles = {}
        self.theme_scroll = ScrollView(size_hint_y=None, height=dp(116), do_scroll_y=False,
                                       bar_width=dp(2), scroll_type=['bars', 'content'])
        gallery = BoxLayout(size_hint=(None, None), height=dp(112), spacing=dp(9), padding=(1, 0))
        gallery.bind(minimum_width=gallery.setter('width'))
        titles = ('Neon Purple', 'Fire Arena', 'Electric Blue', 'Rainbow Neon', 'Emerald Arena')
        asset_root = Path(__file__).resolve().parents[1]
        for (key, theme), title in zip(THEMES.items(), titles):
            candidates = [asset_root/layer.image for layer in theme.layers]+list(theme.image_paths)
            texture = next((tex for path in candidates if (tex := TEXTURES.thumbnail(path)) is not None), None)
            tile = ThemeTile(key, title, texture, theme.palette,
                             lambda key: setattr(self.theme, 'text', key))
            self.theme_tiles[key] = tile
            gallery.add_widget(tile)
        self.theme_scroll.add_widget(gallery)
        self.content.add_widget(self.theme_scroll)
        self.update_theme()

        self.content.add_widget(label('ARKA PLAN', height=24, bold=True))
        self.content.add_widget(label('HAZIR ARKA PLANLAR', height=20, color=MUTED, font_size=dp(10)))
        selected_background = self.preferences.data.get('background_id', DEFAULT_BACKGROUND)
        self.background_choice = ChoiceValue(text=selected_background if selected_background in BACKGROUNDS else DEFAULT_BACKGROUND)
        self.background_tiles = {}
        self.background_scroll = ScrollView(size_hint_y=None, height=dp(132), do_scroll_y=False, bar_width=dp(2))
        backgrounds = BoxLayout(size_hint=(None, None), height=dp(128), spacing=dp(9), padding=(1, 0))
        backgrounds.bind(minimum_width=backgrounds.setter('width'))
        for key, item in BACKGROUNDS.items():
            preview = TEXTURES.preview(key)
            tile = BackgroundTile(key, item.title, preview, self.select_background,
                                  fallback=TEXTURES.preview_fallbacks.get(key, False))
            self.background_tiles[key] = tile
            backgrounds.add_widget(tile)
        self.background_scroll.add_widget(backgrounds)
        self.content.add_widget(self.background_scroll)

        self.content.add_widget(label('BENİM ARKA PLANLARIM', height=24, bold=True))
        self.custom_scroll = ScrollView(size_hint_y=None, height=dp(164), do_scroll_y=False, bar_width=dp(2))
        self.custom_gallery = BoxLayout(size_hint=(None, None), height=dp(158), spacing=dp(9), padding=(1, 0))
        self.custom_gallery.bind(minimum_width=self.custom_gallery.setter('width'))
        self.custom_scroll.add_widget(self.custom_gallery)
        self.content.add_widget(self.custom_scroll)
        self.preview_trigger = Clock.create_trigger(self.update_custom_previews, 0)
        self.custom_scroll.bind(scroll_x=lambda *_: self.preview_trigger(), width=lambda *_: self.preview_trigger())
        self.refresh_custom_gallery()

        background_card = Surface(orientation='vertical', padding=dp(10), spacing=dp(6),
                                  size_hint_y=None, height=dp(104))
        self.custom_background_card = background_card
        controls = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(34))
        self.add_background_button = Action('+ ARKA PLAN EKLE', self.pick_background, height=dp(34), font_size=dp(9))
        controls.add_widget(self.add_background_button)
        self.remove_background = Action('HAZIRA DÖN', self.clear_background, height=dp(34), font_size=dp(9))
        controls.add_widget(self.remove_background)
        background_card.add_widget(controls)
        info = BoxLayout(spacing=dp(10))
        self.background_preview = Image(fit_mode='contain', size_hint_x=None, width=dp(56), opacity=0)
        info.add_widget(self.background_preview)
        self.background_label = label('Tema kullanılacak', size_hint_y=1, color=MUTED, font_size=dp(11))
        info.add_widget(self.background_label)
        background_card.add_widget(info)
        self.content.add_widget(background_card)
        self.refresh_background()
        self._loading_preferences = False
        if migrated and self.selected_custom_id:
            self.save_preferences()
        self.start_button = Action('MAÇI BAŞLAT', self.start_match, primary=True, height=dp(48), font_size=dp(14))
        self.shell.add_widget(self.start_button, index=1)
        self.content.add_widget(Action('TAKIM OLUŞTUR', lambda: router.go('teams'), height=dp(34)))
        self.bind(size=self.responsive)
        self.responsive()

    def responsive(self, *_):
        # Density-aware padding, with a bottom inset for navigation/gesture area.
        inset = min(dp(18), max(dp(10), self.width*.035))
        self.shell.padding = (inset, dp(10), inset, dp(20))
        self.columns.height = min(dp(360), max(dp(274), self.width*.62))

    def adjust_duration(self, delta):
        self.duration_input.commit(self.duration_input, False)
        self.duration_input.text = str(max(10, min(600, int(self.duration_input.text)+delta)))
        self.duration_input.last_valid = int(self.duration_input.text)

    def update_theme(self, *_):
        for key, tile in self.theme_tiles.items():
            tile.selected = key == self.theme.text
        if not self._loading_preferences:
            self.save_preferences()

    def save_preferences(self):
        self.preferences.save(self.theme.text, self.background_choice.text,
                              self.custom_background_path, bool(self.background_path), self.selected_custom_id)
        if self.preferences.warning:
            self.status.text = self.preferences.warning

    def select_background(self, key):
        if key not in BACKGROUNDS:
            return
        self.background_choice.text = key
        self.background_path = ''  # Keep the custom file/reference for later use.
        self.refresh_background()
        self.save_preferences()

    def refresh_background(self):
        for key, tile in self.background_tiles.items():
            tile.selected = key == self.background_choice.text and not self.background_path
        self.custom_background_card.selected = bool(self.background_path)
        selected = self.custom_store.get(self.selected_custom_id)
        self.background_preview.texture = (self.custom_store.thumbnail(selected, TEXTURES) if selected else
                                           TEXTURES.thumbnail(self.custom_background_path))
        self.background_preview.opacity = 1 if self.background_preview.texture else 0
        self.background_label.text = ((selected['name'] if selected else Path(self.custom_background_path).name) if self.background_path else
                                      BACKGROUNDS[self.background_choice.text].title)
        for key, tile in self.custom_tiles.items():
            tile.selected = bool(self.background_path) and key == self.selected_custom_id
        self.preview_trigger()

    def refresh_custom_gallery(self):
        self.custom_gallery.clear_widgets()
        self.custom_tiles, self.custom_rows = {}, []
        for row in self.custom_store.rows:
            column = BoxLayout(orientation='vertical', size_hint=(None, None), size=(dp(116), dp(158)), spacing=dp(4))
            tile = BackgroundTile(row['id'], row['name'], None, self.select_custom_background)
            self.custom_tiles[row['id']] = tile
            self.custom_rows.append((row, tile))
            column.add_widget(tile)
            column.add_widget(Action('SİL', lambda key=row['id']: self.request_delete_background(key), height=dp(26), font_size=dp(10)))
            self.custom_gallery.add_widget(column)
        if not self.custom_rows:
            self.custom_gallery.add_widget(label('Henüz arka plan eklemediniz.', size_hint=(None, 1), width=dp(270), color=MUTED))
        self.preview_trigger()

    def update_custom_previews(self, *_):
        stride = dp(125)
        offset = max(0, self.custom_gallery.width-self.custom_scroll.width)*self.custom_scroll.scroll_x
        start, end = max(0, floor(offset/stride)-1), ceil((offset+self.custom_scroll.width)/stride)+1
        for i, (row, tile) in enumerate(self.custom_rows):
            tile.preview.texture = self.custom_store.thumbnail(row, TEXTURES) if start <= i <= end else None
            tile.selected = bool(self.background_path) and row['id'] == self.selected_custom_id

    def select_custom_background(self, key):
        row = self.custom_store.get(key)
        path = self.custom_store.owned_path(row)
        if not path or TEXTURES.texture(path) is None:
            self.status.text = 'Arka plan bulunamadı veya bozuk; başka bir görsel seçin.'
            return
        self.selected_custom_id = key
        self.background_path = self.custom_background_path = str(path)
        self.refresh_background()
        self.save_preferences()

    def request_delete_background(self, key):
        row = self.custom_store.get(key)
        if not row or self.delete_dialog:
            return
        modal = ModalView(size_hint=(.9, None), height=dp(200), background='', background_color=(0, 0, 0, 0))
        panel = Surface(orientation='vertical', padding=dp(14), spacing=dp(10))
        panel.add_widget(label('Arka planı sil', height=30, bold=True, halign='center'))
        panel.add_widget(label(row['name']+' silinsin mi?', size_hint_y=1, halign='center'))
        buttons = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(10))
        self.delete_cancel_button = Action('İPTAL', modal.dismiss)
        self.delete_confirm_button = Action('SİL', lambda: self.delete_custom_background(key))
        buttons.add_widget(self.delete_cancel_button)
        buttons.add_widget(self.delete_confirm_button)
        panel.add_widget(buttons)
        modal.add_widget(panel)
        modal.bind(on_dismiss=lambda *_: setattr(self, 'delete_dialog', None))
        self.delete_dialog = modal
        modal.open()

    def delete_custom_background(self, key):
        row = self.custom_store.get(key)
        if not row:
            return
        path, thumb = self.custom_store.owned_path(row), self.custom_store.thumbnail_path(row)
        try:
            self.custom_store.delete(key)
        except (ValueError, OSError) as exc:
            self.status.text = f'Arka plan silinemedi: {exc}'
            return
        if self.delete_dialog:
            self.delete_dialog.dismiss()
        TEXTURES.forget(path)
        TEXTURES.forget(thumb)
        if self.selected_custom_id == key:
            active = bool(self.background_path)
            self.selected_custom_id = self.custom_background_path = self.background_path = ''
            if active:
                self.background_choice.text = DEFAULT_BACKGROUND
        self.refresh_custom_gallery()
        self.refresh_background()
        self.save_preferences()
        self.status.text = 'Arka plan silindi.'

    def open_team_picker(self, index):
        if self.team_dialog:
            self.team_dialog.dismiss()
        modal = ModalView(size_hint=(.94, .78), background='', background_color=(0, 0, 0, 0),
                          overlay_color=(.02, .01, .04, .8))
        panel = Surface(orientation='vertical', padding=dp(14), spacing=dp(10))
        panel.add_widget(label('TAKIM SEÇ', height=30, bold=True, font_size=dp(16)))
        scroll = ScrollView(do_scroll_x=False)
        rows = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8))
        rows.bind(minimum_height=rows.setter('height'))
        self.picker_rows = []
        for team in self.router.store.teams:
            texture = load_texture(self.router.store.asset_path(team.get('logo', '')))
            row = TeamRow(team, texture, lambda name, i=index: self.choose_team(i, name))
            row.disabled = team['id'] == self.selected_ids[1-index]
            rows.add_widget(row)
            self.picker_rows.append(row)
        if not self.picker_rows:
            rows.add_widget(label('Henüz takım yok. Önce bir takım oluşturun.', height=60))
        scroll.add_widget(rows)
        panel.add_widget(scroll)
        panel.add_widget(Action('KAPAT', modal.dismiss))
        modal.add_widget(panel)
        self.team_dialog = modal
        modal.open()

    def choose_team(self, index, name):
        self.spinners[index].text = name
        if self.team_dialog:
            self.team_dialog.dismiss()
            self.team_dialog = None

    def on_pre_leave(self, *_):
        self.preview_trigger.cancel()
        if self.delete_dialog:
            self.delete_dialog.dismiss()
        if self.team_dialog:
            self.team_dialog.dismiss()
            self.team_dialog = None

    def on_pre_enter(self, *_):
        self.preview_trigger()
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
        if team and team['id'] == self.selected_ids[1-index]:
            saved = self.router.store.get(self.selected_ids[index])
            self.spinners[index].text = saved['name'] if saved else 'Takım seç'
            self.status.text = 'İki farklı takım seçin.'
            return
        self.selected_ids[index] = team['id'] if team else None
        self.previews[index].texture = load_texture(self.router.store.asset_path(team['logo'])) if team else None
        self.team_names[index].text = team['name'] if team else 'Takım seçin'
        self.logo_placeholders[index].text = team['name'][:2].upper() if team else 'TAKIM'
        self.logo_placeholders[index].opacity = 0 if self.previews[index].texture else 1
        if team and team.get('logo') and self.previews[index].texture is None:
            self.status.text = 'Takım logosu okunamadı; maçta renkli disk kullanılacak.'

    def set_size(self, index, value):
        self.size_labels[index].text = f'LOGO BOYUTU · {value:.0f}'

    def pick_background(self):
        def selected(path, error):
            if error:
                self.status.text = error
            elif path:
                try:
                    row = self.custom_store.add(path)
                except (OSError, ValueError) as exc:
                    self.status.text = str(exc) or 'Arka plan okunamadı.'
                    return
                self.refresh_custom_gallery()
                self.select_custom_background(row['id'])
                self.custom_scroll.scroll_x = 1
                self.status.text = 'Arka plan kaydedildi.'
        self.router.picker.pick('image', selected)

    def clear_background(self):
        self.background_path = ''
        self.custom_background_path = ''
        self.selected_custom_id = ''
        self.refresh_background()
        self.save_preferences()

    def start_match(self):
        try:
            if len(self.router.store.teams) < 2:
                raise ValueError('Maç için en az iki takım oluşturun.')
            teams = [self.router.store.get(key) for key in self.selected_ids]
            if not all(teams):
                raise ValueError('Ev sahibi ve deplasman için iki farklı takım seçin.')
            if self.background_path and TEXTURES.texture(self.background_path) is None:
                self.background_path = ''
                self.refresh_background()
                self.save_preferences()
            try:
                duration = float(self.duration_input.text)
            except ValueError:
                raise ValueError('Maç süresini saniye olarak girin (10–600).') from None
            settings = MatchSettings(*teams, radii=tuple(s.value for s in self.sliders),
                                     duration=duration, theme=self.theme.text,
                                     background=self.background_path,
                                     goal_speed_degrees=self.goal_speed_slider.value,
                                     goal_size_percent=self.goal_size_slider.value,
                                     background_id=self.background_choice.text)
            self.router.start_match(settings)
        except (ValueError, OSError) as exc:
            self.status.text = str(exc) if str(exc) else 'Geçerli bir maç süresi girin.'
