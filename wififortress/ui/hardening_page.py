"""Passphrase hardening: how a Wi-Fi passphrase would fare against an attack.

This page does not attack anything.  It takes the passphrase you set on your
own router and models how much work an offline attack on a captured handshake
would need, then tells you what to change.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.ui.theme import PALETTE
from wififortress.widgets.common import Banner, Card, Pill, button, heading

RATE_LABELS = {
    "cpu": "One desktop CPU core",
    "gpu_entry": "Entry-level GPU",
    "gpu_mid": "Mid-range GPU",
    "gpu_flagship": "Flagship GPU",
    "rig_8_gpu": "8-GPU cracking rig",
}

VERDICT_COLORS = {
    "Weak": PALETTE.critical,
    "Moderate": PALETTE.warning,
    "Strong": PALETTE.success,
    "Very strong": PALETTE.accent,
}


class HardeningPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)

        layout.addWidget(heading(
            "Passphrase Hardening",
            "Would my Wi-Fi passphrase survive an attacker who already captured a "
            "handshake? Model it here — nothing is attacked, nothing leaves this machine.",
        ))

        self.banner = Banner(
            "Type the passphrase you set on your own router. It stays in memory and is "
            "never logged, stored or sent anywhere.",
            "info",
        )
        layout.addWidget(self.banner)

        input_card = Card("Your Wi-Fi passphrase", "WPA2-PSK accepts 8 to 63 characters.")
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("Passphrase set on the router")
        self.input.returnPressed.connect(self._analyse)
        row.addWidget(self.input, 1)
        self.show_btn = button("Show", "ghost", "eye", self._toggle)
        row.addWidget(self.show_btn)
        row.addWidget(button("Model the attack", "primary", "shield", self._analyse))
        input_card.add_layout(row)
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {PALETTE.critical};")
        self.error_label.setWordWrap(True)
        input_card.add(self.error_label)
        layout.addWidget(input_card)

        self.headline_card = Card("Verdict", "")
        self.headline_pill_row = QHBoxLayout()
        self.verdict_pill = Pill("Not analysed", PALETTE.text_muted)
        self.headline_pill_row.addWidget(self.verdict_pill)
        self.weakest_label = QLabel("—")
        self.weakest_label.setObjectName("Muted")
        self.headline_pill_row.addWidget(self.weakest_label, 1)
        self.headline_card.add_layout(self.headline_pill_row)
        self.detail_label = QLabel("Enter your passphrase above to see the verdict.")
        self.detail_label.setWordWrap(True)
        self.headline_card.add(self.detail_label)
        layout.addWidget(self.headline_card)

        self.grid_card = Card(
            "How long the attacker needs",
            "Assumes the attacker already holds a handshake for your network. "
            "Published rates, not a promise — hardware and luck vary.",
        )
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(8)
        self.grid_card.add_layout(self.grid)
        self.rate_labels: dict[str, QLabel] = {}
        for row_index, key in enumerate(RATE_LABELS):
            name = QLabel(RATE_LABELS[key])
            name.setObjectName("Muted")
            value = QLabel("—")
            value.setObjectName("Mono")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.grid.addWidget(name, row_index, 0)
            self.grid.addWidget(value, row_index, 1)
            self.rate_labels[key] = value
        layout.addWidget(self.grid_card)

        self.wpa3_card = Card(
            "If you use WPA3",
            "WPA3-SAE is attacked per connection, not per guess, so the same "
            "passphrase is dramatically more expensive to attack.",
        )
        self.wpa3_label = QLabel("—")
        self.wpa3_label.setObjectName("Muted")
        self.wpa3_label.setWordWrap(True)
        self.wpa3_card.add(self.wpa3_label)
        layout.addWidget(self.wpa3_card)

        self.actions_card = Card("What to change", "")
        self.actions_label = QLabel("—")
        self.actions_label.setObjectName("Muted")
        self.actions_label.setWordWrap(True)
        self.actions_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.actions_card.add(self.actions_label)
        layout.addWidget(self.actions_card)

        layout.addStretch(1)

    # -- actions ---------------------------------------------------------
    def _toggle(self) -> None:
        hidden = self.input.echoMode() == QLineEdit.Password
        self.input.setEchoMode(QLineEdit.Normal if hidden else QLineEdit.Password)
        self.show_btn.setText("Hide" if hidden else "Show")

    def _analyse(self) -> None:
        value = self.input.text()
        self.error_label.setText("")
        if not value:
            self.error_label.setText("Enter the passphrase first.")
            return
        if len(value) < 8 or len(value) > 63:
            self.error_label.setText(
                f"WPA2-PSK passphrases are 8 to 63 characters; this one is {len(value)}."
            )
        try:
            result = self.context.password.attack_resistance(value)
        except ValueError as exc:
            self.error_label.setText(str(exc))
            return

        colour = VERDICT_COLORS.get(result.verdict, PALETTE.text_muted)
        self.verdict_pill.set_status(result.verdict, colour)
        self.weakest_label.setText(f"Weakest link: {result.weakest_link}")
        self.detail_label.setText(
            f"{result.verdict_detail} Effective guessing resistance: "
            f"{result.keyspace_bits:.0f} bits of keyspace, {result.entropy_bits:.0f} bits "
            f"after accounting for structure."
        )
        for key, label in self.rate_labels.items():
            label.setText(result.estimates.get(key, "—"))
        sae = result.seconds_to_crack
        self.wpa3_label.setText(
            "Attacking one WPA3-SA handshake on a mid-range GPU would need "
            f"{self._format_sae(result)} of continuous work — WPA3 also refuses the "
            "offline replay that makes WPA2 so cheap to attack."
            if True else ""
        )
        self.actions_label.setText(
            "\n".join(f"• {item}" for item in result.recommendations)
        )
        self.context.record_operation(
            "hardening",
            f"Passphrase resistance modelled ({result.verdict})",
            "ok",
            result.weakest_link,
        )

    @staticmethod
    def _format_sae(result) -> str:
        from wififortress.services.password_service import _human_duration

        rate = 900  # SAE per-connection attempts per second on a tuned GPU
        guesses = 2 ** max(result.entropy_bits, 0.0)
        return _human_duration(guesses / rate)
