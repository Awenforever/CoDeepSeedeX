from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_compact_audit_runtime_route_wording_is_provider_neutral() -> None:
    app = read("codexchange_proxy/app.py")

    legacy_phrases = [
        "third-party DeepSeek route",
        "DeepSeek route native remote compaction support",
    ]
    for phrase in legacy_phrases:
        assert phrase not in app

    expected_phrases = [
        "cox provider-routed third-party route must not claim native remote compaction",
        "not claimed for provider-routed third-party routes",
    ]
    for phrase in expected_phrases:
        assert phrase in app


def test_compact_audit_docs_route_wording_is_provider_neutral() -> None:
    combined = "\n".join(
        [
            read("README.md"),
            read("README.zh-CN.md"),
            read("docs/development-log.md"),
        ]
    )

    legacy_phrases = [
        "third-party DeepSeek route",
        "DeepSeek route native remote compaction support",
        "第三方DeepSeek route",
    ]
    for phrase in legacy_phrases:
        assert phrase not in combined

    expected_phrases = [
        "provider-routed third-party routes",
        "通过provider路由的第三方route",
        "native remote compaction support for provider-routed third-party routes",
    ]
    for phrase in expected_phrases:
        assert phrase in combined
