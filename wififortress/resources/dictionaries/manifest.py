"""Persistent dictionary resources shipped with WiFi Fortress.

Every entry below is a short, manually curated list written for this project.
The files are generated deterministically by ``scripts/build_dictionaries.py``
so the counts recorded here can always be re-verified.

PROVENANCE
----------
* All ten resources are original compilations authored for WiFi Fortress.
* No third-party word list, leaked password dump or corpus is included.
* The content is limited to what is needed for local password-quality
  assessment: very common passwords, generic words in English and Romanian,
  keyboard/sequence patterns, substitution conventions, name/date shapes,
  short passphrase words and combined pattern sets.
* License for every bundled file: CC0-1.0 (public domain dedication) as
  applied to this compilation by its author.  Redistribution is permitted;
  attribution is appreciated but not required.
"""

from __future__ import annotations

from dataclasses import dataclass

BUNDLED_LICENSE = "CC0-1.0"
BUNDLED_PROVENANCE = (
    "Original compilation authored for WiFi Fortress; no third-party word list, "
    "corpus or leaked password dump is included."
)


@dataclass(frozen=True)
class DictionarySpec:
    dict_id: str
    name: str
    filename: str
    description: str
    purpose: str
    license: str = BUNDLED_LICENSE

    @property
    def provenance(self) -> str:
        return BUNDLED_PROVENANCE


DICTIONARY_SPECS: tuple[DictionarySpec, ...] = (
    DictionarySpec(
        dict_id="common_passwords",
        name="Common Passwords",
        filename="01-common-passwords.txt",
        description=(
            "Well-known default and frequently used passwords: vendor defaults, "
            "device presets and the classic top-of-list choices."
        ),
        purpose="Detect passwords that are effectively public knowledge.",
    ),
    DictionarySpec(
        dict_id="english_words",
        name="English Words",
        filename="02-english-words.txt",
        description=(
            "Common English words and everyday nouns, verbs and adjectives that "
            "people pick for passwords."
        ),
        purpose="Detect a single dictionary word used on its own.",
    ),
    DictionarySpec(
        dict_id="romanian_words",
        name="Romanian Words",
        filename="03-romanian-words.txt",
        description=(
            "Common Romanian words with correct diacritics (UTF-8) plus the "
            "unaccented spelling people actually type."
        ),
        purpose="Detect Romanian-language password choices and diacritic stripping.",
    ),
    DictionarySpec(
        dict_id="numeric_patterns",
        name="Numeric Patterns",
        filename="04-numeric-patterns.txt",
        description=(
            "Years, dates in common formats, repeated digits, ascending runs and "
            "typical numeric suffixes."
        ),
        purpose="Detect passwords made only of predictable numbers.",
    ),
    DictionarySpec(
        dict_id="keyboard_patterns",
        name="Keyboard Patterns",
        filename="05-keyboard-patterns.txt",
        description=(
            "Horizontal, vertical and diagonal keyboard walks on QWERTY and "
            "Romanian QWERTZ layouts, plus shift variants."
        ),
        purpose="Detect key-walk passwords such as qwerty or 1qaz2wsx.",
    ),
    DictionarySpec(
        dict_id="common_substitutions",
        name="Common Substitutions",
        filename="06-common-substitutions.txt",
        description=(
            "Leetspeak and letter-swap conventions (a->4, e->3, o->0, i->1, "
            "s->$, ...) used to 'harden' a dictionary word."
        ),
        purpose="Normalise substituted words before dictionary comparison.",
    ),
    DictionarySpec(
        dict_id="names_dates",
        name="Names and Dates",
        filename="07-names-dates.txt",
        description=(
            "Very common given names, family name shapes and date formats "
            "commonly used as passwords."
        ),
        purpose="Detect personal-name and birthday based passwords.",
    ),
    DictionarySpec(
        dict_id="short_passphrases",
        name="Short Passphrases",
        filename="08-short-passphrases.txt",
        description=(
            "Short everyday phrases and word pairs often joined into a "
            "passphrase-style password."
        ),
        purpose="Detect two- or three-word combinations with no randomness.",
    ),
    DictionarySpec(
        dict_id="extended_patterns",
        name="Extended Password Patterns",
        filename="09-extended-patterns.txt",
        description=(
            "Password shapes built from a word plus a predictable suffix or "
            "prefix: name + year, word + '123', symbol-padded words."
        ),
        purpose="Detect structural padding around an otherwise weak base.",
    ),
    DictionarySpec(
        dict_id="combined",
        name="Combined Dictionary",
        filename="10-combined.txt",
        description=(
            "De-duplicated union of the nine resources above, used for a single "
            "pass over all bundled patterns."
        ),
        purpose="One-pass lookup across every bundled resource.",
    ),
)

SPEC_BY_ID = {spec.dict_id: spec for spec in DICTIONARY_SPECS}
