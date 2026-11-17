#!/usr/bin/env python3
"""Convenience launcher: ``python run.py``."""

import sys

from wififortress.app.main import main

if __name__ == "__main__":
    sys.exit(main())
