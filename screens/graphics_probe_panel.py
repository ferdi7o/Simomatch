"""In-app controls; no new APK is needed between GPU isolation runs."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from screens.setup_controls import Surface, Action, label, MUTED
from services.graphics_probe import MODES, RENDERERS, TARGETS
from services.graphics_diagnostics import milestone


def refresh_probe_button(screen):
    if not hasattr(screen,'graphics_probe_button'): return
    theme = screen.theme.text
    selection = screen.graphics_probe.selection(theme)
    value = 'KAPALI' if selection.mode is None else f'MODE {selection.mode} - {MODES[selection.mode]}'
    screen.graphics_probe_button.text = 'GPU Teşhis Modu: '+value
    screen.graphics_probe_button.disabled = theme not in TARGETS


def open_probe_panel(screen):
    theme = screen.theme.text
    if theme not in TARGETS or screen.probe_dialog: return
    selection = screen.graphics_probe.selection(theme)
    renderer = [selection.renderer]
    panel = Surface(orientation='vertical',padding=dp(12),spacing=dp(8))
    panel.add_widget(label('GPU Teşhis Modu - '+theme, height=28,bold=True,font_size=dp(12)))
    panel.add_widget(label('Seçim sonraki maçta uygulanır ve çökme sonrası korunur.\n'
                           'MODE 1/3: statik, maskesiz PNG. Fizik değişmez.\n'
                           'Özel shader yok = Kivy standart shader; GLES çizimi sürer.',
                           height=74,shorten=False,font_size=dp(11),color=MUTED))
    scroll = ScrollView(do_scroll_x=False)
    content = BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(8))
    content.bind(minimum_height=content.setter('height'))
    scroll.add_widget(content); panel.add_widget(scroll)
    def choose(mode):
        try:
            screen.graphics_probe.save(theme,mode,renderer[0])
        except OSError as error:
            screen.status.text = 'Teşhis seçimi kaydedilemedi: '+str(error)
            return
        milestone('GRAPHICS_PROBE_SELECTED',theme=theme,mode=mode,renderer=renderer[0])
        screen.status.text = 'Grafik teşhisi sonraki maçta uygulanacak.'
        refresh_probe_button(screen)
        screen.probe_dialog.dismiss()
    screen.probe_mode_buttons = {}
    for mode,title in enumerate(MODES):
        button = Action(f'MODE {mode} - {title}',lambda m=mode:choose(m),
                        primary=selection.mode == mode,height=dp(42),font_size=dp(11))
        content.add_widget(button); screen.probe_mode_buttons[mode] = button
    def cycle():
        renderer[0] = RENDERERS[(RENDERERS.index(renderer[0])+1)%len(RENDERERS)]
        render_button.text = 'EFEKT YOLU: '+renderer[0]
    render_button = Action('EFEKT YOLU: '+renderer[0],cycle,height=dp(40),font_size=dp(11))
    screen.probe_renderer_button = render_button
    content.add_widget(render_button)
    content.add_widget(label('auto: mevcut platform yolu; texture: standart shader\n'
                             'custom: özel shader; flat_probe: aynı geometri / düz renk.\n'
                             'Yol seçtikten sonra MODE düğmesine basın.',height=70,
                             shorten=False,font_size=dp(10),color=MUTED))
    content.add_widget(Action('TEŞHİSİ KAPAT - MEVCUT ÇİZİM',lambda:choose(None),font_size=dp(10)))
    panel.add_widget(Action('VAZGEÇ',lambda:screen.probe_dialog.dismiss()))
    dialog = ModalView(size_hint=(.94,.9),background_color=(0,0,0,.8))
    dialog.add_widget(panel)
    screen.probe_dialog = dialog
    dialog.bind(on_dismiss=lambda *_:setattr(screen,'probe_dialog',None))
    dialog.open()
