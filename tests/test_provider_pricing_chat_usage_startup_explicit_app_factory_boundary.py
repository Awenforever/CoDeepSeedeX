from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from codexchange_proxy import app, cli, runtime_app


ROOT = Path(__file__).resolve().parents[1]
PRICING_ENV_NAMES = {
    "COX_PRICING_PROVIDER_ID",
    "COX_PRICING_PROVIDER_OWNED",
    "COX_PRICING_READER_MODE",
    "COX_PRICING_READER_PATH",
    "COX_PRICING_PROVIDER_CACHE_PATH",
}


def _namespace(**overrides):
    values = {
        "thinking": False,
        "port": 8765,
        "state_dir": None,
        "pid_file": None,
        "log_file": None,
        "db_path": None,
        "pricing_provider_id": None,
        "pricing_provider_owned": False,
        "pricing_mode": None,
        "pricing_provider_path": None,
    }
    values.update(overrides)
    return cli.argparse.Namespace(**values)


def test_start_parser_exposes_explicit_pricing_arguments_without_changing_defaults() -> None:
    args = cli.build_parser().parse_args(["start"])

    assert args.pricing_provider_id is None
    assert args.pricing_provider_owned is False
    assert args.pricing_mode is None
    assert args.pricing_provider_path is None
    assert cli._start_pricing_runtime_contract(args) == {
        "explicit": False,
        "provider_id": None,
        "activate": False,
        "mode": None,
        "provider_path": None,
    }


def test_start_pricing_runtime_requires_explicit_provider_and_path(tmp_path: Path) -> None:
    target = tmp_path / "pricing.json"
    target.write_text("{}\n", encoding="utf-8")

    contract = cli._start_pricing_runtime_contract(
        _namespace(
            pricing_provider_id="deepseek",
            pricing_provider_owned=True,
            pricing_provider_path=str(target),
        )
    )

    assert contract == {
        "explicit": True,
        "provider_id": "deepseek",
        "activate": True,
        "mode": "provider_owned",
        "provider_path": str(target),
    }

    with pytest.raises(ValueError, match="pricing-provider-id"):
        cli._start_pricing_runtime_contract(
            _namespace(
                pricing_provider_owned=True,
                pricing_provider_path=str(target),
            )
        )

    with pytest.raises(ValueError, match="pricing-provider-path"):
        cli._start_pricing_runtime_contract(
            _namespace(
                pricing_provider_id="deepseek",
                pricing_provider_owned=True,
            )
        )


def test_start_pricing_runtime_disabled_is_explicit_and_pathless() -> None:
    contract = cli._start_pricing_runtime_contract(
        _namespace(
            pricing_provider_id="deepseek",
            pricing_mode="disabled",
        )
    )

    assert contract == {
        "explicit": True,
        "provider_id": "deepseek",
        "activate": True,
        "mode": "disabled",
        "provider_path": None,
    }

    with pytest.raises(ValueError, match="valid only"):
        cli._start_pricing_runtime_contract(
            _namespace(
                pricing_provider_id="deepseek",
                pricing_mode="disabled",
                pricing_provider_path="/tmp/not-used.json",
            )
        )


def test_start_proxy_uses_dedicated_runtime_module_only_for_explicit_pricing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "pricing.json"
    target.write_text("{}\n", encoding="utf-8")
    captured: list[dict[str, object]] = []
    process_started = {"value": False}

    class FakeProcess:
        pid = 12345
        returncode = None

        def poll(self):
            return None

    for name in PRICING_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(cli, "_maybe_print_startup_release_update_notice", lambda: None)
    monkeypatch.setattr(cli, "_managed_profile_route_preflight_or_error", lambda reason: None)
    monkeypatch.setattr(cli, "_read_pid", lambda path: None)
    monkeypatch.setattr(cli, "default_env_file_path", lambda: tmp_path / "missing-env")
    monkeypatch.setattr(cli, "_tcp_port_open", lambda host, port: False)

    def fake_healthz(port, *, timeout=1.0):
        if process_started["value"]:
            return 200, {"version": cli.PROXY_VERSION}, None
        return None, None, "connection_refused"

    def fake_popen(cmd, **kwargs):
        process_started["value"] = True
        captured.append({"cmd": list(cmd), **kwargs})
        return FakeProcess()

    monkeypatch.setattr(cli, "_healthz_for_port", fake_healthz)

    def fake_runtime_identity(port, *, timeout=1.0):
        if port == 8765:
            return 200, {
                "contract": "provider_pricing_runtime_identity_v1",
                "pricing_provider_id": "deepseek",
                "pricing_activate": True,
                "pricing_mode": "provider_owned",
                "pricing_provider_path": str(target),
            }, None
        return 200, {
            "contract": "provider_pricing_runtime_identity_v1",
            "pricing_provider_id": None,
            "pricing_activate": False,
            "pricing_mode": "legacy_shared",
            "pricing_provider_path": None,
        }, None

    monkeypatch.setattr(cli, "_runtime_pricing_identity_for_port", fake_runtime_identity)
    monkeypatch.setattr(cli, "_process_start_identity", lambda pid: f"test-start:{pid}")
    monkeypatch.setattr(
        cli,
        "_cmdline_for_pid",
        lambda pid: "python -m codexchange_proxy.runtime_app --port 8765",
    )
    monkeypatch.setattr(cli.subprocess, "Popen", fake_popen)

    explicit_args = _namespace(
        state_dir=str(tmp_path / "explicit-state"),
        pricing_provider_id="deepseek",
        pricing_provider_owned=True,
        pricing_provider_path=str(target),
    )
    assert cli._start_proxy(explicit_args) == 0

    explicit_cmd = captured[-1]["cmd"]
    assert explicit_cmd[:3] == [cli.sys.executable, "-m", "codexchange_proxy.runtime_app"]
    assert "--pricing-provider-id" in explicit_cmd
    assert "--pricing-activate" in explicit_cmd
    assert "--pricing-mode" in explicit_cmd
    assert "provider_owned" in explicit_cmd
    assert "--pricing-provider-path" in explicit_cmd
    explicit_env = captured[-1]["env"]
    assert PRICING_ENV_NAMES.isdisjoint(explicit_env)

    process_started["value"] = False
    legacy_args = _namespace(
        port=8766,
        state_dir=str(tmp_path / "legacy-state"),
    )
    assert cli._start_proxy(legacy_args) == 0

    legacy_cmd = captured[-1]["cmd"]
    assert legacy_cmd[:5] == [
        cli.sys.executable,
        "-m",
        "uvicorn",
        "codexchange_proxy.app:app",
        "--host",
    ]
    assert "codexchange_proxy.runtime_app" not in legacy_cmd


def test_runtime_app_factory_forwards_only_explicit_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "pricing.json"
    target.write_text("{}\n", encoding="utf-8")
    seen: dict[str, object] = {}
    sentinel = object()

    def fake_create_app(**kwargs):
        seen.update(kwargs)
        return sentinel

    monkeypatch.setattr(runtime_app, "create_app", fake_create_app)

    assert runtime_app.create_runtime_app(
        pricing_provider_id="deepseek",
        pricing_activate=True,
        pricing_mode="provider-owned",
        pricing_provider_path=target,
    ) is sentinel
    assert seen == {
        "pricing_provider_id": "deepseek",
        "pricing_activate": True,
        "pricing_mode": "provider_owned",
        "pricing_provider_path": target,
    }


def test_startup_factory_has_no_pricing_environment_activation_and_module_entry_stays_static() -> None:
    runtime_text = (ROOT / "codexchange_proxy" / "runtime_app.py").read_text(encoding="utf-8")
    runtime_tree = ast.parse(runtime_text)
    imported_modules = {
        alias.name
        for node in runtime_tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module
        for node in runtime_tree.body
        if isinstance(node, ast.ImportFrom)
    }

    assert "os" not in imported_modules
    assert PRICING_ENV_NAMES.isdisjoint(set(runtime_text.split()))
    assert "create_app(" in runtime_text
    assert "pricing_activate=True" in runtime_text

    app_text = (ROOT / "codexchange_proxy" / "app.py").read_text(encoding="utf-8")
    app_tree = ast.parse(app_text)
    module_app_calls = []
    for node in app_tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets):
            continue
        if isinstance(node.value, ast.Call):
            module_app_calls.append(node.value)

    assert len(module_app_calls) == 1
    assert isinstance(module_app_calls[0].func, ast.Name)
    assert module_app_calls[0].func.id == "create_app"
    assert module_app_calls[0].args == []
    assert module_app_calls[0].keywords == []
    assert "app" in imported_from

    for relative in (
        "scripts/cox-start",
        "scripts/cox-start-reasoning",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "codexchange_proxy.app:app" in text
        assert "codexchange_proxy.runtime_app" not in text
        assert "--pricing-provider-id" not in text
        assert "--pricing-provider-path" not in text

    wrapper_text = (ROOT / "scripts/codex-wrapper.bash").read_text(encoding="utf-8")
    assert "-m codexchange_proxy.cli" in wrapper_text
    assert "exec \"$python_bin\" -m codexchange_proxy.app:app" not in wrapper_text
    assert "exec \"$python_bin\" -m codexchange_proxy.runtime_app" not in wrapper_text
    assert "--pricing-provider-id" in wrapper_text
    assert "--pricing-mode" in wrapper_text
    assert "--pricing-provider-path" in wrapper_text
    assert "--owner-profile" in wrapper_text
    assert PRICING_ENV_NAMES.isdisjoint(set(wrapper_text.split()))
