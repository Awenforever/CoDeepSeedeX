from __future__ import annotations

import argparse
import importlib
import inspect
from pathlib import Path

from codexchange_proxy import cli
from codexchange_proxy.providers import get_provider_adapter

proxy_app = importlib.import_module("codexchange_proxy.app")


def test_deepseek_provider_owns_account_balance_metadata() -> None:
    adapter = get_provider_adapter("deepseek")

    metadata = adapter.account_balance_metadata()

    assert metadata["provider"] == "deepseek"
    assert metadata["supported"] is True
    assert metadata["path"] == "/user/balance"
    assert metadata["url"] == "https://api.deepseek.com/user/balance"
    assert metadata["validation_method"] == "account_balance_probe"
    assert metadata["source"] == "provider_adapter.balance_metadata"


def test_deepseek_validation_request_delegates_to_balance_metadata() -> None:
    adapter = get_provider_adapter("deepseek")

    request = adapter.validation_request()
    metadata = adapter.account_balance_metadata()

    assert request.path == metadata["path"]
    assert request.validation_method == metadata["validation_method"]
    assert request.method == metadata["method"]


def test_cli_balance_defaults_route_through_provider_metadata() -> None:
    assert cli._provider_balance_url("deepseek") == "https://api.deepseek.com/user/balance"
    assert cli._provider_balance_validation_method("deepseek") == "account_balance_probe"

    custom_metadata = cli._provider_balance_metadata("custom")
    assert custom_metadata["supported"] is False


def test_cli_balance_unsupported_provider_is_capability_gated(capsys) -> None:
    rc = cli._balance(argparse.Namespace(provider="custom", env_file=None, url=None, timeout=0.01))

    captured = capsys.readouterr().out
    assert rc == 2
    assert "provider_balance_unsupported" in captured
    assert "https://api.deepseek.com/user/balance" not in captured


def test_cli_balance_help_no_longer_names_deepseek_as_product_boundary() -> None:
    text = Path("codexchange_proxy/cli.py").read_text(encoding="utf-8")

    assert 'help="query DeepSeek API account balance"' not in text
    assert 'help="query provider API account balance when supported"' in text
    assert 'balance.add_argument("--provider", default="deepseek"' in text


def test_proxy_tool_balance_description_is_provider_neutral() -> None:
    source = inspect.getsource(proxy_app._deepseek_proxy_account_tool_schemas)

    assert "Return DeepSeek account balance" not in source
    assert "Return provider account balance" in source


def test_runtime_balance_network_behavior_unchanged_in_first_patch() -> None:
    source = inspect.getsource(proxy_app.DeepSeekClient.user_balance)

    assert 'f"{self.base_url}/user/balance"' in source
