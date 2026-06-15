from __future__ import annotations

import asyncio
import inspect

import importlib

proxy_app = importlib.import_module("codexchange_proxy.app")


class FakeBalanceClient:
    api_key = "sk-test"

    async def user_balance(self):
        return {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "12.5",
                }
            ],
        }


def test_runtime_balance_provider_wrapper_is_provider_neutral() -> None:
    source = inspect.getsource(proxy_app._provider_balance_contract)

    assert "def _provider_balance_contract" in source
    assert "provider_id" in source
    assert "_provider_user_balance(provider_value, client)" in source
    assert "deepseek_client.user_balance" not in source
    assert "app.state.deepseek_client.user_balance" not in source


def test_legacy_weclaw_balance_wrapper_delegates_to_provider_contract() -> None:
    source = inspect.getsource(proxy_app._weclaw_balance_contract)

    assert "_provider_balance_contract(" in source
    assert '"deepseek"' in source
    assert "await deepseek_client.user_balance()" not in source


def test_proxy_balance_route_no_longer_calls_deepseek_client_directly() -> None:
    source = inspect.getsource(proxy_app.create_app)

    proxy_balance_block = source[source.index('async def proxy_balance()'):]
    proxy_balance_block = proxy_balance_block[: proxy_balance_block.index('return {') + 260]
    assert "_provider_user_balance(" in proxy_balance_block
    assert "app.state.deepseek_client.user_balance()" not in proxy_balance_block


def test_proxy_account_balance_tool_routes_through_provider_contract() -> None:
    source = inspect.getsource(proxy_app._execute_proxy_tool_call)
    block = source[source.index('if name == "proxy_balance":'):]
    block = block[: block.index('return {', block.index('return {') + 1) + 360]

    assert "_provider_balance_contract(" in block
    assert "await deepseek_client.user_balance()" not in block
    assert '"provider": balance_contract.get("provider") or "deepseek"' in block


def test_provider_balance_contract_preserves_deepseek_success_shape() -> None:
    result = asyncio.run(
        proxy_app._provider_balance_contract(
            "deepseek",
            client=FakeBalanceClient(),
            include_balance=True,
        )
    )

    assert result["available"] is True
    assert result["status"] == "ok"
    assert result["source"] == "provider_balance_api"
    assert result["provider"] == "deepseek"
    assert result["balance"]["balance_infos"][0]["currency"] == "CNY"
    assert result["currency"] == "CNY"
    assert result["amount"] == 12.5
    assert result["display"] == "12.5 CNY"


def test_provider_balance_contract_preserves_disabled_and_unavailable_reasons() -> None:
    disabled = asyncio.run(
        proxy_app._provider_balance_contract(
            "deepseek",
            client=FakeBalanceClient(),
            include_balance=False,
        )
    )
    unavailable = asyncio.run(
        proxy_app._provider_balance_contract(
            "custom",
            client=None,
            include_balance=True,
        )
    )

    assert disabled["available"] is False
    assert disabled["provider"] == "deepseek"
    assert disabled["reason"] == "disabled_by_request"
    assert unavailable["available"] is False
    assert unavailable["provider"] == "custom"
    assert unavailable["reason"] == "balance_client_unavailable"
