"""Password assessment and generation.

Two independent services live here:

* :class:`PasswordAssessmentService` scores a password locally using length,
  composition, pattern detection and the enabled dictionaries.
* :class:`PasswordGeneratorService` creates passwords and passphrases with
  :mod:`secrets`.

Nothing in this module writes a password to disk, to a log or over the
network.  Inputs are held in memory only for the duration of a call.
"""

from __future__ import annotations

import math
import re
import secrets
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from wififortress.core.logging import get_logger
from wififortress.models.entities import PasswordAssessment

log = get_logger(__name__)

AMBIGUOUS = set("il1Lo0O|`'\"{}[]()/\\")
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?/"

# ---------------------------------------------------------------------------
# Pattern detection
# ---------------------------------------------------------------------------

_KEYBOARD_ROWS = [
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
    "1234567890",
    "qwertzuiop",
]
_KEYBOARD_VERTICAL = ["qaz", "wsx", "edc", "rfv", "tgb", "yhn", "ujm", "ik,", "ol."]


def _has_keyboard_walk(pw: str) -> bool:
    low = pw.lower()
    for row in _KEYBOARD_ROWS:
        for start in range(len(row) - 2):
            chunk = row[start : start + 3]
            if chunk in low or chunk[::-1] in low:
                return True
    for col in _KEYBOARD_VERTICAL:
        if col in low or col[::-1] in low:
            return True
    return False


def _has_sequence(pw: str) -> bool:
    """Detect ascending/descending runs (abc, 123, cba, 321)."""
    run = 1
    prev = None
    direction = 0
    for ch in pw:
        if prev is None:
            prev = ch
            continue
        delta = ord(ch) - ord(prev)
        if delta in (1, -1) and (direction == 0 or direction == delta):
            direction = delta
            run += 1
            if run >= 3:
                return True
        else:
            run = 1
            direction = delta if delta in (1, -1) else 0
        prev = ch
    return False


def _repeated_char_run(pw: str) -> int:
    best = 1
    run = 1
    for i in range(1, len(pw)):
        if pw[i] == pw[i - 1]:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def _repeated_block(pw: str) -> bool:
    """Detect 'abcabc', '12ab12ab' style repeats."""
    for size in range(1, len(pw) // 2 + 1):
        unit = pw[:size]
        if unit * (len(pw) // size) == pw and len(pw) // size >= 2:
            return True
    return False


_LEET_MAP = str.maketrans(
    {"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s",
     "$": "s", "7": "t", "+": "t", "8": "b", "9": "g", "6": "g", "|": "l"}
)


def _deleet(pw: str) -> str:
    return pw.lower().translate(_LEET_MAP)


def _entropy_bits(pw: str) -> float:
    """Character-pool entropy (an upper bound, documented in the UI)."""
    pool = 0
    if any(c.islower() for c in pw):
        pool += 26
    if any(c.isupper() for c in pw):
        pool += 26
    if any(c.isdigit() for c in pw):
        pool += 10
    if any(c in SYMBOLS or not c.isalnum() for c in pw):
        pool += 32
    if any(ord(c) > 127 for c in pw):
        pool += 100
    if pool == 0:
        return 0.0
    return len(pw) * math.log2(pool)


def _human_duration(seconds: float) -> str:
    if seconds < 1:
        return "under a second"
    units = [
        (60, "second", 1),
        (60, "minute", 60),
        (24, "hour", 3600),
        (365, "day", 86400),
        (100, "year", 31536000),
    ]
    if seconds < 60:
        return f"{seconds:.0f} seconds"
    if seconds < 3600:
        return f"{seconds / 60:.0f} minutes"
    if seconds < 86400:
        return f"{seconds / 3600:.0f} hours"
    if seconds < 31536000:
        return f"{seconds / 86400:.0f} days"
    years = seconds / 31536000
    if years < 1e3:
        return f"{years:.0f} years"
    if years < 1e6:
        return f"{years / 1e3:.0f} thousand years"
    if years < 1e9:
        return f"{years / 1e6:.0f} million years"
    if years < 1e12:
        return f"{years / 1e9:.0f} billion years"
    return "longer than the age of the universe"


@dataclass
class DictionarySet:
    """Word sets used for offline comparison (lowercase, in-memory)."""

    words: set[str] = field(default_factory=set)
    labels: dict[str, str] = field(default_factory=dict)
    loaded_from: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.words)

    @classmethod
    def from_files(
        cls, paths: Iterable[Path], max_words: int = 500_000
    ) -> "DictionarySet":
        words: set[str] = set()
        labels: dict[str, str] = {}
        loaded: list[str] = []
        for path in paths:
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        key = line.lower()
                        if key not in words:
                            words.add(key)
                            labels[key] = path.name
                        if len(words) >= max_words:
                            break
                loaded.append(path.name)
            except OSError as exc:
                log.warning("Dictionary not readable: %s (%s)", path, exc)
        return cls(words=words, labels=labels, loaded_from=loaded)


class PasswordAssessmentService:
    """Score a password entirely on this machine."""

    def __init__(self, dictionary: DictionarySet | None = None) -> None:
        self.dictionary = dictionary or DictionarySet()

    def set_dictionary(self, dictionary: DictionarySet) -> None:
        self.dictionary = dictionary

    # -- public API ----------------------------------------------------
    def assess(self, password: str) -> PasswordAssessment:
        if not password:
            return PasswordAssessment(
                strength="Empty",
                category="No password supplied",
                recommendations=["Enter a password to analyse it."],
            )

        result = PasswordAssessment(length=len(password))
        weaknesses: list[str] = []
        patterns: list[str] = []
        recommendations: list[str] = []

        lower = sum(1 for c in password if c.islower())
        upper = sum(1 for c in password if c.isupper())
        digits = sum(1 for c in password if c.isdigit())
        symbols = sum(1 for c in password if not c.isalnum())
        unique = len(set(password))

        result.composition = {
            "lowercase": lower,
            "uppercase": upper,
            "digits": digits,
            "symbols": symbols,
            "unique_characters": unique,
            "pool": self._pool_size(password),
        }

        # --- structural checks ---------------------------------------
        if len(password) < 8:
            weaknesses.append("Shorter than 8 characters")
            recommendations.append("Use at least 12 characters; 16 or more is better.")
        elif len(password) < 12:
            weaknesses.append("Shorter than 12 characters")
            recommendations.append("Extend the password to 16+ characters.")

        if upper == 0:
            weaknesses.append("No uppercase letters")
        if lower == 0:
            weaknesses.append("No lowercase letters")
        if digits == 0:
            weaknesses.append("No digits")
        if symbols == 0:
            weaknesses.append("No symbols")
        if 0 < unique <= max(1, len(password) // 3):
            weaknesses.append("Very low character variety")

        if _repeated_char_run(password) >= 3:
            patterns.append("Repeated characters (e.g. 'aaa')")
            weaknesses.append("Repeated character runs")
        if _repeated_block(password):
            patterns.append("Repeating block (e.g. 'abcabc')")
        if _has_sequence(password):
            patterns.append("Sequential characters (abc / 123 / cba)")
            weaknesses.append("Sequential character run")
        if _has_keyboard_walk(password):
            patterns.append("Keyboard walk (e.g. qwerty / asdf)")
            weaknesses.append("Keyboard pattern")
        if re.fullmatch(r"\d+", password):
            patterns.append("Digits only")
            weaknesses.append("Digits only")
        if re.fullmatch(r"[A-Za-z]+", password):
            patterns.append("Letters only")
        if re.search(r"(19|20)\d{2}", password):
            patterns.append("Contains a year")
        if re.fullmatch(r"(?=.*\d)(?=.*[A-Za-z]).{0,8}", password):
            patterns.append("Short word+number shape")

        # --- dictionary checks ---------------------------------------
        candidates = self._candidate_forms(password)
        hits: list[str] = []
        if self.dictionary.words:
            for candidate in candidates:
                if candidate in self.dictionary.words:
                    label = self.dictionary.labels.get(candidate, "dictionary")
                    hits.append(f"{candidate} ({label})")
                    if len(hits) >= 4:
                        break
        if hits:
            weaknesses.append("Contains a dictionary entry")
            recommendations.append(
                "Avoid words that appear in any dictionary, even with substitutions."
            )
        result.dictionary_hits = hits

        # --- scoring --------------------------------------------------
        score = self._score(password, upper, lower, digits, symbols, unique, weaknesses)
        result.score = score
        result.strength = self._strength_label(score)
        result.entropy_bits = _entropy_bits(password)
        result.category = self._category(score)
        result.weaknesses = weaknesses
        result.patterns = patterns
        result.recommendations = self._recommendations(
            score, weaknesses, patterns, recommendations
        )
        # Rough offline guessing estimate: 2^entropy / 1e10 guesses per second,
        # further divided when dictionary/pattern hits were found.
        guesses = 2 ** min(result.entropy_bits, 200) / 1e10
        if hits:
            guesses = min(guesses, 3600)
        if patterns:
            guesses = min(guesses, 86400)
        result.crack_time_estimate = _human_duration(guesses)
        return result

    # -- internals -----------------------------------------------------
    @staticmethod
    def _pool_size(password: str) -> int:
        pool = 0
        if any(c.islower() for c in password):
            pool += 26
        if any(c.isupper() for c in password):
            pool += 26
        if any(c.isdigit() for c in password):
            pool += 10
        if any(not c.isalnum() for c in password):
            pool += 32
        return pool

    @staticmethod
    def _candidate_forms(password: str) -> list[str]:
        low = password.lower()
        forms = {low, _deleet(password), low.strip(string.digits + string.punctuation)}
        stripped = low.strip(string.punctuation)
        forms.add(stripped)
        # strip trailing/leading digits (word+year shapes)
        core = re.sub(r"^[0-9]+|[0-9]+$", "", stripped)
        if core:
            forms.add(core)
        forms.add(core.translate(_LEET_MAP))
        return [f for f in forms if f]

    def _score(
        self,
        password: str,
        upper: int,
        lower: int,
        digits: int,
        symbols: int,
        unique: int,
        weaknesses: list[str],
    ) -> int:
        score = 0
        length = len(password)
        # Length is the dominant factor (0-45)
        score += min(45, int(length * 2.8))
        # Character classes (0-24)
        classes = sum(1 for c in (upper, lower, digits, symbols) if c)
        score += classes * 6
        # Variety (0-16)
        score += min(16, int(unique * 1.4))
        # Penalties
        if any("dictionary" in w.lower() for w in weaknesses):
            score -= 22
        if any("Sequential" in w for w in weaknesses):
            score -= 10
        if any("Keyboard" in w for w in weaknesses):
            score -= 12
        if any("Repeated character" in w for w in weaknesses):
            score -= 8
        if any("Digits only" in w for w in weaknesses):
            score -= 25
        if length < 8:
            score -= 20
        return max(0, min(100, score))

    @staticmethod
    def _strength_label(score: int) -> str:
        if score >= 85:
            return "Very strong"
        if score >= 70:
            return "Strong"
        if score >= 50:
            return "Moderate"
        if score >= 30:
            return "Weak"
        return "Very weak"

    @staticmethod
    def _category(score: int) -> str:
        if score >= 85:
            return "Resists offline guessing for decades"
        if score >= 70:
            return "Resists most targeted guessing"
        if score >= 50:
            return "Survives casual guessing only"
        if score >= 30:
            return "Guessed in minutes by modern hardware"
        return "Guessed almost immediately"

    # -- offline attack resistance -------------------------------------
    def attack_resistance(self, password: str) -> AttackResistance:
        """Model how long an offline attack on this passphrase would take.

        The model assumes an attacker who already holds a captured handshake
        for the network; that is exactly the scenario a passphrase has to
        survive, and it needs no attack to be performed here.  Nothing is
        sent anywhere and no cracking is attempted.
        """
        if not password:
            raise ValueError("A passphrase is required to model attack resistance")

        assessment = self.assess(password)
        length = len(password)
        # Keyspace of the WPA2-PSK format itself: 8-63 printable ASCII
        # characters.  Anything shorter is rejected by the standard.
        printable = 95
        keyspace_bits = length * math.log2(printable)

        # The practical entropy is capped by structural weakness: a dictionary
        # word plus a digit is guessed in wordlist order, not by brute force.
        pool = self._pool_size(password)
        estimated = length * math.log2(pool) if pool > 1 else 0.0
        dictionary_hit = bool(assessment.dictionary_hits)
        effective_bits = min(keyspace_bits, estimated)
        if dictionary_hit:
            # A wordlist hit collapses the search to the list size times the
            # small rules set applied on top of it.
            effective_bits = min(effective_bits, 22.0 + 3.0 * max(0, length - 8) / 4)

        guesses = 2 ** effective_bits if effective_bits > 0 else 1.0
        seconds: dict[str, float | None] = {}
        estimates: dict[str, str] = {}
        for label, rate in WPA2_HANDSHAKE_RATES.items():
            value = guesses / rate
            seconds[label] = value
            estimates[label] = _human_duration(value)

        # WPA3-SAE is attacked per connection, not per guess.
        sae_seconds = {
            label: guesses / rate for label, rate in SAE_HANDSHAKE_RATES.items()
        }

        if dictionary_hit:
            weakest = "dictionary word"
        elif _has_keyboard_walk(password):
            weakest = "keyboard pattern"
        elif _repeated_char_run(password) >= 3:
            weakest = "repeated characters"
        elif length < 10:
            weakest = "short length"
        else:
            weakest = "no structural weakness found"

        fastest = seconds["gpu_flagship"]
        if dictionary_hit or length < 8:
            verdict = "Weak"
            detail = (
                "This passphrase would be recovered in minutes by a single GPU "
                "against a captured handshake."
            )
        elif fastest < 3600:
            verdict = "Weak"
            detail = "Recoverable in under an hour on one modern GPU."
        elif fastest < 86400 * 30:
            verdict = "Moderate"
            detail = "Recoverable in days on one GPU; hours on a rented rig."
        elif fastest < 86400 * 365 * 5:
            verdict = "Strong"
            detail = "Would take months to years on one GPU - acceptable for home use."
        else:
            verdict = "Very strong"
            detail = "Beyond practical offline attack with current hardware."

        recommendations: list[str] = []
        if length < 12:
            recommendations.append(
                "Use at least 12 characters; 20 or a 5-word passphrase costs an "
                "attacker orders of magnitude more."
            )
        if dictionary_hit:
            recommendations.append(
                "Remove the dictionary word - attackers try wordlists before brute force."
            )
        if _has_keyboard_walk(password):
            recommendations.append("Avoid keyboard walks such as qwerty or 123456.")
        if any(ch.isdigit() for ch in password) and length < 14:
            recommendations.append(
                "Appending a year to a word is one of the first rules an attacker tries."
            )
        if verdict in ("Weak", "Moderate"):
            recommendations.append(
                "Generate a 20+ character random passphrase in the Password Laboratory and "
                "change it on the router."
            )
        if not recommendations:
            recommendations.append(
                "Keep this passphrase unique to this network and re-check it after any change."
            )

        return AttackResistance(
            length=length,
            keyspace_bits=keyspace_bits,
            entropy_bits=effective_bits,
            has_dictionary_hit=dictionary_hit,
            weakest_link=weakest,
            estimates=estimates,
            seconds_to_crack=seconds,
            verdict=verdict,
            verdict_detail=detail,
            recommendations=recommendations,
        )

    @staticmethod
    def _recommendations(
        score: int,
        weaknesses: list[str],
        patterns: list[str],
        existing: list[str],
    ) -> list[str]:
        recs = list(dict.fromkeys(existing))
        if score < 70:
            recs.append("Use a generated passphrase of four to six random words.")
        if any("dictionary" in w.lower() for w in weaknesses):
            recs.append("Replace dictionary words entirely instead of substituting letters.")
        if any("year" in p.lower() for p in patterns):
            recs.append("Remove years and dates; they are among the first guesses.")
        if not recs:
            recs.append("No structural weakness found; store it in a password manager.")
        return list(dict.fromkeys(recs))


# --------------------------------------------------------------------------
# Offline attack-resistance model for WPA2-PSK / WPA3-SAE passphrases
# --------------------------------------------------------------------------
# These figures are published, measured rates for the offline attack against
# a captured WPA2 handshake (PBKDF2-HMAC-SHA1, 4096 iterations, SSID as salt)
# and for WPA3-SAE (a memory-hard handshake, attacked per-connection).  They
# are planning numbers, not a promise: real hardware and luck vary.
WPA2_HANDSHAKE_RATES = {
    "cpu": 2_500,            # one core of a desktop CPU
    "gpu_entry": 100_000,    # entry-level gaming GPU
    "gpu_mid": 600_000,      # mid-range GPU
    "gpu_flagship": 3_000_000,  # flagship GPU, hcxdumptool+hashcat tuning
    "rig_8_gpu": 24_000_000,    # typical office cracking rig
}
SAE_HANDSHAKE_RATES = {
    "per_connection_cpu": 12,   # SAE handshakes per second, one CPU core
    "per_connection_gpu": 900,  # tuned GPU against one SAE connection
}


@dataclass
class AttackResistance:
    """How a specific passphrase would fare against an offline attack."""

    length: int
    keyspace_bits: float
    entropy_bits: float
    has_dictionary_hit: bool
    weakest_link: str
    estimates: dict[str, str]
    seconds_to_crack: dict[str, float | None]
    verdict: str
    verdict_detail: str
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "keyspace_bits": round(self.keyspace_bits, 1),
            "entropy_bits": round(self.entropy_bits, 1),
            "has_dictionary_hit": self.has_dictionary_hit,
            "weakest_link": self.weakest_link,
            "estimates": self.estimates,
            "verdict": self.verdict,
            "verdict_detail": self.verdict_detail,
            "recommendations": self.recommendations,
        }


class PasswordGeneratorService:
    """Cryptographically secure password and passphrase generation."""

    def __init__(self, word_source: DictionarySet | None = None) -> None:
        self._words: list[str] = []
        if word_source:
            self._words = sorted(
                w for w in word_source.words if w.isalpha() and 3 <= len(w) <= 10
            )

    def set_word_source(self, words: Iterable[str]) -> None:
        self._words = sorted({w for w in words if w.isalpha() and 3 <= len(w) <= 10})

    @property
    def has_word_source(self) -> bool:
        return len(self._words) >= 200

    def generate(
        self,
        length: int = 20,
        *,
        use_upper: bool = True,
        use_lower: bool = True,
        use_digits: bool = True,
        use_symbols: bool = True,
        exclude_ambiguous: bool = True,
    ) -> str:
        length = max(16, min(40, int(length)))
        pools: list[str] = []
        if use_lower:
            pools.append(string.ascii_lowercase)
        if use_upper:
            pools.append(string.ascii_uppercase)
        if use_digits:
            pools.append(string.digits)
        if use_symbols:
            pools.append(SYMBOLS)
        if not pools:
            raise ValueError("Select at least one character class")
        if exclude_ambiguous:
            pools = ["".join(c for c in p if c not in AMBIGUOUS) for p in pools]
        pools = [p for p in pools if p]

        # Guarantee one character from every selected class, then fill.
        chars = [secrets.choice(p) for p in pools]
        combined = "".join(pools)
        while len(chars) < length:
            chars.append(secrets.choice(combined))
        # Fisher-Yates shuffle with secrets.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return "".join(chars)

    def generate_passphrase(
        self, words: int = 5, separator: str = "-", capitalize: bool = False
    ) -> str:
        if not self.has_word_source:
            raise ValueError(
                "The bundled word lists do not provide enough words for a passphrase. "
                "Enable the English and Romanian dictionaries first."
            )
        words = max(3, min(10, int(words)))
        picked = [self._words[secrets.randbelow(len(self._words))] for _ in range(words)]
        if capitalize:
            picked = [w.capitalize() for w in picked]
        # Add one digit or symbol to avoid an all-letter passphrase.
        tail = secrets.choice(string.digits)
        return separator.join(picked) + tail

    def entropy_bits(self, password: str, *, pool_size: int | None = None) -> float:
        if pool_size is None:
            return _entropy_bits(password)
        return len(password) * math.log2(pool_size) if pool_size > 1 else 0.0

    def describe(self, password: str) -> list[str]:
        """Plain-language explanation of a generated password."""
        lines = [f"Length: {len(password)} characters"]
        classes = []
        if any(c.islower() for c in password):
            classes.append("lowercase letters")
        if any(c.isupper() for c in password):
            classes.append("uppercase letters")
        if any(c.isdigit() for c in password):
            classes.append("digits")
        if any(not c.isalnum() for c in password):
            classes.append("symbols")
        lines.append("Contains: " + ", ".join(classes) if classes else "Contains: nothing")
        bits = _entropy_bits(password)
        lines.append(f"Character-pool entropy: {bits:.0f} bits (upper bound)")
        lines.append(
            "Generated with Python's secrets module (CSPRNG); it is not derived "
            "from anything the application knows about you."
        )
        return lines
def iter_words_streaming(path: Path, limit: int | None = None) -> Iterator[str]:
    """Stream words from a file without loading it fully into memory."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            count = 0
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                yield line
                count += 1
                if limit is not None and count >= limit:
                    return
    except OSError as exc:
        log.warning("Cannot stream dictionary %s: %s", path, exc)
