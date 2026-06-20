from pathlib import Path


def test_final_release_blocker_terms_are_provider_neutralized() -> None:
    checks = {
        "codexchange_proxy/app.py": [
            ("DeepSeek compatibility", "provider compatibility"),
        ],
        "codexchange_proxy/cli.py": [
            ("DeepSeek compatibility", "provider compatibility"),
        ],
        "codexchange_proxy/providers/deepseek.py": [
            ("run cox tokenizer sync deepseek --json", "run cox tokenizer sync <provider> --json"),
            ("official DeepSeek pricing HTML", "official provider pricing source"),
        ],
        "docs/developer-handbook.md": [
            ("DeepSeek compatibility", "provider compatibility"),
        ],
    }

    root = Path(__file__).resolve().parents[1]
    for rel, pairs in checks.items():
        text = (root / rel).read_text(encoding="utf-8")
        for old, new in pairs:
            assert old not in text, rel
            assert new in text, rel
