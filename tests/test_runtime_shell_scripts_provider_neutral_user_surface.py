from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SHELL_SCRIPTS = [
    "scripts/cox-start",
    "scripts/cox-start-reasoning",
    "scripts/cox-status",
    "scripts/cox-status-reasoning",
]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_runtime_shell_script_messages_use_codexchange_routes() -> None:
    expected_markers = {
        "scripts/cox-start": [
            "CodeXchange standard runtime failed to start after 10 seconds",
        ],
        "scripts/cox-start-reasoning": [
            "CodeXchange reasoning runtime failed to start after 10 seconds",
            "CodeXchange reasoning runtime started on port",
        ],
        "scripts/cox-status": [
            "CodeXchange standard runtime is reachable at",
            "CodeXchange standard runtime is not reachable at",
        ],
        "scripts/cox-status-reasoning": [
            "CodeXchange reasoning runtime is reachable at",
            "CodeXchange reasoning runtime is NOT reachable at",
        ],
    }

    for rel, markers in expected_markers.items():
        text = _read(rel)
        for marker in markers:
            assert marker in text


def test_runtime_shell_script_messages_do_not_brand_routes_as_deepseek_proxy() -> None:
    combined = "\n".join(_read(rel) for rel in RUNTIME_SHELL_SCRIPTS)

    forbidden_markers = [
        "DeepSeek proxy failed to start",
        "DeepSeek thinking proxy failed to start",
        "DeepSeek thinking proxy started",
        "DeepSeek proxy is reachable",
        "DeepSeek proxy is not reachable",
        "DeepSeek thinking proxy is reachable",
        "DeepSeek thinking proxy is NOT reachable",
    ]
    for marker in forbidden_markers:
        assert marker not in combined
