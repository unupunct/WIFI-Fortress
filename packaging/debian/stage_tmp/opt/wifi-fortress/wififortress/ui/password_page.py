"""Password Laboratory: local assessment and secure generation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from wififortress.app.context import AppContext
from wififortress.ui.theme import PALETTE
from wififortress.widgets.common import Banner, Card, Pill, button, divider, heading, mono_label


class PasswordPage(QWidget):
    def __init__(self, context: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.context = context
        self._generated = ""

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
        layout.setSpacing(16)

        layout.addWidget(heading(
            "Password Laboratory",
            "Assess and generate passwords locally. Nothing you type here is logged, "
            "stored or sent anywhere.",
        ))

        columns = QHBoxLayout()
        columns.setSpacing(16)

        # --- assessment ---------------------------------------------------
        left = QVBoxLayout()
        left.setSpacing(12)
        self.assess_card = Card("Assess a password", "Analysis happens in memory only.")
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("Type or paste a password…")
        self.input.textChanged.connect(self._assess)
        self.show_btn = button("Show", "ghost", "eye", self._toggle_input)
        row.addWidget(self.input, 1)
        row.addWidget(self.show_btn)
        self.assess_card.add_layout(row)
        self.score_label = QLabel("—")
        self.score_label.setObjectName("StatValue")
        self.score_label.setStyleSheet("font-size: 40px;")
        self.assess_card.add(self.score_label)
        self.summary_label = QLabel("Enter a password to analyse it.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("Muted")
        self.assess_card.add(self.summary_label)
        self.composition = QGridLayout()
        self.assess_card.add_layout(self.composition)
        self.assess_card.add(divider())
        self.weak_label = QLabel("")
        self.weak_label.setWordWrap(True)
        self.assess_card.add(self.weak_label)
        self.rec_label = QLabel("")
        self.rec_label.setWordWrap(True)
        self.assess_card.add(self.rec_label)
        left.addWidget(self.assess_card)

        self.privacy_card = Card("Privacy", "")
        privacy = QLabel(
            "• The password stays in this process's memory.\n"
            "• It is never written to a log, a report, the database or the clipboard "
            "unless you press Copy.\n"
            "• Dictionary comparison runs against files on this computer."
        )
        privacy.setWordWrap(True)
        privacy.setObjectName("Muted")
        self.privacy_card.add(privacy)
        left.addWidget(self.privacy_card)
        left.addStretch(1)
        columns.addLayout(left, 1)

        # --- generation ---------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(12)
        self.gen_card = Card("Generate a password", "Uses Python's secrets module (CSPRNG).")
        self.gen_output = mono_label("")
        self.gen_output.setStyleSheet(
            f"background: {PALETTE.secondary}; border: 1px solid {PALETTE.border};"
            f" border-radius: 8px; padding: 12px; font-size: 14px;"
        )
        self.gen_output.setWordWrap(True)
        self.gen_card.add(self.gen_output)

        gen_row = QHBoxLayout()
        gen_row.addWidget(button("Generate", "primary", "refresh", self._generate))
        gen_row.addWidget(button("Copy", "secondary", "copy", self._copy_generated))
        self.reveal_gen = button("Hide", "ghost", "eye", self._toggle_generated)
        gen_row.addWidget(self.reveal_gen)
        gen_row.addStretch(1)
        self.gen_card.add_layout(gen_row)

        length_row = QHBoxLayout()
        length_row.addWidget(QLabel("Length"))
        self.length_slider = QSlider(Qt.Horizontal)
        self.length_slider.setRange(16, 40)
        self.length_slider.setValue(int(self.context.settings.get("password_min_length", 20)))
        self.length_value = QLabel(str(self.length_slider.value()))
        self.length_slider.valueChanged.connect(lambda v: self.length_value.setText(str(v)))
        length_row.addWidget(self.length_slider, 1)
        length_row.addWidget(self.length_value)
        self.gen_card.add_layout(length_row)

        checks = QGridLayout()
        self.cb_upper = QCheckBox("Uppercase")
        self.cb_lower = QCheckBox("Lowercase")
        self.cb_digits = QCheckBox("Numbers")
        self.cb_symbols = QCheckBox("Symbols")
        self.cb_ambiguous = QCheckBox("Exclude ambiguous characters")
        for checkbox, key, default in (
            (self.cb_upper, "password_use_upper", True),
            (self.cb_lower, "password_use_lower", True),
            (self.cb_digits, "password_use_digits", True),
            (self.cb_symbols, "password_use_symbols", True),
            (self.cb_ambiguous, "password_exclude_ambiguous", True),
        ):
            checkbox.setChecked(bool(self.context.settings.get(key, default)))
        checks.addWidget(self.cb_upper, 0, 0)
        checks.addWidget(self.cb_lower, 0, 1)
        checks.addWidget(self.cb_digits, 0, 2)
        checks.addWidget(self.cb_symbols, 1, 0)
        checks.addWidget(self.cb_ambiguous, 1, 1, 1, 2)
        self.gen_card.add_layout(checks)
        right.addWidget(self.gen_card)

        self.phrase_card = Card("Memorable passphrase", "Random words joined by a separator.")
        phrase_row = QHBoxLayout()
        phrase_row.addWidget(QLabel("Words"))
        self.word_count = QSpinBox()
        self.word_count.setRange(3, 10)
        self.word_count.setValue(int(self.context.settings.get("passphrase_words", 5)))
        phrase_row.addWidget(self.word_count)
        phrase_row.addWidget(QLabel("Separator"))
        self.separator = QComboBox()
        self.separator.addItems(["-", "_", ".", " ", "+"])
        phrase_row.addWidget(self.separator)
        phrase_row.addWidget(button("Generate passphrase", "secondary", "", self._generate_phrase))
        phrase_row.addStretch(1)
        self.phrase_card.add_layout(phrase_row)
        self.phrase_note = QLabel("")
        self.phrase_note.setObjectName("Muted")
        self.phrase_note.setWordWrap(True)
        self.phrase_card.add(self.phrase_note)
        right.addWidget(self.phrase_card)

        self.gen_assess = Card("Assessment of the generated value", "")
        self.gen_assess_label = QLabel("Nothing generated yet.")
        self.gen_assess_label.setWordWrap(True)
        self.gen_assess_label.setObjectName("Muted")
        self.gen_assess.add(self.gen_assess_label)
        self.notice = Banner(
            "A generated password is only a suggestion. WiFi Fortress never applies it to "
            "your router; you must set it in the router's own administration page.",
            "info",
        )
        self.gen_assess.add(self.notice)
        right.addWidget(self.gen_assess)
        right.addStretch(1)
        columns.addLayout(right, 1)
        layout.addLayout(columns)
        layout.addStretch(1)

    # -- assessment -----------------------------------------------------
    def _toggle_input(self) -> None:
        if self.input.echoMode() == QLineEdit.Password:
            self.input.setEchoMode(QLineEdit.Normal)
            self.show_btn.setText("Hide")
        else:
            self.input.setEchoMode(QLineEdit.Password)
            self.show_btn.setText("Show")

    def _assess(self, text: str) -> None:
        if not text:
            self.score_label.setText("—")
            self.score_label.setStyleSheet("font-size: 40px;")
            self.summary_label.setText("Enter a password to analyse it.")
            self.weak_label.setText("")
            self.rec_label.setText("")
            return
        result = self.context.password.assess(text)
        color = (
            PALETTE.success if result.score >= 70
            else PALETTE.warning if result.score >= 45
            else PALETTE.critical
        )
        self.score_label.setText(f"{result.score}")
        self.score_label.setStyleSheet(f"font-size: 40px; color: {color};")
        self.summary_label.setText(
            f"<b>{result.strength}</b> · {result.category}<br>"
            f"Estimated resistance: {result.crack_time_estimate}<br>"
            f"Character-pool entropy: {result.entropy_bits:.0f} bits (upper bound)"
        )
        while self.composition.count():
            item = self.composition.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        comp = result.composition
        for index, (key, value) in enumerate(comp.items()):
            label = QLabel(f"{key.replace('_', ' ').title()}: {value}")
            label.setObjectName("Muted")
            self.composition.addWidget(label, index // 3, index % 3)
        weak = result.weaknesses + result.patterns + result.dictionary_hits
        self.weak_label.setText(
            "<b>Weaknesses</b><br>" + ("<br>".join(f"• {w}" for w in weak) if weak else "None found.")
        )
        self.rec_label.setText(
            "<b>Recommendations</b><br>"
            + "<br>".join(f"• {r}" for r in result.recommendations)
        )

    # -- generation -----------------------------------------------------
    def _generate(self) -> None:
        try:
            value = self.context.generator.generate(
                self.length_slider.value(),
                use_upper=self.cb_upper.isChecked(),
                use_lower=self.cb_lower.isChecked(),
                use_digits=self.cb_digits.isChecked(),
                use_symbols=self.cb_symbols.isChecked(),
                exclude_ambiguous=self.cb_ambiguous.isChecked(),
            )
        except ValueError as exc:
            self.gen_output.setText(str(exc))
            return
        self._generated = value
        self.gen_output.setText(value)
        self._describe_generated(value)

    def _generate_phrase(self) -> None:
        try:
            value = self.context.generator.generate_passphrase(
                self.word_count.value(), self.separator.currentText()
            )
        except ValueError as exc:
            self.phrase_note.setText(str(exc))
            return
        self._generated = value
        self.gen_output.setText(value)
        self.phrase_note.setText(
            f"{self.word_count.value()} words chosen uniformly at random from "
            f"{'the enabled dictionaries' if self.context.generator.has_word_source else 'no word source'}."
        )
        self._describe_generated(value)

    def _describe_generated(self, value: str) -> None:
        result = self.context.password.assess(value)
        lines = self.context.generator.describe(value)
        lines.append(f"Local assessment: {result.score}/100 ({result.strength})")
        self.gen_assess_label.setText("<br>".join(lines))
        self.reveal_gen.setText("Hide")
        self.gen_output.setVisible(True)

    def _toggle_generated(self) -> None:
        if not self._generated:
            return
        if self.reveal_gen.text() == "Hide":
            self.gen_output.setText("•" * len(self._generated))
            self.reveal_gen.setText("Show")
        else:
            self.gen_output.setText(self._generated)
            self.reveal_gen.setText("Hide")

    def _copy_generated(self) -> None:
        if self._generated:
            QGuiApplication.clipboard().setText(self._generated)
            self.notice.set_text(
                "Copied to the clipboard. Set it in your router's administration page "
                "yourself; WiFi Fortress does not apply it.", "info",
            )
