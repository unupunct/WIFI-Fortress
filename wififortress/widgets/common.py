"""Reusable widgets: cards, stat tiles, pills, signal bars, step indicator."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from wififortress.ui.theme import PALETTE, SEVERITY_COLORS, STATUS_COLORS


# ---------------------------------------------------------------------------
# Icons drawn with QPainter (no external asset dependency, crisp on HiDPI)
# ---------------------------------------------------------------------------

def _icon_pixmap(name: str, size: int = 22, color: str | None = None) -> QPixmap:
    color = color or PALETTE.accent
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), max(1.4, size / 12))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    s = size
    m = s * 0.18

    def line(x1, y1, x2, y2):
        painter.drawLine(int(x1), int(y1), int(x2), int(y2))

    if name == "dashboard":
        painter.drawRoundedRect(QRectF(m, m, s * 0.28, s * 0.28), 2, 2)
        painter.drawRoundedRect(QRectF(s * 0.54, m, s * 0.28, s * 0.28), 2, 2)
        painter.drawRoundedRect(QRectF(m, s * 0.54, s * 0.28, s * 0.28), 2, 2)
        painter.drawRoundedRect(QRectF(s * 0.54, s * 0.54, s * 0.28, s * 0.28), 2, 2)
    elif name == "wifi":
        for i, frac in enumerate((0.55, 0.72, 0.9)):
            rect = QRectF(s / 2 - s * frac / 2, s / 2 - s * frac / 2, s * frac, s * frac)
            painter.drawArc(rect, 45 * 16, 90 * 16)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(s / 2 - s * 0.06, s * 0.72, s * 0.12, s * 0.12))
    elif name == "key":
        painter.drawEllipse(QRectF(m, s * 0.3, s * 0.34, s * 0.34))
        line(s * 0.5, s * 0.5, s * 0.86, s * 0.5)
        line(s * 0.72, s * 0.5, s * 0.72, s * 0.66)
        line(s * 0.82, s * 0.5, s * 0.82, s * 0.62)
    elif name == "shield":
        path = QPainterPath()
        path.moveTo(s / 2, m * 0.7)
        path.lineTo(s - m, s * 0.3)
        path.lineTo(s - m, s * 0.55)
        path.cubicTo(s - m, s * 0.78, s * 0.7, s * 0.88, s / 2, s - m * 0.6)
        path.cubicTo(s * 0.3, s * 0.88, m, s * 0.78, m, s * 0.55)
        path.lineTo(m, s * 0.3)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "tools":
        line(s * 0.25, s * 0.75, s * 0.65, s * 0.35)
        painter.drawEllipse(QRectF(s * 0.6, s * 0.12, s * 0.28, s * 0.28))
        line(s * 0.3, s * 0.3, s * 0.7, s * 0.7)
        painter.drawEllipse(QRectF(s * 0.12, s * 0.6, s * 0.28, s * 0.28))
    elif name == "adapter":
        painter.drawRoundedRect(QRectF(m, s * 0.45, s * 0.6, s * 0.34), 3, 3)
        line(s * 0.8, s * 0.62, s * 0.92, s * 0.62)
        line(s * 0.3, s * 0.45, s * 0.3, s * 0.3)
        line(s * 0.5, s * 0.45, s * 0.5, s * 0.24)
    elif name == "lock":
        painter.drawRoundedRect(QRectF(m, s * 0.45, s * 0.64, s * 0.4), 3, 3)
        painter.drawArc(QRectF(s * 0.3, m, s * 0.38, s * 0.5), 0, 180 * 16)
    elif name == "book":
        painter.drawRect(QRectF(m, m, s - 2 * m, s - 2 * m))
        line(s * 0.38, m, s * 0.38, s - m)
        line(s * 0.5, s * 0.3, s - m * 1.4, s * 0.3)
        line(s * 0.5, s * 0.5, s - m * 1.4, s * 0.5)
    elif name == "pulse":
        path = QPainterPath()
        path.moveTo(m, s * 0.55)
        path.lineTo(s * 0.32, s * 0.55)
        path.lineTo(s * 0.42, s * 0.25)
        path.lineTo(s * 0.55, s * 0.78)
        path.lineTo(s * 0.66, s * 0.45)
        path.lineTo(s - m, s * 0.45)
        painter.drawPath(path)
    elif name == "report":
        painter.drawRoundedRect(QRectF(s * 0.22, m, s * 0.56, s - 2 * m), 2, 2)
        for y in (0.35, 0.5, 0.65):
            line(s * 0.32, s * y, s * 0.68, s * y)
    elif name == "settings":
        painter.drawEllipse(QRectF(s * 0.3, s * 0.3, s * 0.4, s * 0.4))
        for x1, y1, x2, y2 in (
            (0.5, 0.1, 0.5, 0.26), (0.5, 0.74, 0.5, 0.9),
            (0.1, 0.5, 0.26, 0.5), (0.74, 0.5, 0.9, 0.5),
            (0.22, 0.22, 0.33, 0.33), (0.67, 0.67, 0.78, 0.78),
            (0.78, 0.22, 0.67, 0.33), (0.33, 0.67, 0.22, 0.78),
        ):
            line(s * x1, s * y1, s * x2, s * y2)
    elif name == "refresh":
        painter.drawArc(QRectF(m, m, s - 2 * m, s - 2 * m), 40 * 16, 280 * 16)
        line(s * 0.78, s * 0.16, s * 0.78, s * 0.38)
        line(s * 0.78, s * 0.38, s * 0.56, s * 0.38)
    elif name == "check":
        line(s * 0.2, s * 0.55, s * 0.42, s * 0.76)
        line(s * 0.42, s * 0.76, s * 0.82, s * 0.26)
    elif name == "warning":
        path = QPainterPath()
        path.moveTo(s / 2, m)
        path.lineTo(s - m, s - m)
        path.lineTo(m, s - m)
        path.closeSubpath()
        painter.drawPath(path)
        line(s * 0.5, s * 0.4, s * 0.5, s * 0.62)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(s * 0.46, s * 0.68, s * 0.08, s * 0.08))
    elif name == "copy":
        painter.drawRoundedRect(QRectF(m, s * 0.28, s * 0.44, s * 0.5), 2, 2)
        painter.drawRoundedRect(QRectF(s * 0.32, m, s * 0.44, s * 0.5), 2, 2)
    elif name == "eye":
        path = QPainterPath()
        path.moveTo(m, s * 0.5)
        path.cubicTo(s * 0.32, s * 0.2, s * 0.68, s * 0.2, s - m, s * 0.5)
        path.cubicTo(s * 0.68, s * 0.8, s * 0.32, s * 0.8, m, s * 0.5)
        painter.drawPath(path)
        painter.drawEllipse(QRectF(s * 0.4, s * 0.4, s * 0.2, s * 0.2))
    elif name == "stop":
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44), 3, 3)
    elif name == "play":
        path = QPainterPath()
        path.moveTo(s * 0.32, m)
        path.lineTo(s * 0.82, s / 2)
        path.lineTo(s * 0.32, s - m)
        path.closeSubpath()
        painter.setBrush(QColor(color))
        painter.drawPath(path)
    else:
        painter.drawEllipse(QRectF(m, m, s - 2 * m, s - 2 * m))
    painter.end()
    return pix


def make_icon(name: str, color: str | None = None) -> QIcon:
    icon = QIcon()
    for size in (16, 22, 32, 64):
        icon.addPixmap(_icon_pixmap(name, size, color))
    return icon


def app_icon() -> QIcon:
    """Application icon: a shield with a Wi-Fi arc, in the accent colour."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        s = size
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.06)
        path.lineTo(s * 0.9, s * 0.22)
        path.lineTo(s * 0.9, s * 0.52)
        path.cubicTo(s * 0.9, s * 0.76, s * 0.72, s * 0.9, s * 0.5, s * 0.96)
        path.cubicTo(s * 0.28, s * 0.9, s * 0.1, s * 0.76, s * 0.1, s * 0.52)
        path.lineTo(s * 0.1, s * 0.22)
        path.closeSubpath()
        gradient = QColor(PALETTE.accent)
        p.setPen(QPen(gradient, max(1.0, s * 0.02)))
        p.setBrush(QColor(16, 24, 32, 235))
        p.drawPath(path)
        pen = QPen(QColor(PALETTE.accent), max(1.2, s * 0.045))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for frac in (0.34, 0.5, 0.66):
            rect = QRectF(s * 0.5 - s * frac / 2, s * 0.42 - s * frac / 2, s * frac, s * frac)
            p.drawArc(rect, 45 * 16, 90 * 16)
        p.setBrush(QColor(PALETTE.accent))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(s * 0.5 - s * 0.05, s * 0.6, s * 0.1, s * 0.1))
        p.end()
        icon.addPixmap(pix)
    return icon


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class Card(QFrame):
    """A rounded panel with an optional title and subtitle."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
        *,
        object_name: str = "Card",
        margins: tuple[int, int, int, int] = (18, 16, 18, 16),
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(*margins)
        self._layout.setSpacing(10)
        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("Muted")
        self.subtitle_label.setWordWrap(True)
        if title:
            self.header.addWidget(self.title_label)
            self.header.addStretch(1)
            self._layout.addLayout(self.header)
        if subtitle:
            self._layout.addWidget(self.subtitle_label)

    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._layout.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch: int = 0):
        self._layout.addLayout(layout, stretch)
        return layout

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)


class StatTile(Card):
    """A compact metric: big value, label and optional hint."""

    clicked = Signal()

    def __init__(
        self,
        label: str,
        value: str = "—",
        hint: str = "",
        icon: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent, margins=(16, 14, 16, 14))
        top = QHBoxLayout()
        top.setSpacing(10)
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(_icon_pixmap(icon, 26, PALETTE.accent2))
            top.addWidget(icon_label)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("StatValue")
        self.label_label = QLabel(label)
        self.label_label.setObjectName("StatLabel")
        text_col.addWidget(self.value_label)
        text_col.addWidget(self.label_label)
        top.addLayout(text_col, 1)
        self._layout.addLayout(top)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("StatHint")
        self.hint_label.setWordWrap(True)
        self._layout.addWidget(self.hint_label)
        self.setCursor(Qt.PointingHandCursor)

    def set_value(self, value: str, color: str | None = None) -> None:
        self.value_label.setText(value)
        if color:
            self.value_label.setStyleSheet(f"color: {color};")

    def set_hint(self, hint: str) -> None:
        self.hint_label.setText(hint)

    def mousePressEvent(self, event):  # noqa: N802 - Qt API
        self.clicked.emit()
        super().mousePressEvent(event)


class ActionCard(Card):
    """Large call-to-action card used on the dashboard."""

    activated = Signal()

    def __init__(
        self,
        title: str,
        body: str,
        button_text: str,
        icon: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent, object_name="ActionCard", margins=(20, 18, 20, 18))
        top = QHBoxLayout()
        top.setSpacing(12)
        if icon:
            icon_label = QLabel()
            icon_label.setPixmap(_icon_pixmap(icon, 34, PALETTE.accent))
            top.addWidget(icon_label, 0, Qt.AlignTop)
        text_col = QVBoxLayout()
        text_col.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("ActionTitle")
        self.body_label = QLabel(body)
        self.body_label.setObjectName("ActionBody")
        self.body_label.setWordWrap(True)
        text_col.addWidget(self.title_label)
        text_col.addWidget(self.body_label)
        top.addLayout(text_col, 1)
        self._layout.addLayout(top)
        self.button = QPushButton(button_text)
        self.button.setObjectName("Primary")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.activated)
        self._layout.addWidget(self.button)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)


class Pill(QLabel):
    """Small coloured status chip."""

    def __init__(self, text: str = "", color: str = PALETTE.text_muted,
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignCenter)
        self.set_status(text, color)

    def set_status(self, text: str, color: str = PALETTE.text_muted) -> None:
        self.setText(text)
        self.setStyleSheet(
            f"#Pill {{ background: rgba(255,255,255,0.04); color: {color};"
            f" border: 1px solid {color}; border-radius: 9px; padding: 2px 9px;"
            f" font-size: 11px; font-weight: 600; }}"
        )


class SeverityPill(Pill):
    def __init__(self, severity: str, parent: QWidget | None = None) -> None:
        super().__init__(severity, SEVERITY_COLORS.get(severity, PALETTE.text_muted), parent)


class StatusDot(QWidget):
    """A coloured dot with an optional label, used for diagnostics."""

    def __init__(self, status: str = "unknown", text: str = "",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(10, 10)
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        layout.addWidget(self._dot, 0, Qt.AlignTop)
        layout.addWidget(self._text, 1)
        self.set_status(status, text)

    def set_status(self, status: str, text: str | None = None) -> None:
        color = STATUS_COLORS.get(status, PALETTE.text_muted)
        self._dot.setStyleSheet(
            f"background: {color}; border-radius: 5px; min-width:10px; max-width:10px;"
            f" min-height:10px; max-height:10px;"
        )
        if text is not None:
            self._text.setText(text)


class SignalBars(QWidget):
    """Four-bar Wi-Fi signal indicator drawn with QPainter."""

    def __init__(self, percent: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent = percent
        self.setFixedSize(30, 20)

    def set_percent(self, percent: int) -> None:
        self._percent = max(0, min(100, percent))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bars = 4
        lit = 0 if self._percent <= 0 else max(1, round(self._percent / 100 * bars))
        color = (
            PALETTE.success if self._percent >= 70
            else PALETTE.accent2 if self._percent >= 45
            else PALETTE.warning if self._percent >= 20
            else PALETTE.critical
        )
        for i in range(bars):
            h = 5 + i * 4
            rect = QRectF(i * 7, 20 - h, 5, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color) if i < lit else QColor(PALETTE.border))
            p.drawRoundedRect(rect, 1.5, 1.5)
        p.end()


class StepIndicator(QWidget):
    """Horizontal step tracker for the guided wizards."""

    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._dots: list[QLabel] = []
        self._labels: list[QLabel] = []
        self._steps = steps
        for index, step in enumerate(steps):
            dot = QLabel(str(index + 1))
            dot.setObjectName("StepDot")
            dot.setAlignment(Qt.AlignCenter)
            dot.setFixedSize(26, 26)
            self._dots.append(dot)
            label = QLabel(step)
            label.setObjectName("Muted")
            self._labels.append(label)
            self._layout.addWidget(dot)
            self._layout.addWidget(label)
            if index < len(steps) - 1:
                line = QFrame()
                line.setObjectName("Divider")
                line.setFixedHeight(1)
                line.setMinimumWidth(18)
                self._layout.addWidget(line, 1)
        self._layout.addStretch(0)
        self.set_step(0)

    def set_step(self, index: int) -> None:
        for i, dot in enumerate(self._dots):
            dot.setProperty("active", "true" if i == index else "false")
            dot.setProperty("done", "true" if i < index else "false")
            dot.style().unpolish(dot)
            dot.style().polish(dot)
            self._labels[i].setStyleSheet(
                f"color: {PALETTE.accent if i == index else PALETTE.text_dim};"
            )


class Banner(QFrame):
    """Inline info / warning / error banner."""

    def __init__(self, text: str = "", kind: str = "info", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(10)
        self._icon = QLabel()
        self._text = QLabel(text)
        self._text.setWordWrap(True)
        self._layout.addWidget(self._icon, 0, Qt.AlignTop)
        self._layout.addWidget(self._text, 1)
        self.set_kind(kind)

    def set_kind(self, kind: str) -> None:
        colors = {
            "info": PALETTE.accent2,
            "success": PALETTE.success,
            "warning": PALETTE.warning,
            "error": PALETTE.critical,
        }
        icons = {
            "info": "dashboard",
            "success": "check",
            "warning": "warning",
            "error": "warning",
        }
        color = colors.get(kind, PALETTE.accent2)
        self._icon.setPixmap(_icon_pixmap(icons.get(kind, "dashboard"), 20, color))
        self.setStyleSheet(
            f"Banner {{ background: rgba(255,255,255,0.03); border: 1px solid {color};"
            f" border-radius: 10px; }}"
        )

    def set_text(self, text: str, kind: str | None = None) -> None:
        self._text.setText(text)
        if kind:
            self.set_kind(kind)


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def h_line_spacer(height: int = 8) -> QWidget:
    widget = QWidget()
    widget.setFixedHeight(height)
    return widget


def icon_label(name: str, size: int = 20, color: str | None = None) -> QLabel:
    label = QLabel()
    label.setPixmap(_icon_pixmap(name, size, color))
    label.setFixedSize(size, size)
    return label


def mono_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("Mono")
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def elide(text: str, length: int = 40) -> str:
    return text if len(text) <= length else text[: length - 1] + "…"


def button(text: str, kind: str = "default", icon: str = "", on_click: Callable | None = None) -> QPushButton:
    btn = QPushButton(text)
    if icon:
        btn.setIcon(make_icon(icon, PALETTE.accent if kind in ("default", "ghost") else "#08282B"))
    if kind == "primary":
        btn.setObjectName("Primary")
    elif kind == "secondary":
        btn.setObjectName("Secondary")
    elif kind == "danger":
        btn.setObjectName("Danger")
    elif kind == "ghost":
        btn.setObjectName("Ghost")
    btn.setCursor(Qt.PointingHandCursor)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def heading(text: str, subtitle: str = "") -> QWidget:
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    title = QLabel(text)
    title.setObjectName("PageTitle")
    layout.addWidget(title)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("PageSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return wrapper
