# WiFi Fortress 1.1.0

Two new capabilities, both aimed at hardening a network you own.

## Passphrase Hardening (new page)

The question "is my Wi-Fi password actually crackable?" no longer needs a
captured handshake. Enter the passphrase you set on your router and the page
models the offline attack an adversary would have to run:

- Time to recover on a CPU core, an entry-level GPU, a mid-range GPU, a
  flagship GPU and an 8-GPU rig, from published PBKDF2 rate figures.
- The **weakest link** named: dictionary word, keyboard walk, repeated
  characters, short length, or none found.
- The same passphrase against **WPA3-SAE**, where every guess must be replayed
  live against the network instead of offline.
- A concrete list of changes, and the verdict feeds the Security Audit so the
  network score reflects real attack resistance, not only the cipher suite.

Pure arithmetic over the bundled dictionaries. Nothing is transmitted, logged
or stored, and no cracking is performed.

## Public word lists (Dictionary Manager)

A catalogue of **49 public word lists**, every link verified to exist when it
was added:

- 24 are single text files, downloadable in one click, with **Download** or
  **Download + import** straight into the dictionary set.
- 25 are reference pages (rockyou, weakpass, CrackStation, haveibeenpwned,
  Hob0Rules, full repositories) that open in the browser.
- Filter by category or **Wi-Fi focused only** — 8 lists are WPA-specific,
  including SecLists *probable WPA top 4800*, Probable-Wordlists *WPA 204k* and
  the wifite/fern-wifi lists Parrot ships.

Downloads are streamed with a size cap, gzipped archives are unpacked, binary
files are rejected, and each import keeps its upstream licence, source URL and
SHA-256. Nothing is fetched until you ask, and no list is bundled.

## Under the hood

- Additive database migration: an upgrade keeps existing dictionaries, now with
  provenance, description and purpose persisted.
- `.pyc` files are no longer tracked.
- Windows packaging committed (PyInstaller spec, Inno Setup script, icon,
  version info, licence).
- `packaging/debian/mkdeb_fallback.py`: builds the `.deb` on a host without
  `dpkg-deb`, in Debian's own ar + zstd format with correct ownership and modes.
- 176 tests passing (22 new).
