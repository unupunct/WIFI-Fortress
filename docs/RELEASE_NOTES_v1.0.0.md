## WiFi Fortress 1.0.0

The first release of WiFi Fortress: a defensive wireless-security suite for
Parrot OS that replaces a pile of terminal one-liners with one desktop
application.

### What's in it

- **Adapter Manager** — interface state, driver, chipset, PHY capabilities,
  supported bands, monitor-mode support, rfkill and link control.
- **Wireless Networks** — `iw`-based scanning with a `nmcli` fallback;
  WPA2/WPA3/OWE/WEP/Open/Enterprise classified strictly from the RSN and WPA
  information elements, channel congestion and signal history.
- **Wi-Fi Recovery** — a guided 5-step process that reads a credential your
  user account **already has saved** (NetworkManager profiles and keyfiles),
  plus documented router-reset and router-admin routes. System-wide profiles
  are only touched with explicit authorisation.
- **Security Audit** — a documented 0–100 score with evidence, explanation,
  impact and recommendation per finding, a prioritised checklist and
  before/after comparison. Information that cannot be determined is reported
  as *Unknown — not determinable* and is never scored.
- **Wireless Tools** — detects installed Parrot tooling and versions for
  inventory; it does not run capture, deauthentication or cracking workflows.
- **Password Laboratory** — local-only strength assessment and CSPRNG
  generation, including passphrases built from the bundled word lists.
- **Dictionary Manager** — ten bundled lists with verified checksums and
  provenance, plus import, verify, enable and reorder for your own lists.
- **Diagnostics** — interface, addressing, gateway, DNS, reachability,
  latency and packet loss, each with a suggested fix.
- **Reports** — PDF, HTML and JSON, with every field passed through a secret
  redactor. Reports never contain passwords.
- **Quick and Advanced modes**, so the technical detail is there when you want
  it and out of the way when you don't.

### Safety properties

- Passwords are never written to logs, the database, reports or shell history;
  all tool output is validated and redacted.
- Commands run as argument lists — never through a shell — after interface
  names, MAC addresses and host targets are validated.
- The GUI never runs as root; privileged operations are elevated individually
  with `pkexec`/`sudo`.
- No handshake capture, no deauthentication, no WPS brute force, no cracking.

### Install

See [docs/INSTALL.md](docs/INSTALL.md). In short:

```bash
sudo apt install python3-pyside6.qtwidgets python3-reportlab \
                 iw network-manager rfkill ethtool pciutils usbutils
sudo dpkg -i wifi-fortress_1.0.0_all.deb
wifi-fortress --selftest
wifi-fortress
```

A source install (`sudo ./packaging/debian/install.sh`) and a no-install
virtualenv route are documented as well.

### Notes

- Requires Python 3.12+ and PySide6 6.6+ (Parrot OS / Debian 12+).
- The application starts on Windows for development, but adapter discovery,
  scanning, recovery and diagnostics are Linux-only and say so plainly instead
  of showing invented data.
- 154 automated tests cover parsing and classification, audit scoring,
  recovery, redaction, dictionary integrity, reports, process safety and core
  services.

### Dictionaries

All ten bundled word lists were authored for this project and are released
CC0-1.0. No third-party word list, corpus or leaked password dump is included.
