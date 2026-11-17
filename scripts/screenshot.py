"""Render each page of the running application to a PNG (documentation/screenshots).

Usage:  python scripts/screenshot.py [output_dir]
Requires a display; on a headless machine use ``xvfb-run``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# A real platform plugin is required for text rendering; on a headless
# machine run this script through xvfb-run instead.

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from wififortress.app.context import build_context  # noqa: E402
from wififortress.ui.main_window import MainWindow  # noqa: E402
from wififortress.ui.theme import stylesheet  # noqa: E402
from wififortress.widgets.common import app_icon  # noqa: E402

PAGES = [
    "dashboard", "networks", "recovery", "audit", "tools",
    "adapters", "password", "dictionaries", "diagnostics", "reports", "settings",
]


def pump(ms: int = 250) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "screenshots"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("WiFi Fortress")
    app.setWindowIcon(app_icon())
    app.setStyleSheet(stylesheet())
    context = build_context()
    window = MainWindow(context)
    window.resize(1500, 950)
    window.show()
    pump(600)
    for key in PAGES:
        window.navigate(key)
        pump(350)
        path = out / f"{PAGES.index(key) + 1:02d}-{key}.png"
        window.grab().save(str(path))
        print(f"wrote {path}")
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
