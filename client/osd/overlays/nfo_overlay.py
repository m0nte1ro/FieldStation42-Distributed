import multiprocessing
import logging

_logger = logging.getLogger("NFOOverlay")

MAX_NFO_LINES = 5


_OVERLAY_DEFAULTS = {
    "overlay_effect": "outline",
    "overlay_offset_px": 2,
    "overlay_font_path": None,
    "overlay_text_color": [255, 255, 255, 255],
    "overlay_shadow_color": [0, 0, 0, 255],
    "overlay_title_size": 30,
    "overlay_body_size": 20,
    "overlay_title_weight": "bold",
    "overlay_body_weight": "normal",
    "overlay_type": "normal",
    "overlay_fade_duration_ms": 600,
}



class NFOData:

    def __init__(self, lines):
        self.lines = lines  # list of non-empty strings, up to MAX_NFO_LINES

    @property
    def title(self):
        return self.lines[0] if self.lines else ""

    @property
    def info(self):
        return self.lines[1] if len(self.lines) > 1 else ""

    @property
    def description(self):
        return self.lines[2] if len(self.lines) > 2 else ""


DEFAULT_SHOW_SECONDS = 10



def _run_overlay_app(lines, play_duration, show_seconds, overlay_cfg):

    import sys
    import signal
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtGui import QColor, QPainter, QFont, QFontMetrics, QFontDatabase
    from PySide6.QtCore import Qt, QTimer

    def _qt_weight(weight_str):
        return QFont.Bold if weight_str == "bold" else QFont.Normal

    class NFOOverlayWindow(QWidget):
        def __init__(self, nfo_lines):
            super().__init__()
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_NoSystemBackground)
            self.setAutoFillBackground(False)
            self.setStyleSheet("background: transparent;")
            self.setCursor(Qt.BlankCursor)

            screen = QApplication.primaryScreen()
            if screen:
                screen_rect = screen.geometry()
                self.setGeometry(screen_rect)
                screen_height = screen_rect.height()
            else:
                screen_height = 1080

            self.scale = screen_height / 1080.0

            if overlay_cfg["overlay_type"] == "minimal":
                self.lines = nfo_lines[:2]
            else:
                self.lines = nfo_lines

            font_family = "Arial"
            font_path = overlay_cfg["overlay_font_path"]
            if font_path and os.path.exists(font_path):
                font_id = QFontDatabase.addApplicationFont(font_path)
                if font_id >= 0:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        font_family = families[0]

            self.title_font = QFont(font_family, int(overlay_cfg["overlay_title_size"] * self.scale), _qt_weight(overlay_cfg["overlay_title_weight"]))
            self.body_font = QFont(font_family, int(overlay_cfg["overlay_body_size"] * self.scale), _qt_weight(overlay_cfg["overlay_body_weight"]))

            self.text_color = QColor(*overlay_cfg["overlay_text_color"])
            self.effect_color = QColor(*overlay_cfg["overlay_shadow_color"])
            self.opacity = 1.0

        def _draw_drop_shadow(self, painter, x, y, text, font, px):
            painter.setFont(font)
            painter.setPen(self.effect_color)
            for i in range(1, px + 1):
                painter.drawText(x + i, y + i, text)
            painter.setPen(self.text_color)
            painter.drawText(x, y, text)

        def _draw_outline(self, painter, x, y, text, font, px):
            painter.setFont(font)
            offsets = [
                (-px, -px), (0, -px), (px, -px),
                (-px,   0),           (px,   0),
                (-px,  px), (0,  px), (px,  px),
            ]
            painter.setPen(self.effect_color)
            for dx, dy in offsets:
                painter.drawText(x + dx, y + dy, text)
            painter.setPen(self.text_color)
            painter.drawText(x, y, text)

        def _draw_text(self, painter, x, y, text, font, px):
            if overlay_cfg["overlay_effect"] == "drop_shadow":
                self._draw_drop_shadow(painter, x, y, text, font, px)
            else:
                self._draw_outline(painter, x, y, text, font, px)

        def paintEvent(self, event):
            if not self.lines:
                return

            from PySide6.QtGui import QPixmap

            # Render text and effect to an off-screen pixmap at full opacity so
            # overlapping shadow copies composite correctly, then draw the whole
            # pixmap onto the widget at self.opacity so everything fades as one.
            pixmap = QPixmap(self.size())
            pixmap.fill(Qt.transparent)

            pm = QPainter(pixmap)
            pm.setRenderHint(QPainter.Antialiasing)
            pm.setRenderHint(QPainter.TextAntialiasing)

            scale = self.scale
            margin_x = int(80 * scale)
            margin_y = int(80 * scale)
            px = max(1, int(overlay_cfg["overlay_offset_px"] * scale))

            title_metrics = QFontMetrics(self.title_font)
            body_metrics = QFontMetrics(self.body_font)

            title_line_h = int(title_metrics.height() * 1.2)
            body_line_h = int(body_metrics.height() * 1.2)

            # Anchor to the bottom of the screen
            total_h = title_line_h + body_line_h * (len(self.lines) - 1)
            start_y = self.height() - margin_y - total_h

            x = margin_x
            y = start_y + title_metrics.ascent()
            self._draw_text(pm, x, y, self.lines[0], self.title_font, px)

            y += title_line_h
            for line in self.lines[1:]:
                self._draw_text(pm, x, y, line, self.body_font, px)
                y += body_line_h

            pm.end()

            painter = QPainter(self)
            painter.setOpacity(self.opacity)
            painter.drawPixmap(0, 0, pixmap)
            painter.end()

    FADE_INTERVAL_MS = 30  # ~33 fps

    def fade_out(on_done=None):
        steps = max(1, overlay_cfg["overlay_fade_duration_ms"] // FADE_INTERVAL_MS)
        step_size = 1.0 / steps
        timer = QTimer()

        def tick():
            window.opacity = max(0.0, window.opacity - step_size)
            window.update()
            if window.opacity <= 0.0:
                timer.stop()
                if on_done:
                    on_done()

        window._fade_timer = timer  # prevent GC
        timer.timeout.connect(tick)
        timer.start(FADE_INTERVAL_MS)

    def fade_in():
        window.opacity = 0.0
        window.show()
        steps = max(1, overlay_cfg["overlay_fade_duration_ms"] // FADE_INTERVAL_MS)
        step_size = 1.0 / steps
        timer = QTimer()

        def tick():
            window.opacity = min(1.0, window.opacity + step_size)
            window.update()
            if window.opacity >= 1.0:
                timer.stop()

        window._fade_timer = timer  # prevent GC
        timer.timeout.connect(tick)
        timer.start(FADE_INTERVAL_MS)

    def signal_handler(sig, frame):
        QApplication.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app = QApplication(sys.argv)
    window = NFOOverlayWindow(nfo_lines=lines)
    window.show()

    # Set up show/hide timers when we know how long the clip runs.
    # Only bother if the clip is long enough to have a hidden middle section.
    if play_duration is not None and play_duration > show_seconds * 2:
        hide_timer = QTimer()
        hide_timer.setSingleShot(True)
        hide_timer.timeout.connect(lambda: fade_out(on_done=window.hide))
        hide_timer.start(int(show_seconds * 1000))

        show_timer = QTimer()
        show_timer.setSingleShot(True)
        show_timer.timeout.connect(fade_in)
        show_timer.start(int((play_duration - show_seconds) * 1000))

    sys.exit(app.exec())



class NFOOverlay:
    """The on-screen overlay for music and plaintext NFO metadata."""

    @staticmethod
    def _load_overlay_config():
        cfg = dict(_OVERLAY_DEFAULTS)
        try:
            from shared.stations.manager import StationManager
            main_conf = StationManager().server_conf
            overlay_conf = main_conf.get("overlay_conf", {})
            for key in _OVERLAY_DEFAULTS:
                if key in overlay_conf:
                    cfg[key] = overlay_conf[key]
        except Exception as e:
            _logger.warning(f"Could not load overlay config from StationManager: {e}")
        return cfg

    OVERLAY_TYPES = ("music", "plaintext")


    @staticmethod
    def overlay_lines(meta):

        if not meta:
            return None

        meta_type = meta.get("type")
        if meta_type == "music":
            ordered = [meta.get(k, "") for k in ("artist", "title", "album", "year")]
            lines = [str(l) for l in ordered if l][:MAX_NFO_LINES]
            return lines or None
        if meta_type == "plaintext":
            lines = [l for l in meta.get("lines", []) if l][:MAX_NFO_LINES]
            return lines or None
        return None

    @staticmethod
    def show_overlay(nfo_data, play_duration=None, show_seconds=DEFAULT_SHOW_SECONDS):

        if nfo_data is None:
            return None
        try:
            overlay_cfg = NFOOverlay._load_overlay_config()
            process = multiprocessing.Process(
                target=_run_overlay_app,
                args=(nfo_data.lines, play_duration, show_seconds, overlay_cfg),
                daemon=True,
            )
            process.start()
            _logger.info(
                f"NFO overlay started (pid={process.pid}) '{nfo_data.title}'"
                + (f" play_duration={play_duration:.1f}s" if play_duration else " permanent")
            )
            return process
        except Exception as e:
            _logger.error(f"Failed to start NFO overlay: {e}")
            return None

    @staticmethod
    def close_overlay(process):

        if not process or not process.is_alive():
            return
        try:
            process.terminate()
            process.join(timeout=0.2)
            if process.is_alive():
                process.kill()
                process.join(timeout=0.1)
            _logger.debug("NFO overlay closed")
        except Exception as e:
            _logger.warning(f"Error closing NFO overlay: {e}")
