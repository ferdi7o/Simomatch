from pathlib import Path
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from screens.common import Page, button, caption
from services.media import load_texture
from screens.setup_controls import NeonSlider
from services.music_backend import max_music_start


class TeamScreen(Page):
    def __init__(self, router, **kwargs):
        super().__init__(router, 'TAKIM OLUŞTUR', **kwargs)
        self.edit_id = None
        self.pending_logo = self.pending_music = None
        self.music_length = 0.
        self.music_duration = 5.
        self.test_status_event = None
        self.name_input = TextInput(hint_text='Takım adı', multiline=False, size_hint_y=None,
                                    height=dp(44), background_color=(.13, .11, .2, 1), foreground_color=(1, 1, 1, 1))
        self.content.add_widget(self.name_input)
        self.preview = Image(size_hint_y=None, height=dp(90), fit_mode='contain', color=(1, 1, 1, 0))
        self.preview.bind(texture=lambda w, texture: setattr(w, 'color', (1, 1, 1, 1 if texture else 0)))
        self.content.add_widget(self.preview)
        self.logo_label = caption('Logo seçilmedi · isteğe bağlı', height=42)
        self.content.add_widget(self.logo_label)
        self.content.add_widget(button('PNG / JPG LOGO SEÇ', lambda: self.pick('image'), secondary=True))
        self.music_label = caption('Gol müziği seçilmedi · isteğe bağlı', height=42)
        self.content.add_widget(self.music_label)
        self.content.add_widget(button('MP3 GOL MÜZİĞİ SEÇ', lambda: self.pick('music'), secondary=True))
        self.music_start_label = caption('MÜZİK BAŞLANGICI · 0.0 sn', height=32)
        self.content.add_widget(self.music_start_label)
        self.music_start_slider = NeonSlider(min=0, max=0, value=0, step=.1, size_hint_y=None, height=dp(42), disabled=True)
        self.music_start_slider.bind(value=lambda _, value: setattr(
            self.music_start_label, 'text', f'MÜZİK BAŞLANGICI · {value:.1f} sn'))
        self.content.add_widget(self.music_start_slider)
        self.test_music_button = button('TEST ET', self.test_music, secondary=True)
        self.content.add_widget(self.test_music_button)
        self.content.add_widget(caption('Çalma süresini Maç Oluştur ekranından ayarlayabilirsiniz.', height=42))
        clears = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
        clears.add_widget(button('Logoyu kaldır', lambda: self.clear_media('logo'), secondary=True))
        clears.add_widget(button('MP3 kaldır', lambda: self.clear_media('music'), secondary=True))
        self.content.add_widget(clears)
        self.content.add_widget(button('KAYDET', self.save))
        self.content.add_widget(button('YENİ TAKIM / VAZGEÇ', self.reset_form, secondary=True))
        self.content.add_widget(caption('KAYITLI TAKIMLAR', bold=True))
        self.team_list = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(8))
        self.team_list.bind(minimum_height=self.team_list.setter('height'))
        self.content.add_widget(self.team_list)

    def on_pre_enter(self, *_):
        self.refresh_list()
        self.status.text = self.router.store.warning

    def on_pre_leave(self, *_):
        self.cancel_test_status()
        audio = getattr(self.router, 'audio', None)
        if audio and hasattr(audio, 'stop_preview'):
            audio.stop_preview(unload=True)

    def cancel_test_status(self):
        if self.test_status_event:
            self.test_status_event.cancel()
            self.test_status_event = None

    def music_path(self):
        if self.pending_music is not None:
            return self.pending_music or None
        team = self.router.store.get(self.edit_id) if self.edit_id else None
        return self.router.store.asset_path(team.get('music', '')) if team else None

    def configure_music(self, path, start=0., duration=5.):
        self.cancel_test_status()
        self.music_duration = duration
        audio = getattr(self.router, 'audio', None)
        self.music_length = audio.prepare_preview(path) if audio and hasattr(audio, 'prepare_preview') else 0.
        self.music_start_slider.max = max_music_start(self.music_length, duration) if self.music_length else max(0., start)
        self.music_start_slider.value = min(start, self.music_start_slider.max)
        self.music_start_slider.disabled = self.music_length <= 0
        self.test_music_button.disabled = not path or self.music_length <= 0

    def test_music(self):
        self.cancel_test_status()
        audio = getattr(self.router, 'audio', None)
        path = self.music_path()
        if not audio or not path:
            self.status.text = 'Önce okunabilir bir MP3 seçin.'
            return
        if audio.preview_music(path, self.music_start_slider.value, self.music_duration):
            self.update_test_status()
        else:
            self.status.text = 'Müzik testi başlatılamadı: '+audio.diagnostics.get('music', 'dosya veya ses sağlayıcısı okunamadı.')

    def update_test_status(self, *_):
        audio = getattr(self.router, 'audio', None)
        if not audio or not audio.preview_pool:
            return
        voice = audio.preview_pool[0]
        if voice.seek_status == 'pending':
            self.status.text = 'Müzik başlangıç konumu doğrulanıyor.'
            self.test_status_event = Clock.schedule_once(self.update_test_status, .1)
        elif voice.error:
            self.status.text = 'Müzik testi başarısız: '+voice.error
        else:
            self.status.text = f'Müzik testi çalıyor; süre en fazla {self.music_duration:g} saniye.'

    def refresh_list(self):
        self.team_list.clear_widgets()
        if not self.router.store.teams:
            self.team_list.add_widget(caption('Henüz takım yok. İlk takımını kaydet.', height=42))
        for team in self.router.store.teams:
            row = BoxLayout(size_hint_y=None, height=dp(76), spacing=dp(6))
            row.add_widget(caption(team['name'], height=76, size_hint_x=.46))
            row.add_widget(button('Düzenle', lambda key=team['id']: self.edit(key), secondary=True, size_hint_x=.32))
            row.add_widget(button('Sil', lambda key=team['id']: self.delete(key), secondary=True, size_hint_x=.22))
            self.team_list.add_widget(row)

    def pick(self, kind):
        def selected(path, error):
            if error:
                self.status.text = error
            elif path:
                if kind == 'image':
                    texture = load_texture(path)
                    if texture is None:
                        self.status.text = 'Logo okunamadı. Geçerli bir PNG/JPG seçin.'
                        return
                    self.pending_logo = path
                    self.preview.texture = texture
                    self.logo_label.text = Path(path).name
                else:
                    self.pending_music = path
                    self.music_label.text = Path(path).name
                    self.configure_music(path)
                self.status.text = 'Dosya seçildi. Kalıcı kopya için Kaydet düğmesine basın.'
                if kind == 'music' and self.music_length <= 0:
                    self.status.text = 'Müzik süresi okunamadı; başlangıç ayarı ve ses testi kullanılamıyor.'
        self.router.picker.pick(kind, selected)

    def clear_media(self, kind):
        if kind == 'logo':
            self.pending_logo = ''
            self.preview.texture = None
            self.logo_label.text = 'Logo seçilmedi'
        else:
            self.pending_music = ''
            self.music_label.text = 'Gol müziği seçilmedi'
            self.configure_music(None)

    def reset_form(self):
        self.edit_id = None
        self.name_input.text = ''
        self.clear_media('logo')
        self.clear_media('music')
        self.pending_logo = self.pending_music = None

    def edit(self, key):
        team = self.router.store.get(key)
        if not team:
            return
        self.reset_form()
        self.edit_id = key
        self.name_input.text = team['name']
        self.scroll.scroll_y = 1
        logo = self.router.store.asset_path(team['logo'])
        music = self.router.store.asset_path(team['music'])
        self.preview.texture = load_texture(logo)
        self.logo_label.text = 'Kayıtlı logo' if self.preview.texture else 'Logo yok veya okunamıyor'
        self.music_label.text = 'Kayıtlı MP3' if music else 'MP3 yok veya bulunamadı'
        self.configure_music(music, team.get('goal_music_start_seconds', 0.),
                             team.get('goal_music_duration_seconds', 5.))
        self.status.text = 'Takım düzenleniyor. Değişikliklerden sonra Kaydet düğmesine basın.'

    def save(self):
        try:
            if self.pending_logo and load_texture(self.pending_logo) is None:
                raise ValueError('Seçilen logo artık okunamıyor; yeniden seçin.')
            if self.music_length and self.music_start_slider.value > max_music_start(self.music_length, self.music_duration):
                raise ValueError('Seçilen bölüm dosya sonunu aşamaz.')
            self.router.store.save(self.name_input.text, self.pending_logo, self.pending_music, self.edit_id,
                                   goal_music_start_seconds=self.music_start_slider.value,
                                   goal_music_duration_seconds=self.music_duration)
        except (ValueError, OSError) as exc:
            self.status.text = str(exc)
            return
        self.reset_form()
        self.refresh_list()
        self.status.text = 'Takım kaydedildi.'

    def delete(self, key):
        try:
            self.router.store.delete(key)
        except (ValueError, OSError) as exc:
            self.status.text = str(exc)
            return
        if self.edit_id == key:
            self.reset_form()
        self.refresh_list()
        self.status.text = 'Takım silindi.'
