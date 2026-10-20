"""The OSD's looks besides the original green "vcr" one (drawn in client/osd/main.py).

Each style draws the channel (number, network and what's on) and the volume bar or mute sign. The
designs are made for a 1920x1080 picture and scale with it.
"""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF

FONTS = Path(__file__).parent / "fonts"
_families = {}


def _font(file, px, weight=QFont.Normal):
    if file not in _families:
        ids = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(FONTS / file)))
        _families[file] = ids[0] if ids else QFont().defaultFamily()
    font = QFont(_families[file])
    font.setPixelSize(max(1, int(px)))
    font.setWeight(weight)
    return font


def _speaker(painter, x, y, size, color):
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRect(QRectF(x, y + size * 0.3, size * 0.3, size * 0.4))
    painter.drawPolygon(QPolygonF([QPointF(x + size * 0.3, y + size * 0.3), QPointF(x + size * 0.65, y),
                                   QPointF(x + size * 0.65, y + size), QPointF(x + size * 0.3, y + size * 0.7)]))
    painter.setPen(QPen(color, max(2.0, size * 0.1)))
    painter.drawLine(QPointF(x + size * 0.8, y + size * 0.3), QPointF(x + size * 1.2, y + size * 0.7))
    painter.drawLine(QPointF(x + size * 0.8, y + size * 0.7), QPointF(x + size * 1.2, y + size * 0.3))


# ---- cable: a late-90s cable box ----------------------------------------------------------------

CABLE_PANEL = QColor(10, 14, 28, 190)
CABLE_ACCENT = QColor(0, 190, 230)


def cable_status(painter: QPainter, w, h, status):
    s = h / 1080
    channel, network = str(status.get("channel_number", "")), str(status.get("network_name", "")).upper()
    title = str(status.get("title") or "").upper()
    painter.setFont(_font("Michroma-Regular.ttf", 38 * s))
    name_w = painter.fontMetrics().horizontalAdvance(network)
    painter.setFont(_font("Michroma-Regular.ttf", 20 * s))
    title_w = painter.fontMetrics().horizontalAdvance(title)
    # the box grows with the name and the programme, up to most of the screen
    width = min(max(620 * s, 220 * s + max(name_w, title_w)), w - 160 * s)
    painter.setPen(Qt.NoPen)
    painter.setBrush(CABLE_PANEL)
    painter.drawRoundedRect(QRectF(80 * s, 70 * s, width, 150 * s), 10 * s, 10 * s)
    painter.setBrush(CABLE_ACCENT)
    painter.drawRect(QRectF(80 * s, 70 * s, 150 * s, 150 * s))
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(_font("Michroma-Regular.ttf", (84 if len(channel) < 3 else 60) * s))
    painter.drawText(QRectF(80 * s, 70 * s, 150 * s, 150 * s), Qt.AlignCenter, channel)
    painter.setFont(_font("Michroma-Regular.ttf", 38 * s))
    painter.drawText(QPointF(260 * s, 135 * s), network)
    if title:
        painter.setPen(QColor(170, 200, 215))
        painter.setFont(_font("Michroma-Regular.ttf", 20 * s))
        painter.drawText(QPointF(262 * s, 185 * s), painter.fontMetrics().elidedText(title, Qt.ElideRight, int(width - 205 * s)))


def cable_volume(painter: QPainter, w, h, volume, muted):
    s = h / 1080
    x, y = (w - 800 * s) / 2, h - 180 * s
    painter.setPen(Qt.NoPen)
    painter.setBrush(CABLE_PANEL)
    painter.drawRoundedRect(QRectF(x, y, 800 * s, 90 * s), 10 * s, 10 * s)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(_font("Michroma-Regular.ttf", 22 * s))
    if muted:
        _speaker(painter, x + 30 * s, y + 25 * s, 40 * s, CABLE_ACCENT)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(_font("Michroma-Regular.ttf", 30 * s))
        painter.drawText(QPointF(x + 110 * s, y + 60 * s), "MUTE")
        return
    painter.drawText(QPointF(x + 30 * s, y + 58 * s), "VOLUME")
    lit = round(volume * 25)
    painter.setPen(Qt.NoPen)
    for i in range(25):
        painter.setBrush(CABLE_ACCENT if i < lit else QColor(255, 255, 255, 50))
        painter.drawRect(QRectF(x + 200 * s + i * 20 * s, y + 25 * s, 13 * s, 40 * s))
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(_font("Michroma-Regular.ttf", 26 * s))
    painter.drawText(QPointF(x + 720 * s, y + 60 * s), str(round(volume * 100)))


# ---- kids: round and bright ---------------------------------------------------------------------

KIDS_INK = QColor(30, 40, 120)
KIDS_YELLOW = QColor(255, 205, 40)
KIDS_PINK = QColor(240, 70, 120)


def kids_status(painter: QPainter, w, h, status):
    s = h / 1080
    channel, network = str(status.get("channel_number", "")), str(status.get("network_name", ""))
    name_font = _font("Fredoka-Variable.ttf", 64 * s, QFont.Bold)
    painter.setFont(name_font)
    width = max(560 * s, 175 * s + painter.fontMetrics().horizontalAdvance(network) + 50 * s)
    painter.setPen(QPen(KIDS_INK, 6 * s))
    painter.setBrush(KIDS_YELLOW)
    painter.drawRoundedRect(QRectF(80 * s, 70 * s, width, 130 * s), 65 * s, 65 * s)
    painter.setBrush(KIDS_PINK)
    painter.drawEllipse(QRectF(90 * s, 80 * s, 110 * s, 110 * s))
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(_font("Fredoka-Variable.ttf", (80 if len(channel) < 3 else 56) * s, QFont.Bold))
    painter.drawText(QRectF(90 * s, 76 * s, 110 * s, 110 * s), Qt.AlignCenter, channel)
    path = QPainterPath()
    path.addText(QPointF(225 * s, 158 * s), name_font, network)
    painter.setPen(QPen(KIDS_INK, 8 * s))
    painter.drawPath(path)
    painter.fillPath(path, QColor(255, 255, 255))


def kids_volume(painter: QPainter, w, h, volume, muted):
    s = h / 1080
    x, y = (w - 700 * s) / 2, h - 175 * s
    painter.setPen(QPen(KIDS_INK, 6 * s))
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRoundedRect(QRectF(x, y, 700 * s, 80 * s), 40 * s, 40 * s)
    if muted:
        # no words: a crossed-out speaker reads in any language, and to a toddler
        _speaker(painter, x + 290 * s, y + 10 * s, 60 * s, KIDS_PINK)
        return
    gradient = QLinearGradient(x + 15 * s, 0, x + 685 * s, 0)
    for stop, color in [(0, QColor(80, 200, 120)), (0.5, KIDS_YELLOW), (1, KIDS_PINK)]:
        gradient.setColorAt(stop, color)
    if volume > 0:
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(x + 15 * s, y + 15 * s, max(50 * s, 670 * s * volume), 50 * s), 25 * s, 25 * s)


STATUS = {"cable": cable_status, "kids": kids_status}
VOLUME = {"cable": cable_volume, "kids": kids_volume}
