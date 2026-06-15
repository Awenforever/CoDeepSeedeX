from __future__ import annotations

from codexchange_proxy import cli


def test_route_target_normalizer_prefers_reasoning_name() -> None:
    assert cli._normalize_route_target_to_reasoning("reasoning") is True
    assert cli._normalize_route_target_to_reasoning("thinking") is True
    assert cli._normalize_route_target_to_reasoning("standard") is False
    assert cli._normalize_route_target_to_reasoning("stable") is False
    assert cli._normalize_route_target_to_reasoning("non-thinking") is False
    assert cli._normalize_route_target_to_reasoning("non_thinking") is False
    assert cli._normalize_route_target_to_reasoning("nonthinking") is False
    assert cli._normalize_route_target_to_reasoning(None) is None


def test_legacy_thinking_normalizer_delegates_to_reasoning_name() -> None:
    for target in [
        "reasoning",
        "thinking",
        "standard",
        "stable",
        "non-thinking",
        "non_thinking",
        "nonthinking",
        None,
    ]:
        assert cli._normalize_route_target_to_thinking(target) is cli._normalize_route_target_to_reasoning(target)
