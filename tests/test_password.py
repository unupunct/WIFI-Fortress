"""Password assessment and generation."""

from __future__ import annotations

import pytest

from wififortress.services.password_service import (
    DictionarySet,
    PasswordAssessmentService,
    PasswordGeneratorService,
)


# -- assessment ----------------------------------------------------------
def test_empty_password_scores_zero(assessment):
    result = assessment.assess("")
    assert result.score == 0
    assert result.strength == "Empty"
    assert result.recommendations


def test_short_common_password_is_weak(assessment):
    result = assessment.assess("password")
    assert result.score < 40
    assert result.dictionary_hits


def test_common_dictionary_word_detected(assessment):
    assert assessment.assess("football").dictionary_hits


def test_dictionary_match_is_case_insensitive(assessment):
    assert assessment.assess("FooTbAll").dictionary_hits


def test_leetspeak_substitution_detected(assessment):
    result = assessment.assess("p@ssw0rd")
    assert result.dictionary_hits or any("substitut" in p.lower() for p in result.patterns)


def test_year_and_date_patterns_flagged(assessment):
    result = assessment.assess("Summer2024!")
    assert result.patterns or result.dictionary_hits
    assert result.score < 90


def test_keyboard_walk_flagged(assessment):
    assert any("keyboard" in p.lower() for p in assessment.assess("qwertyui").patterns)


def test_repeated_characters_penalised(assessment):
    weak = assessment.assess("aaaaaaaa")
    strong = assessment.assess("Q7#vLm2!pXr9")
    assert weak.score < strong.score


def test_long_random_password_is_strong(assessment):
    result = assessment.assess("Q7#vLm2!pXr9&Zt4")
    assert result.score >= 80
    assert not result.dictionary_hits


def test_score_is_bounded(assessment):
    for candidate in ("", "a", "a" * 500, "Ünïcödé-Пароль-123!"):
        score = assessment.assess(candidate).score
        assert 0 <= score <= 100


def test_entropy_reported_for_unknown_inputs(assessment):
    result = assessment.assess("Tr0ub4dor&3")
    assert result.entropy_bits > 0


def test_strength_label_is_always_set(assessment):
    assert assessment.assess("somethingElse1!").strength
    assert assessment.assess("somethingElse1!").crack_time_estimate


# -- generation ----------------------------------------------------------
def test_generated_password_length_and_charset():
    generator = PasswordGeneratorService()
    password = generator.generate(24, use_symbols=True, use_digits=True)
    assert len(password) == 24
    assert any(c.isdigit() for c in password)
    assert any(c.isupper() for c in password)
    assert any(c.islower() for c in password)


def test_generation_is_random():
    generator = PasswordGeneratorService()
    samples = {generator.generate(20) for _ in range(25)}
    assert len(samples) == 25


def test_short_lengths_are_clamped_to_the_documented_minimum():
    generator = PasswordGeneratorService()
    assert len(generator.generate(4)) == 16


def test_no_character_class_selected_is_rejected():
    generator = PasswordGeneratorService()
    with pytest.raises(ValueError):
        generator.generate(20, use_upper=False, use_lower=False, use_digits=False, use_symbols=False)


def test_passphrase_word_count(dictionaries):
    generator = PasswordGeneratorService(
        DictionarySet.from_files(dictionaries.enabled_paths())
    )
    phrase = generator.generate_passphrase(words=5, separator="-")
    assert len(phrase.split("-")) == 5
    assert any(ch.isdigit() for ch in phrase)


def test_passphrase_without_word_source_is_refused():
    generator = PasswordGeneratorService()
    assert generator.has_word_source is False
    with pytest.raises(ValueError):
        generator.generate_passphrase(words=5)


def test_dictionary_set_counts_entries(dictionaries):
    word_set = DictionarySet.from_files(dictionaries.enabled_paths())
    assert len(word_set) >= 1000
