import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from pydantic import BaseModel

from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPen
from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from python_mpv_jsonipc import MPV

from client.osd.osd_layout import HAlignment, VAlignment, frac_to_margin_px, frac_to_size_px, resolve_top_left
from client.osd.logo_display import LogoDisplay, LogoDisplayConfig
from client.playback.config import load_client_config, prepare_station_loading
from client.osd.mpv_overlay import MpvOverlay

SOCKET_FILE = "runtime/play_status.socket"
VOLUME_SOCKET_FILE = "runtime/volume.socket"
CONFIG_FILE_PATH = Path("client/osd/osd.json")
DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

_registered_font_families: dict[str, str] = {}


def resolve_font(font_path: str | None, pixel_size: int) -> QFont:
    """
    StatusDisplayConfig.font is a TTF file path (matching the old Pillow
    ImageFont.truetype(path, size) semantics), but Qt's QFont constructor
    takes a family name, not a path. Load the file into Qt's font database
    once per path and cache the resulting family name.

    font_size is likewise pixels (Pillow semantics), not points, so it's set
    via setPixelSize rather than the QFont point-size constructor argument.
    """
    path = font_path or DEFAULT_FONT
    family = _registered_font_families.get(path)
    if family is None:
        font_id = QFontDatabase.addApplicationFont(path)
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
        if families:
            family = families[0]
        else:
            print(f"[WARNING] Could not load font {path}, falling back to default")
            family = QFont().defaultFamily()
        _registered_font_families[path] = family

    font = QFont(family)
    font.setPixelSize(pixel_size)
    return font


class StatusDisplayConfig(BaseModel):
    socket_file: str = SOCKET_FILE
    display_time: float = 2.0
    halign: HAlignment = HAlignment.LEFT
    valign: VAlignment = VAlignment.TOP
    format_text: str = "{channel_number} - {network_name}"
    text_color: tuple[int, int, int, int] = (0, 255, 0, 200)
    font_size: int = 40
    expansion_factor: float = 1.0
    font: str | None = None
    x_margin: float = 0.1
    y_margin: float = 0.1
    delay: float = 0.0


class StatusDisplay(object):
    def __init__(self, config: StatusDisplayConfig):
        self.config = config
        self._font = resolve_font(self.config.font, self.config.font_size)
        self._string = ""

        self.time_since_change = 0
        self.last_status = None  # Track the last status to detect changes

        self.check_status()

    def check_status(self, socket_file=None):
        if socket_file is None:
            socket_file = self.config.socket_file
        try:
            with open(socket_file, "r") as f:
                status = f.read()
        except OSError:
            return

        if not status.strip():
            return

        try:
            status = json.loads(status)
        except (json.JSONDecodeError, ValueError):
            print(f"Unable to parse player status, {status}")
            return

        # Check if status field changed (e.g., from "stopped" to "playing")
        status_changed = self.last_status is None or status.get("status") != self.last_status.get("status")
        self.last_status = status

        new_string = self.config.format_text.format_map(defaultdict(str, status))
        # Reset timer if text changed OR if status changed (like stopped->playing)
        if new_string != self._string or status_changed:
            self.time_since_change = -self.config.delay
            if new_string:
                self._string = new_string

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

    def draw(self, painter: QPainter, screen_w: float, screen_h: float):
        if self.time_since_change >= self.config.display_time:
            return
        if not self._string:
            return

        painter.setFont(self._font)
        metrics = painter.fontMetrics()
        text_w = metrics.horizontalAdvance(self._string) * self.config.expansion_factor
        text_h = metrics.height() * self.config.expansion_factor

        x_margin_px = frac_to_margin_px(self.config.x_margin, screen_w)
        y_margin_px = frac_to_margin_px(self.config.y_margin, screen_h)
        x, y = resolve_top_left(
            screen_w, screen_h, text_w, text_h,
            self.config.halign, self.config.valign,
            x_margin_px, y_margin_px,
        )

        painter.setPen(QColor(*self.config.text_color))
        if self.config.expansion_factor != 1.0:
            painter.save()
            painter.translate(x, y + metrics.ascent() * self.config.expansion_factor)
            painter.scale(self.config.expansion_factor, self.config.expansion_factor)
            painter.drawText(0, 0, self._string)
            painter.restore()
        else:
            painter.drawText(int(x), int(y + metrics.ascent()), self._string)


class VolumeDisplayConfig(BaseModel):
    display_time: float = 5.0
    halign: HAlignment = HAlignment.CENTER
    valign: VAlignment = VAlignment.BOTTOM
    color: tuple[int, int, int, int] = (0, 255, 0, 200)
    width: float = 0.4
    height: float = 0.04
    x_margin: float = 0.1
    y_margin: float = 0.375
    border_thickness: float = 2.0
    padding: float = 0.008


class VolumeDisplay(object):
    def __init__(self, config: VolumeDisplayConfig):
        self.config = config
        self.volume = 0.0
        # Start hidden until we actually see a volume message.
        self.time_since_change = float("inf")

    def check_volume(self, socket_file=VOLUME_SOCKET_FILE):
        try:
            with open(socket_file, "r") as f:
                content = f.read()
        except OSError:
            return

        if not content.strip():
            return

        try:
            status = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            print(f"Unable to parse volume status, {content}")
            return

        raw_volume = status.get("volume")
        if raw_volume is None:
            return

        # The volume field can arrive in several shapes depending on the mixer:
        # "75%", "MUTED (75%)", "unknown", "MUTE", etc. Pull the first number
        # out of whatever we get so a decorated string still drives the meter. If
        # there's no number at all (e.g. "unknown"), there's nothing to show.
        match = re.search(r"\d+(?:\.\d+)?", str(raw_volume))
        if not match:
            print(f"No volume level in volume status, {raw_volume}")
            return
        pct = float(match.group())

        self.volume = max(0.0, min(1.0, pct / 100.0))
        self.time_since_change = 0.0

        # Truncate the socket so we only display each change once.
        try:
            with open(socket_file, "w"):
                pass
        except OSError:
            pass

    def update(self, dt):
        self.time_since_change += dt
        self.check_volume()

    def draw(self, painter: QPainter, screen_w: float, screen_h: float):
        if self.time_since_change >= self.config.display_time:
            return

        w = frac_to_size_px(self.config.width, screen_w)
        h = frac_to_size_px(self.config.height, screen_h)
        x_margin_px = frac_to_margin_px(self.config.x_margin, screen_w)
        y_margin_px = frac_to_margin_px(self.config.y_margin, screen_h)
        x, y = resolve_top_left(
            screen_w, screen_h, w, h,
            self.config.halign, self.config.valign,
            x_margin_px, y_margin_px,
        )

        color = QColor(*self.config.color)

        painter.setPen(QPen(color, self.config.border_thickness))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(int(x), int(y), int(w), int(h))

        pad_x = frac_to_margin_px(self.config.padding, screen_w)
        pad_y = frac_to_margin_px(self.config.padding, screen_h)
        inner_h = h - 2.0 * pad_y
        inner_w = (w - 2.0 * pad_x) * self.volume
        if inner_w > 0.0 and inner_h > 0.0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRect(int(x + pad_x), int(y + pad_y), int(inner_w), int(inner_h))


def load_objects() -> list:
    objects = []

    if CONFIG_FILE_PATH.exists():
        with open(CONFIG_FILE_PATH, "r") as f:
            config_dict = json.load(f)
            for obj in config_dict:
                if "type" not in obj:
                    obj["type"] = "StatusDisplay"
                if obj["type"] == "StatusDisplay":
                    del obj["type"]
                    config = StatusDisplayConfig.model_validate(obj)
                    objects.append(StatusDisplay(config))
                elif obj["type"] == "LogoDisplay":
                    del obj["type"]
                    config = LogoDisplayConfig.model_validate(obj)
                    objects.append(LogoDisplay(config))
                elif obj["type"] == "HybridDisplay":
                    del obj["type"]
                    config_status = StatusDisplayConfig.model_validate(obj)
                    config_logo = LogoDisplayConfig.model_validate(obj)
                    status_osd = StatusDisplay(config_status)
                    status_logo = LogoDisplay(config_logo)
                    objects.append(status_logo)
                    objects.append(status_osd)
                elif obj["type"] == "VolumeDisplay":
                    del obj["type"]
                    config = VolumeDisplayConfig.model_validate(obj)
                    objects.append(VolumeDisplay(config))
                else:
                    print(f"Unrecognized osd object type: {obj['type']}")
    else:
        config = StatusDisplayConfig()
        objects.append(StatusDisplay(config))

    # Always show a volume meter unless one was explicitly configured. Match its
    # color to the first StatusDisplay so it blends with the rest of the OSD.
    if not any(isinstance(obj, VolumeDisplay) for obj in objects):
        volume_config = VolumeDisplayConfig()
        for obj in objects:
            if isinstance(obj, StatusDisplay):
                volume_config.color = obj.config.text_color
                break
        objects.append(VolumeDisplay(volume_config))

    return objects


# where the OSD's frames go for mpv to read: shared memory, never the SD card. In Docker the client
# and the OSD share a tmpfs at this path (client/compose.yml)
OVERLAY_FILE = os.environ.get("FS42_OSD_FILE", "/dev/shm/fs42-osd.bgra")
MPV_SOCKET = "runtime/mpv.socket"


class MpvOsd:
    """Draws the OSD objects ~30 times a second into an mpv overlay over the video."""

    def __init__(self, objects: list, connect=None):
        self.objects = objects
        self._connect = connect or (lambda: MPV(start_mpv=False, ipc_socket=MPV_SOCKET))
        self.overlay = None

        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        self._last_ns = self._elapsed.nsecsElapsed()

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / 30))  # ~30 FPS, matching the old glfw.wait_events_timeout cadence

    def _tick(self):
        now_ns = self._elapsed.nsecsElapsed()
        dt = (now_ns - self._last_ns) / 1e9
        self._last_ns = now_ns

        for obj in self.objects:
            obj.update(dt)

        try:
            if self.overlay is None:
                self.overlay = MpvOverlay(self._connect(), OVERLAY_FILE)
            self.draw(self.overlay)
        except Exception as e:
            # the player isn't up yet, or restarted mpv: connect again on a later tick
            print(f"OSD waiting for mpv: {e}")
            self.overlay = None

    def draw(self, overlay):
        image = overlay.frame()
        if image is None:
            return
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)  # bilinear-scale logos, matching the old GL_LINEAR filtering

        w, h = image.width(), image.height()
        # Draw objects with StatusDisplay on top, same ordering as before.
        for obj in sorted(self.objects, key=lambda o: isinstance(o, StatusDisplay)):
            obj.draw(painter, w, h)

        painter.end()
        overlay.present()


def main():
    prepare_station_loading(load_client_config())
    # no window: Qt only draws into memory, so the OSD needs no X11 or Wayland
    app = QGuiApplication([sys.argv[0], "-platform", "offscreen"])
    osd = MpvOsd(load_objects())  # noqa: F841 - its timer drives the OSD
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
