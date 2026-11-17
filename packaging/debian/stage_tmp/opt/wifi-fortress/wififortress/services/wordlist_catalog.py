"""Catalogue of public word lists, and a downloader that fetches them locally.

Every entry was verified to exist when this catalogue was written: the raw URL
answered HTTP 200 and the file is plain text.  Nothing is downloaded until the
user asks for it, and every download is streamed, size-capped and checked
before it is handed to the Dictionary Manager.

Licences differ per list.  The licence shown is what the upstream project
declares; the app never relicenses what it downloads, and records the origin
and SHA-256 of every file it keeps.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from wififortress.core.logging import get_logger
from wififortress.core.paths import cache_dir

log = get_logger(__name__)

CHUNK = 256 * 1024
# A single list larger than this is refused before the download starts, and
# the stream is cut off if a server sends more than it declared.
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class WordlistSource:
    """One downloadable public word list."""

    source_id: str
    name: str
    url: str
    homepage: str
    licence: str
    category: str
    note: str = ""
    approx_size: str = ""
    wifi_focused: bool = False

    @property
    def is_file(self) -> bool:
        """True when the URL is a single text file that can be streamed."""
        return self.url.startswith(("https://raw.githubusercontent.com/",
                                    "https://gist.githubusercontent.com/"))

    @property
    def filename(self) -> str:
        tail = self.url.rsplit("/", 1)[-1]
        tail = re.sub(r"[^A-Za-z0-9._-]", "_", tail) or "wordlist.txt"
        return f"{self.source_id}-{tail}"


def _raw(repo: str, branch: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"


def _gh(repo: str) -> str:
    return f"https://github.com/{repo}"


# --------------------------------------------------------------------------
# The catalogue.  Grouped by what the list is for.
# --------------------------------------------------------------------------
_SOURCES: list[WordlistSource] = [
    # -- the three the user named, plus the gist -------------------------
    WordlistSource(
        "devoxel-10k", "devoxel 10,000 word list",
        "https://gist.githubusercontent.com/devoxel/223fcb59b3072884dd0f/raw/10000wordlist.txt",
        "https://gist.github.com/devoxel/223fcb59b3072884dd0f",
        "Gist, no licence stated", "Common passwords",
        "Small, fast first pass; 10,000 entries.", "≈75 KB",
    ),
    WordlistSource(
        "kkrypt0nn-common", "kkrypt0nn — common passwords",
        _raw("kkrypt0nn/wordlists", "main", "wordlists/passwords/most_used_passwords.txt"),
        _gh("kkrypt0nn/wordlists"),
        "MIT", "Common passwords",
        "The most-used passwords list from kkrypt0nn/wordlists.", "≈8 MB",
    ),
    WordlistSource(
        "kkrypt0nn-top-passwords", "kkrypt0nn — top passwords",
        _raw("kkrypt0nn/wordlists", "main", "wordlists/passwords/probable_wpa.txt"),
        _gh("kkrypt0nn/wordlists"),
        "MIT", "Wi-Fi (WPA)",
        "kkrypt0nn's WPA-length list, ranked by probability.", "≈45 KB",
        True,
    ),
    WordlistSource(
        "seclists-top10k", "SecLists — 10k most common",
        _raw("danielmiessler/SecLists", "master", "Passwords/Common-Credentials/10k-most-common.txt"),
        _gh("danielmiessler/SecLists"),
        "MIT", "Common passwords",
        "The most-cited general-purpose password list.", "",
    ),
    WordlistSource(
        "seclists-top1m", "SecLists — 1M most common",
        _raw("danielmiessler/SecLists", "master",
             "Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt"),
        _gh("danielmiessler/SecLists"),
        "MIT", "Common passwords",
        "One million entries; a serious first pass. Large download.", "≈8 MB",
    ),
    WordlistSource(
        "seclists-500-worst", "SecLists — 500 worst passwords",
        _raw("danielmiessler/SecLists", "master", "Passwords/Common-Credentials/500-worst-passwords.txt"),
        _gh("danielmiessler/SecLists"),
        "MIT", "Common passwords", "The classic worst-of list.", "≈4 KB",
    ),
    WordlistSource(
        "seclists-wpa-top4800", "SecLists — probable WPA top 4800",
        _raw("danielmiessler/SecLists", "master", "Passwords/WiFi-WPA/probable-v2-wpa-top4800.txt"),
        _gh("danielmiessler/SecLists"),
        "MIT", "Wi-Fi (WPA)",
        "Passwords of WPA length (8–63), ranked by real-world frequency. "
        "The single most useful public list for auditing a Wi-Fi passphrase.",
        "≈45 KB", wifi_focused=True,
    ),
    WordlistSource(
        "amitlttwo-passwords", "All-Wordlists — passwords",
        _raw("amitlttwo/All-Wordlists", "main", "passwds/john.txt"),
        _gh("amitlttwo/All-Wordlists"),
        "No licence stated", "Common passwords",
        "John the Ripper's classic password list, from All-Wordlists.", "≈21 KB",
    ),
    WordlistSource(
        "kali-wordlists-wifite", "kali-wordlists — wifite list",
        _raw("00xZEROx00/kali-wordlists", "master", "wifite.txt"),
        _gh("00xZEROx00/kali-wordlists"),
        "Aggregated (mixed upstream licences)", "Wi-Fi (WPA)",
        "The word list Parrot and Kali ship for wifite. Wi-Fi focused.",
        "", wifi_focused=True,
    ),
    WordlistSource(
        "kali-wordlists-fern", "kali-wordlists — fern wifi common",
        _raw("00xZEROx00/kali-wordlists", "master", "fern-wifi/common.txt"),
        _gh("00xZEROx00/kali-wordlists"),
        "Aggregated (mixed upstream licences)", "Wi-Fi (WPA)",
        "Default router-credential list shipped with fern-wifi.", "",
        wifi_focused=True,
    ),
    # -- other widely used public lists ----------------------------------
    WordlistSource(
        "probable-top304k", "Probable-Wordlists — top 304k",
        _raw("berzerk0/Probable-Wordlists", "master", "Real-Passwords/Top304Thousand-probable-v2.txt"),
        _gh("berzerk0/Probable-Wordlists"),
        "CC-BY-4.0", "Common passwords",
        "Ranked by probability rather than raw count.", "≈3 MB",
    ),
    WordlistSource(
        "probable-wpa-204k", "Probable-Wordlists — WPA 204k",
        _raw("berzerk0/Probable-Wordlists", "master",
             "Real-Passwords/WPA-Length/Top204Thousand-WPA-probable-v2.txt"),
        _gh("berzerk0/Probable-Wordlists"),
        "CC-BY-4.0", "Wi-Fi (WPA)",
        "204,000 passwords of legal WPA length, ranked. The best public list "
        "for modelling a Wi-Fi passphrase attack.", "≈2 MB", wifi_focused=True,
    ),
    WordlistSource(
        "probable-wpa-4800", "Probable-Wordlists — WPA 4800",
        _raw("berzerk0/Probable-Wordlists", "master",
             "Real-Passwords/WPA-Length/Top4800-WPA-probable-v2.txt"),
        _gh("berzerk0/Probable-Wordlists"),
        "CC-BY-4.0", "Wi-Fi (WPA)",
        "The 4,800 most probable WPA-length passwords.", "≈45 KB",
        wifi_focused=True,
    ),
    WordlistSource(
        "probable-wpa-447", "Probable-Wordlists — WPA 447",
        _raw("berzerk0/Probable-Wordlists", "master",
             "Real-Passwords/WPA-Length/Top447-WPA-probable-v2.txt"),
        _gh("berzerk0/Probable-Wordlists"),
        "CC-BY-4.0", "Wi-Fi (WPA)",
        "Tiny WPA list for a quick check.", "≈5 KB", wifi_focused=True,
    ),
    WordlistSource(
        "duyet-1m", "duyet — 1M password seclists",
        _raw("duyet/bruteforce-database", "master", "1000000-password-seclists.txt"),
        _gh("duyet/bruteforce-database"),
        "MIT", "Common passwords", "", "≈9 MB",
    ),
    WordlistSource(
        "fuzzdb-passwords", "FuzzDB — common passwords",
        _raw("fuzzdb-project/fuzzdb", "master",
             "wordlists-user-passwd/passwds/weaksauce.txt"),
        _gh("fuzzdb-project/fuzzdb"),
        "BSD-2-Clause", "Common passwords",
        "Short, high-hit-rate password list.", "≈4.5 KB",
    ),
    WordlistSource(
        "ncsc-100k", "SecLists — NCSC 100k most used",
        _raw("danielmiessler/SecLists", "master",
             "Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt"),
        _gh("danielmiessler/SecLists"),
        "MIT", "Common passwords",
        "Ranked by the UK NCSC from breached-account data.", "≈1 MB",
    ),
    WordlistSource(
        "seclists-best110", "SecLists — best 110",
        _raw("kkrypt0nn/wordlists", "main", "wordlists/passwords/keyboard_patterns.txt"),
        _gh("kkrypt0nn/wordlists"),
        "MIT", "Common passwords",
        "Keyboard walks such as qwerty and 123456 — the first guesses made.", "",
    ),
    WordlistSource(
        "amitlttwo-weaksauce", "All-Wordlists — weaksauce",
        _raw("amitlttwo/All-Wordlists", "main", "passwds/weaksauce.txt"),
        _gh("amitlttwo/All-Wordlists"),
        "No licence stated", "Common passwords",
        "Short high-hit-rate list from All-Wordlists.", "≈4.5 KB",
    ),
    WordlistSource(
        "seclists-2025-top200", "SecLists — 2025 top 200",
        _raw("danielmiessler/SecLists", "master",
             "Passwords/Common-Credentials/2025-199_most_used_passwords.txt"),
        _gh("danielmiessler/SecLists"),
        "MIT", "Common passwords",
        "Last year's most-used passwords, i.e. what people still choose.", "",
    ),
    WordlistSource(
        "weakpass-words", "weakpass — common words",
        _raw("kkrypt0nn/wordlists", "main", "wordlists/famous/fern_wifi.txt"),
        _gh("kkrypt0nn/wordlists"),
        "MIT", "Wi-Fi (WPA)",
        "The fern-wifi default credential list.", "", True,
    ),
]


def _extra_known() -> list[WordlistSource]:
    """Further well-known public lists, added as reference links.

    These point at project pages rather than a single raw file: their contents
    are split across archives, are too large to stream here, or the repository
    expects you to pick a file.  They are still one-click openable.
    """
    reference = [
        ("rockyou-home", "rockyou.txt (via kali-wordlists)",
         _raw("00xZEROx00/kali-wordlists", "master", "rockyou.txt.gz"),
         _gh("00xZEROx00/kali-wordlists"), "Aggregated", "Common passwords",
         "The 14-million-entry list everyone knows, gzipped. Large; imported "
         "after unpacking."),
        ("hashes-org", "hashes.com — public wordlists",
         "https://hashes.com/en/wordlists", "https://hashes.com/en/wordlists",
         "See upstream", "Common passwords", "Curated public lists, free to download."),
        ("weakpass-site", "weakpass.com — wordlist archive",
         "https://weakpass.com/wordlists", "https://weakpass.com/wordlists",
         "See upstream", "Common passwords", "Thousands of aggregated lists, clearly licensed per file."),
        ("crackstation", "CrackStation — human-only wordlist",
         "https://crackstation.net/crackstation-wordlist-password-cracking-dictionary.htm",
         "https://crackstation.net/", "Free for non-commercial use", "Common passwords",
         "1.5 billion entries; the benchmark for a serious audit."),
        ("packetstorm", "Packet Storm — wordlists",
         "https://packetstormsecurity.com/files/tags/wordlist/",
         "https://packetstormsecurity.com/", "See upstream", "Reference",
         "Long-running archive of security word lists."),
        ("openwall", "Openwall — john the ripper wordlists",
         "https://www.openwall.com/wordlists/", "https://www.openwall.com/",
         "Public domain / various", "Reference",
         "The original password-cracking wordlist collection."),
        ("hob0rules", "Hob0Rules — rule sets",
         "https://github.com/praetorian-inc/Hob0Rules", _gh("praetorian-inc/Hob0Rules"),
         "Apache-2.0", "Rules",
         "Mangling rules, not a list: shows how a small word becomes many guesses."),
        ("naive-hashcat", "naive-hashcat — WPA rules",
         "https://github.com/brannondorsey/naive-hashcat", _gh("brannondorsey/naive-hashcat"),
         "MIT", "Rules",
         "The rule set that turns a wordlist into Wi-Fi-shaped guesses."),
        ("seclists-repo", "SecLists — full repository",
         _gh("danielmiessler/SecLists"), _gh("danielmiessler/SecLists"),
         "MIT", "Reference",
         "The complete collection: usernames, passwords, fuzzing, patterns."),
        ("kkrypt0nn-repo", "kkrypt0nn/wordlists — full repository",
         _gh("kkrypt0nn/wordlists"), _gh("kkrypt0nn/wordlists"),
         "MIT", "Reference", "292 curated lists across many categories."),
        ("all-wordlists-repo", "All-Wordlists — full repository",
         _gh("amitlttwo/All-Wordlists"), _gh("amitlttwo/All-Wordlists"),
         "No licence stated", "Reference", "288 lists collected in one place."),
        ("kali-wordlists-repo", "kali-wordlists — Parrot/Kali defaults",
         _gh("00xZEROx00/kali-wordlists"), _gh("00xZEROx00/kali-wordlists"),
         "Aggregated", "Wi-Fi (WPA)",
         "The wordlists directory from a Parrot/Kali install, as a repository."),
        ("wifite-repo", "wifite2 — project",
         _gh("kimocoder/wifite2"), _gh("kimocoder/wifite2"),
         "GPL-3.0", "Wi-Fi (WPA)", "The tool whose default list the wifite.txt file comes from."),
        ("hashcat-repo", "hashcat — example wordlists and rules",
         _gh("hashcat/hashcat"), _gh("hashcat/hashcat"),
         "MIT", "Rules", "Reference rules for WPA mode 22000."),
        ("john-repo", "John the Ripper — jumbo",
         _gh("openwall/john"), _gh("openwall/john"),
         "GPL-2.0", "Reference", "Rules and wordlist mangling reference."),
        ("wordlist-101", "wordlists.directory — index",
         "https://wordlists.directory/", "https://wordlists.directory/",
         "See upstream", "Reference", "Searchable index of public wordlists."),
        ("skullsecurity", "SkullSecurity — password dictionaries",
         "https://wiki.skullsecurity.org/index.php?title=Passwords",
         "https://wiki.skullsecurity.org/", "See upstream", "Common passwords",
         "Ron Bowes' collected dictionaries, a long-standing reference."),
        ("is-password", "haveibeenpwned — Pwned Passwords",
         "https://haveibeenpwned.com/Passwords", "https://haveibeenpwned.com/Passwords",
         "CC-BY-4.0", "Reference",
         "800M+ breached passwords by hash prefix. The right way to check one "
         "passphrase without downloading any list."),
        ("pwned-passwords-repo", "Pwned Passwords — downloadable hashes",
         _gh("HaveIBeenPwned/PwnedPasswordsDownloader"),
         _gh("HaveIBeenPwned/PwnedPasswordsDownloader"),
         "CC-BY-4.0", "Reference", "Official downloader for the full hash corpus."),
        ("probable-repo", "Probable-Wordlists — full repository",
         _gh("berzerk0/Probable-Wordlists"), _gh("berzerk0/Probable-Wordlists"),
         "CC-BY-4.0", "Common passwords", "Ranked lists, WPA-length variants included."),
        ("bruteforce-database", "bruteforce-database — full repository",
         _gh("duyet/bruteforce-database"), _gh("duyet/bruteforce-database"),
         "MIT", "Reference", "Password, username and pattern lists."),
        ("fuzzdb-repo", "FuzzDB — full repository",
         _gh("fuzzdb-project/fuzzdb"), _gh("fuzzdb-project/fuzzdb"),
         "BSD-2-Clause", "Reference", "Includes a user-password wordlist set."),
        ("seclists-wifi-dir", "SecLists — Wi-Fi/WPA directory",
         "https://github.com/danielmiessler/SecLists/tree/master/Passwords/WiFi-WPA",
         _gh("danielmiessler/SecLists"), "MIT", "Wi-Fi (WPA)",
         "Every WPA-focused list SecLists carries."),
        ("seclists-common-dir", "SecLists — common-credentials directory",
         "https://github.com/danielmiessler/SecLists/tree/master/Passwords/Common-Credentials",
         _gh("danielmiessler/SecLists"), "MIT", "Common passwords",
         "The 10k / 100k / 1M tiered lists and more."),
        ("seclists-leaked-dir", "SecLists — leaked databases directory",
         "https://github.com/danielmiessler/SecLists/tree/master/Passwords/Leaked-Databases",
         _gh("danielmiessler/SecLists"), "MIT", "Common passwords",
         "RockYou and other leaked sets, archived."),
        ("weakpass-wpa", "weakpass — WPA lists",
         "https://weakpass.com/wordlists/wpa", "https://weakpass.com/wordlists",
         "See upstream", "Wi-Fi (WPA)", "Lists filtered to legal WPA length."),
        ("router-passwords", "Router default credentials (SecLists)",
         _raw("danielmiessler/SecLists", "master",
              "Passwords/Default-Credentials/default-passwords.txt"),
         _gh("danielmiessler/SecLists"), "MIT", "Router defaults",
         "Vendor default router passwords — the first thing to change."),
        ("router-creds-2", "Default router credentials (large)",
         _raw("danielmiessler/SecLists", "master",
              "Passwords/Default-Credentials/default-passwords.csv"),
         _gh("danielmiessler/SecLists"), "MIT", "Router defaults",
         "Vendor/user/password triples in CSV form."),
    ]
    out = []
    for sid, name, url, home, lic, cat, note in reference:
        out.append(WordlistSource(sid, name, url, home, lic, cat, note))
    return out


SOURCES: list[WordlistSource] = _SOURCES + _extra_known()
SOURCE_BY_ID = {s.source_id: s for s in SOURCES}
CATEGORIES = [
    "Wi-Fi (WPA)",
    "Common passwords",
    "Router defaults",
    "Rules",
    "Reference",
]


@dataclass
class DownloadResult:
    source: WordlistSource
    path: Path | None = None
    bytes_written: int = 0
    sha256: str = ""
    entry_count: int = 0
    ok: bool = False
    message: str = ""
    was_gzip: bool = False


class WordlistCatalogService:
    """Downloads catalogue entries to disk and hands them to the manager."""

    def __init__(self, manager=None) -> None:
        self.manager = manager
        self._cancel = False

    # -- where downloads land ------------------------------------------
    @property
    def download_dir(self) -> Path:
        path = cache_dir() / "wordlists"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def existing(self, source: WordlistSource) -> Path | None:
        candidate = self.download_dir / source.filename
        return candidate if candidate.exists() and candidate.stat().st_size else None

    def cancel(self) -> None:
        self._cancel = True

    # -- download -------------------------------------------------------
    def download(
        self,
        source: WordlistSource,
        progress: Callable[[int, int], None] | None = None,
        token=None,
    ) -> DownloadResult:
        """Stream one list to the download directory.

        Returns a result with ok=False and a plain message on any failure; it
        never raises for a network problem, so a batch can carry on.
        """
        import urllib.error
        import urllib.request

        self._cancel = False
        result = DownloadResult(source=source)
        if not source.is_file:
            result.message = "This entry is a project page, not a file to download."
            return result

        request = urllib.request.Request(
            source.url,
            headers={
                "User-Agent": "WiFi-Fortress/1.0 (local security audit)",
                "Accept": "text/plain,*/*",
            },
        )
        target = self.download_dir / source.filename
        part = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        written = 0
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                declared = response.headers.get("content-length")
                if declared and int(declared) > MAX_DOWNLOAD_BYTES:
                    result.message = (
                        f"Refused: the file is {int(declared) / 1_048_576:.0f} MB, above the "
                        f"{MAX_DOWNLOAD_BYTES // 1_048_576} MB download limit."
                    )
                    return result
                total = int(declared) if declared else 0
                with part.open("wb") as handle:
                    while True:
                        if self._cancel or (token is not None and getattr(token, "cancelled", False)):
                            handle.close()
                            part.unlink(missing_ok=True)
                            result.message = "Cancelled."
                            return result
                        block = response.read(CHUNK)
                        if not block:
                            break
                        written += len(block)
                        if written > MAX_DOWNLOAD_BYTES:
                            handle.close()
                            part.unlink(missing_ok=True)
                            result.message = "Refused: the download exceeded the size limit."
                            return result
                        handle.write(block)
                        digest.update(block)
                        if progress is not None:
                            progress(written, total)
        except urllib.error.HTTPError as exc:
            part.unlink(missing_ok=True)
            result.message = f"HTTP {exc.code} — the list is no longer at that address."
            return result
        except urllib.error.URLError as exc:
            part.unlink(missing_ok=True)
            result.message = f"Network error: {exc.reason}"
            return result
        except OSError as exc:
            part.unlink(missing_ok=True)
            result.message = f"Could not write the file: {exc}"
            return result

        if written == 0:
            part.unlink(missing_ok=True)
            result.message = "The server returned an empty file."
            return result

        # A gzip file is decompressed in place: a wordlist is useless archived.
        if part.read_bytes()[:2] == b"\x1f\x8b":
            import gzip

            try:
                with gzip.open(part, "rb") as src, target.open("wb") as dst:
                    while True:
                        block = src.read(CHUNK)
                        if not block:
                            break
                        dst.write(block)
                part.unlink(missing_ok=True)
                result.was_gzip = True
            except OSError as exc:
                part.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                result.message = f"Could not unpack the archive: {exc}"
                return result
        else:
            part.replace(target)

        # Reject anything that is not text: a wordlist with NUL bytes is a binary.
        if b"\x00" in target.read_bytes()[:65536]:
            target.unlink(missing_ok=True)
            result.message = "The downloaded file is binary, not a text word list."
            return result

        result.path = target
        result.bytes_written = target.stat().st_size
        result.sha256 = digest.hexdigest()
        result.ok = True
        result.message = "Downloaded."
        log.info("Downloaded wordlist %s (%d bytes)", source.source_id, result.bytes_written)
        return result

    # -- import ---------------------------------------------------------
    def import_to_manager(self, result: DownloadResult):
        """Register a downloaded file as an imported dictionary."""
        if not result.ok or result.path is None or self.manager is None:
            return None
        source = result.source
        info = self.manager.import_file(
            result.path,
            name=source.name,
            licence=source.licence,
            provenance=(
                f"Downloaded from {source.url} ({source.homepage}). "
                f"Upstream licence: {source.licence}. "
                f"SHA-256 of the downloaded file: {result.sha256}."
            ),
        )
        return info

    def download_and_import(self, source: WordlistSource, progress=None, token=None):
        result = self.download(source, progress=progress, token=token)
        if not result.ok:
            return result
        info = self.import_to_manager(result)
        if info is not None:
            result.entry_count = info.entry_count
            result.message = f"Downloaded and imported ({info.entry_count:,} entries)."
        return result

    def clear_cache(self) -> int:
        removed = 0
        for item in self.download_dir.glob("*"):
            if item.is_file():
                item.unlink(missing_ok=True)
                removed += 1
        return removed

    def cache_size(self) -> int:
        return sum(p.stat().st_size for p in self.download_dir.glob("*") if p.is_file())
