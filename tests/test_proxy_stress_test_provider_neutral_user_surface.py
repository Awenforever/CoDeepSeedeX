from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts" / "proxy-stress-test.py"


def load_stress_module():
    spec = importlib.util.spec_from_file_location("proxy_stress_test_user_surface", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_stress_test_help_uses_standard_and_reasoning_as_primary_routes() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    output = completed.stdout

    assert "--standard-url" in output
    assert "--reasoning-url" in output
    assert "target route: standard, reasoning, or both" in output
    normalized = " ".join(output.split())
    assert "legacy aliases: stable, thinking" in normalized
    assert "CodeXchange standard route URL" in output
    assert "CodeXchange reasoning route URL" in output



def test_stress_test_profile_normalizer_keeps_legacy_aliases() -> None:
    module = load_stress_module()

    assert module.normalize_profile_targets("both") == ["standard", "reasoning"]
    assert module.normalize_profile_targets("standard") == ["standard"]
    assert module.normalize_profile_targets("reasoning") == ["reasoning"]
    assert module.normalize_profile_targets("stable") == ["standard"]
    assert module.normalize_profile_targets("thinking") == ["reasoning"]
    assert module.normalize_profile_targets("non_thinking") == ["standard"]



def test_stress_test_main_reports_provider_neutral_route_names(monkeypatch, tmp_path, capsys) -> None:
    module = load_stress_module()

    calls: list[str] = []

    def fake_http_json(method: str, url: str, payload=None, timeout: int = 120):
        calls.append(url)
        return 200, {"ok": True}

    monkeypatch.setattr(module, "http_json", fake_http_json)
    monkeypatch.setattr(module, "build_cases", lambda scale: [])
    monkeypatch.setattr(module, "run_previous_response_case", lambda base_url: [])

    output = tmp_path / "stress-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            "--profile",
            "reasoning",
            "--reasoning-url",
            "http://127.0.0.1:9001/v1",
            "--output",
            str(output),
        ],
    )

    assert module.main() == 0
    captured = capsys.readouterr().out

    assert "===== reasoning http://127.0.0.1:9001/v1 =====" in captured
    assert "===== thinking" not in captured
    assert calls == ["http://127.0.0.1:9001/healthz"]
    assert output.exists()
