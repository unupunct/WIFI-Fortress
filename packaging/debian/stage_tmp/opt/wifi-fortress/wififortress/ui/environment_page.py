"""Wireless Environment Analyzer: charts and channel suggestions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.services.audit_service import neighbour_statistics
from wififortress.services.discovery_service import WirelessDiscoveryService
from wififortress.ui.theme import PALETTE
from wififortress.widgets.charts import BarChart, DonutChart
from wififortress.widgets.common import Banner, Card, Pill, button, divider, heading

# Non-overlapping 2.4 GHz channels and their width in MHz.
CHANNEL_WIDTH_24 = {1: 4, 2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 4, 11: 4, 12: 4, 13: 4}
CLEAN_24 = [1, 6, 11]


class EnvironmentPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(heading(
            "Wireless Environment",
            "Channel usage, band distribution and congestion from the latest scan.",
        ), 1)
        header.addWidget(button("Refresh", "secondary", "refresh", self.refresh), 0, Qt.AlignTop)
        layout.addLayout(header)

        self.banner = Banner(
            "Channel observations come from beacon information elements in a Wi-Fi scan. "
            "This is not RF spectrum analysis: it does not show interference from "
            "non-Wi-Fi sources or noise floors.", "warning",
        )
        layout.addWidget(self.banner)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.channel_card = Card("Channel distribution", "Access points per channel, by band.")
        self.channel_chart = BarChart()
        self.channel_chart.setMinimumHeight(220)
        self.channel_card.add(self.channel_chart)
        grid.addWidget(self.channel_card, 0, 0, 1, 2)

        self.security_card = Card("Security distribution", "")
        self.security_chart = DonutChart()
        self.security_card.add(self.security_chart)
        grid.addWidget(self.security_card, 1, 0)

        self.bands_card = Card("Band distribution", "")
        self.bands_label = QLabel("No scan data.")
        self.bands_label.setWordWrap(True)
        self.bands_label.setObjectName("Muted")
        self.bands_card.add(self.bands_label)
        grid.addWidget(self.bands_card, 1, 1)

        self.congestion_card = Card("Congested channels", "Ranked by number of access points.")
        self.congestion_label = QLabel("No scan data.")
        self.congestion_label.setWordWrap(True)
        self.congestion_label.setObjectName("Muted")
        self.congestion_card.add(self.congestion_label)
        grid.addWidget(self.congestion_card, 2, 0)

        self.dupes_card = Card("Duplicate SSIDs", "Same name, different BSSID - check for look-alikes.")
        self.dupes_label = QLabel("No scan data.")
        self.dupes_label.setWordWrap(True)
        self.dupes_label.setObjectName("Muted")
        self.dupes_card.add(self.dupes_label)
        grid.addWidget(self.dupes_card, 2, 1)

        self.suggest_card = Card("Suggested channel improvements", "")
        self.suggest_label = QLabel("No scan data.")
        self.suggest_label.setWordWrap(True)
        self.suggest_label.setObjectName("Muted")
        self.suggest_card.add(self.suggest_label)
        grid.addWidget(self.suggest_card, 3, 0, 1, 2)
        layout.addLayout(grid, 1)

    def refresh(self) -> None:
        networks = self.context.networks
        if not networks:
            self.banner.set_text(
                "No scan data yet. Run a scan in Wireless Networks first.", "warning"
            )
            return
        distribution = WirelessDiscoveryService.channel_distribution(networks)
        series = [
            (band, distribution[band])
            for band in ("2.4 GHz", "5 GHz", "6 GHz")
            if distribution.get(band)
        ]
        self.channel_chart.set_series(series)
        self.security_chart.set_values(WirelessDiscoveryService.security_distribution(networks))

        bands: dict[str, int] = {}
        for network in networks:
            bands[network.band.value] = bands.get(network.band.value, 0) + 1
        self.bands_label.setText(
            "<br>".join(f"{band}: {count}" for band, count in sorted(bands.items()))
        )

        counts: dict[str, int] = {}
        for network in networks:
            if network.channel is None:
                continue
            key = f"{network.band.value} ch {network.channel}"
            counts[key] = counts.get(key, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
        self.congestion_label.setText(
            "<br>".join(f"{key}: {value} APs" for key, value in ranked)
        )

        stats = neighbour_statistics(networks)
        dupes = stats["duplicate_ssids"]
        self.dupes_label.setText(
            ", ".join(dupes) if dupes else "No duplicate SSIDs observed."
        )

        suggestions: list[str] = []
        channels_24 = distribution.get("2.4 GHz", {})
        if channels_24:
            free = [ch for ch in CLEAN_24 if channels_24.get(ch, 0) == 0]
            if free:
                suggestions.append(
                    f"On 2.4 GHz, channel(s) {', '.join(map(str, free))} are unused and do "
                    "not overlap the other clean channels."
                )
            else:
                best = min(CLEAN_24, key=lambda ch: channels_24.get(ch, 0))
                suggestions.append(
                    f"All of 1/6/11 are in use; channel {best} has the fewest access points "
                    f"({channels_24.get(best, 0)})."
                )
        if distribution.get("5 GHz"):
            suggestions.append(
                "5 GHz channels are wide and mostly independent; prefer them for "
                "throughput and leave 2.4 GHz for legacy and IoT devices."
            )
        else:
            suggestions.append(
                "No 5 GHz networks were observed. If the adapter and router support it, "
                "enable a 5 GHz SSID to reduce congestion."
            )
        weak = [n for n in networks if (n.signal_dbm or 0) < -80]
        if weak:
            suggestions.append(
                f"{len(weak)} network(s) are below -80 dBm, which usually indicates distant "
                "or heavily obstructed access points."
            )
        self.suggest_label.setText("<br>".join(f"• {s}" for s in suggestions))
        self.banner.set_text(
            f"{len(networks)} networks analysed from the latest scan.", "info"
        )
