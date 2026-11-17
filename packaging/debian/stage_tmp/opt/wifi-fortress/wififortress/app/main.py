"""WiFi Fortress application entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from wififortress import APP_NAME, APP_VERSION
from wififortress.core.logging import get_logger, setup_logging
from wififortress.core.paths import log_dir
from wififortress.core.privileges import is_root
from wififortress.ui.main_window import MainWindow
from wififortress.ui.theme import stylesheet
from wififortress.widgets.common import app_icon

log = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wifi-fortress", description=f"{APP_NAME} {APP_VERSION}"
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--allow-root",
        action="store_true",
        help="Start the GUI as root (not recommended; elevation is per-operation)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run headless service checks and exit (used by the installer)",
    )
    return parser


def run_selftest() -> int:
    """Headless verification of the non-GUI layers."""
    from wififortress.app.context import build_context

    setup_logging(logging.INFO)
    try:
        context = build_context()
        dictionaries = context.dictionaries.all()
        word_count = sum(len(context.dictionaries.preview(i.dict_id, 500000)) for i in dictionaries)
        assess = context.password.assess("Parola123!")
        generated = context.generator.generate(24)
        adapters = context.adapters.discover()
        print(f"{APP_NAME} {APP_VERSION} self-test")
        from wififortress.core.paths import data_dir

        print(f"  data directory      : {data_dir()}")
        print(f"  dictionaries        : {len(dictionaries)} files, {word_count} entries readable")
        print(f"  password assessment : score {assess.score}/100 ({assess.strength})")
        print(f"  password generation : {len(generated)} characters")
        print(f"  adapters detected   : {len(adapters.adapters)}")
        print(f"  tools available     : {sum(1 for t in context.tools.discover_all() if t.installed)}")
        print("  result              : OK")
        return 0
    except Exception as exc:  # pragma: no cover - installer path
        print(f"self-test failed: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_file = setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    if args.selftest:
        return run_selftest()

    if is_root() and not args.allow_root:
        message = (
            "WiFi Fortress is running as root.\n\n"
            "The graphical application must run as your normal user account; it asks "
            "for elevation only for individual operations. Please start it again "
            "without sudo."
        )
        print(message, file=sys.stderr)
        app = QApplication.instance() or QApplication(sys.argv[:1])
        QMessageBox.critical(None, f"{APP_NAME} - not started as root", message)
        return 2

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("WiFi Fortress Project")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(stylesheet())

    from wififortress.app.context import build_context

    log.info("Starting %s %s (log: %s)", APP_NAME, APP_VERSION, log_file)
    try:
        context = build_context()
    except Exception as exc:  # pragma: no cover - startup failure
        log.error("Startup failed: %s", exc)
        QMessageBox.critical(
            None,
            f"{APP_NAME} could not start",
            f"Startup failed:\n\n{exc}\n\nSee the log file in {log_dir()}",
        )
        return 1

    window = MainWindow(context)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
