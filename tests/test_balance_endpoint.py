import pytest
from httpx import ASGITransport, AsyncClient

from deepseek_responses_proxy.app import DeepSeekClient, InMemoryResponseStore, create_app


class BalanceDeepSeekClient(DeepSeekClient):
    async def user_balance(self):
        return {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "USD",
                    "total_balance": "12.34",
                    "granted_balance": "1.00",
                    "topped_up_balance": "11.34",
                }
            ],
        }


class BalanceErrorDeepSeekClient(DeepSeekClient):
    async def user_balance(self):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=502,
            detail={
                "upstream": "deepseek",
                "status_code": 401,
                "body": "unauthorized",
            },
        )


@pytest.mark.asyncio
async def test_proxy_balance_returns_deepseek_balance():
    app = create_app(deepseek_client=BalanceDeepSeekClient(), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/balance")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["upstream"] == "deepseek"
    assert data["balance"]["is_available"] is True
    assert data["balance"]["balance_infos"][0]["currency"] == "USD"
    assert data["balance"]["balance_infos"][0]["total_balance"] == "12.34"


@pytest.mark.asyncio
async def test_proxy_balance_returns_clean_error():
    app = create_app(deepseek_client=BalanceErrorDeepSeekClient(), store=InMemoryResponseStore())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/balance")

    assert response.status_code == 502
    detail = response.json()["detail"]

    assert detail["upstream"] == "deepseek"
    assert detail["status_code"] == 401
    assert "unauthorized" in detail["body"]
