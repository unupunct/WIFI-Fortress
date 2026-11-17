"""Charts built on pyqtgraph, styled for the dark theme."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

try:
    import pyqtgraph as pg

    pg.setConfigOption("background", None)
    pg.setConfigOption("foreground", "#94AAB3")
    pg.setConfigOptions(antialias=True)
    HAVE_PYQTGRAPH = True
except Exception:  # pragma: no cover - optional dependency
    pg = None
    HAVE_PYQTGRAPH = False

from wififortress.ui.theme import PALETTE

BAND_COLORS = {
    "2.4 GHz": PALETTE.accent,
    "5 GHz": PALETTE.accent2,
    "6 GHz": "#9C7BFF",
}

SERIES_COLORS = [
    PALETTE.accent,
    PALETTE.accent2,
    "#9C7BFF",
    PALETTE.warning,
    PALETTE.success,
    PALETTE.critical,
]


class _Fallback(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setObjectName("Dim")


class BarChart(QWidget):
    """Grouped bar chart: one series per band, one bar per channel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if not HAVE_PYQTGRAPH:
            layout.addWidget(_Fallback("Chart unavailable: install pyqtgraph"))
            self._plot = None
            return
        self._plot = pg.PlotWidget()
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.showGrid(x=False, y=True, alpha=0.15)
        self._plot.getAxis("left").setLabel("APs")
        self._plot.getAxis("bottom").setLabel("Channel")
        self._legend = self._plot.addLegend(offset=(-10, 10), labelTextColor=PALETTE.text_muted)
        layout.addWidget(self._plot)
        self._items: list = []

    def set_series(self, series: list[tuple[str, dict[int, int]]]) -> None:
        if self._plot is None:
            return
        for item in self._items:
            self._plot.removeItem(item)
        self._items.clear()
        if self._legend is not None:
            self._legend.clear()
        if not series:
            return
        channels = sorted({ch for _, data in series for ch in data})
        positions = list(range(len(channels)))
        width = 0.8 / max(1, len(series))
        for index, (name, data) in enumerate(series):
            values = [data.get(ch, 0) for ch in channels]
            bar = pg.BarGraphItem(
                x=[p - 0.4 + width * index + width / 2 for p in positions],
                height=values,
                width=width * 0.92,
                brush=QColor(BAND_COLORS.get(name, SERIES_COLORS[index % len(SERIES_COLORS)])),
                pen=None,
                name=name,
            )
            self._plot.addItem(bar)
            self._items.append(bar)
        axis = self._plot.getAxis("bottom")
        axis.setTicks([[(i, str(ch)) for i, ch in enumerate(channels)]])
        self._plot.setYRange(0, max(1, max(data.get(ch, 0) for _, data in series for ch in channels)) + 1)


class DonutChart(QWidget):
    """Simple horizontal distribution bars (readable at small sizes)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._rows: list[QWidget] = []

    def set_values(self, values: dict[str, int]) -> None:
        for row in self._rows:
            row.deleteLater()
        self._rows.clear()
        if not values:
            empty = _Fallback("No data yet")
            self._layout.addWidget(empty)
            self._rows.append(empty)
            return
        total = max(1, sum(values.values()))
        ordered = sorted(values.items(), key=lambda kv: kv[1], reverse=True)
        for index, (name, count) in enumerate(ordered):
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            label = QLabel(f"{name} — {count} ({count * 100 // total}%)")
            label.setObjectName("Muted")
            row_layout.addWidget(label)
            bar = QWidget()
            bar.setFixedHeight(6)
            color = SERIES_COLORS[index % len(SERIES_COLORS)]
            if "Open" in name:
                color = PALETTE.critical
            elif "WEP" in name or name == "WPA":
                color = PALETTE.warning
            elif "WPA3" in name:
                color = PALETTE.success
            bar.setStyleSheet(
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                f" stop:0 {color}, stop:{count / total:.3f} {color},"
                f" stop:{min(1.0, count / total + 0.001):.3f} {PALETTE.border},"
                f" stop:1 {PALETTE.border}); border-radius: 3px;"
            )
            row_layout.addWidget(bar)
            self._layout.addWidget(row)
            self._rows.append(row)


class SignalHistoryChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if not HAVE_PYQTGRAPH:
            layout.addWidget(_Fallback("Chart unavailable: install pyqtgraph"))
            self._plot = None
            return
        self._plot = pg.PlotWidget()
        self._plot.setMenuEnabled(False)
        self._plot.hideButtons()
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.showGrid(x=False, y=True, alpha=0.15)
        self._plot.getAxis("left").setLabel("dBm")
        self._plot.setYRange(-95, -25)
        layout.addWidget(self._plot)
        self._curve = self._plot.plot(pen=pg.mkPen(PALETTE.accent, width=2))

    def set_series(self, values: list[float]) -> None:
        if self._plot is None:
            return
        if not values:
            self._curve.setData([])
            return
        self._curve.setData(list(range(len(values))), values)
