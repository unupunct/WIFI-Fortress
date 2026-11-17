"""Offline attack-resistance model: honest, bounded, and structure-aware."""

from __future__ import annotations

import pytest

from wififortress.services.password_service import (
    DictionarySet,
    PasswordAssessmentService,
)


@pytest.fixture
def service(dictionaries):
    return PasswordAssessmentService(DictionarySet.from_files(dictionaries.enabled_paths()))


def test_empty_passphrase_is_refused(service):
    with pytest.raises(ValueError):
        service.attack_resistance("")


def test_dictionary_word_is_weak(service):
    result = service.attack_resistance("password123")
    assert result.verdict == "Weak"
    assert result.has_dictionary_hit is True
    assert result.weakest_link == "dictionary word"


def test_random_passphrase_is_strong(service):
    result = service.attack_resistance("Q7#vLm2!pXr9&Zt4")
    assert result.verdict in ("Strong", "Very strong")
    assert result.has_dictionary_hit is False


def test_longer_passphrase_takes_longer(service):
    short = service.attack_resistance("Zx9#kq")
    long = service.attack_resistance("Zx9#kqTrm2!vLp8&Wd4")
    assert long.seconds_to_crack["gpu_flagship"] > short.seconds_to_crack["gpu_flagship"]


def test_faster_hardware_reduces_time(service):
    result = service.attack_resistance("Trm2!vLp8&")
    assert (
        result.seconds_to_crack["rig_8_gpu"]
        < result.seconds_to_crack["gpu_flagship"]
        < result.seconds_to_crack["cpu"]
    )


def test_every_rate_has_a_human_estimate(service):
    result = service.attack_resistance("Trm2!vLp8&")
    assert set(result.estimates) == {
        "cpu", "gpu_entry", "gpu_mid", "gpu_flagship", "rig_8_gpu"
    }
    assert all(isinstance(v, str) and v for v in result.estimates.values())


def test_recommendations_are_always_actionable(service):
    for pw in ("password", "Summer2024!", "Q7#vLm2!pXr9&Zt4"):
        assert service.attack_resistance(pw).recommendations


def test_result_is_json_serialisable(service):
    payload = service.attack_resistance("Summer2024!").to_dict()
    assert payload["verdict"]
    assert isinstance(payload["estimates"], dict)


def test_no_cracking_is_performed(service):
    """The model must be pure arithmetic: same input, same output."""
    first = service.attack_resistance("StarWars1977").to_dict()
    second = service.attack_resistance("StarWars1977").to_dict()
    assert first == second
