"""Optional immersive UI. All Android imports and window mutations stay gated."""
import logging

log = logging.getLogger(__name__)


class ImmersiveDisplay:
    def __init__(self, platform, window, schedule):
        self.enabled = platform == 'android'
        self.window, self.schedule = window, schedule
        self.active, self.pending = False, None
        self.diagnostics = ''

    def start(self):
        if not self.enabled:
            return
        if not self.active:
            self.active = True
            self.window.bind(focus=self.focus, size=self.request)
        self.request()

    def focus(self, _, focused):
        if focused:
            self.request()

    def request(self, *_):
        if not self.active:
            return
        if self.pending:
            self.pending.cancel()
        self.pending = self.schedule(self.apply, .15)

    def apply(self, *_):
        self.pending = None
        if not self.active:
            return
        try:
            from android.runnable import run_on_ui_thread
            run_on_ui_thread(self._apply_android)()
        except Exception as exc:
            self.diagnostics = str(exc)
            log.warning('Immersive UI could not be applied: %s', exc)

    def _apply_android(self):
        if not self.active:
            return
        try:
            from jnius import autoclass
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            window = activity.getWindow()
            decor = window.getDecorView()
            sdk = autoclass('android.os.Build$VERSION').SDK_INT
            if sdk >= 30:
                window.setDecorFitsSystemWindows(False)
                controller = window.getInsetsController()
                if controller is None:
                    raise RuntimeError('WindowInsetsController not attached yet')
                controller.setSystemBarsBehavior(2)  # TRANSIENT_BARS_BY_SWIPE
                controller.hide(autoclass('android.view.WindowInsets$Type').systemBars())
                self.diagnostics = 'WindowInsetsController'
            else:
                try:
                    from android.display_cutout import set_immersive_mode
                    set_immersive_mode(True, True, True)
                    self.diagnostics = 'android.display_cutout.set_immersive_mode'
                except Exception:
                    decor.setSystemUiVisibility(0x100 | 0x200 | 0x400 | 0x2 | 0x4 | 0x1000)
                    self.diagnostics = 'legacy immersive-sticky flags'
            if sdk >= 29:
                window.setNavigationBarContrastEnforced(False)
                window.setStatusBarContrastEnforced(False)
            # Reserve physical camera cutouts, not transient system bar heights.
            # Native content padding resizes the SDL surface; existing responsive
            # Kivy layouts continue to use its usable size without physics edits.
            if sdk >= 28:
                insets = decor.getRootWindowInsets()
                cutout = insets.getDisplayCutout() if insets else None
                padding = ((cutout.getSafeInsetLeft(), cutout.getSafeInsetTop(),
                            cutout.getSafeInsetRight(), cutout.getSafeInsetBottom()) if cutout else (0, 0, 0, 0))
                content = window.findViewById(autoclass('android.R$id').content)
                if content:
                    content.setPadding(*padding)
        except Exception as exc:
            self.diagnostics = str(exc)
            log.warning('Android immersive configuration failed: %s', exc)

    def close(self):
        self.active = False
        if self.pending:
            self.pending.cancel()
        if self.enabled:
            self.window.unbind(focus=self.focus, size=self.request)
