from __future__ import annotations

import subprocess
from pathlib import Path


def test_tokenizer_recovery_action_no_longer_names_deepseek_as_generic_provider() -> None:
    source = Path("codexchange_proxy/cli.py").read_text(encoding="utf-8")

    forbidden = "run cox tokenizer sync " + "deepseek --json"
    assert forbidden not in source


def test_tracked_debug_artifacts_do_not_republish_legacy_tokenizer_or_message_surface() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", ".debug"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.split("\0")

    forbidden = [
        "run cox tokenizer sync " + "deepseek --json",
        "run cox tokenizer status " + "deepseek --json",
        "messages_for_" + "deepseek",
        "messages_prepared_for_" + "deepseek",
    ]

    offenders: list[str] = []
    for item in tracked:
        if not item:
            continue
        path = Path(item)
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for marker in forbidden:
            if marker in text:
                offenders.append(f"{path}: {marker}")

    assert offenders == []
