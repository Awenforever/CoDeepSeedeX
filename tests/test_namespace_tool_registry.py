import json
from pathlib import Path

from fastapi.testclient import TestClient

from deepseek_responses_proxy.app import PROXY_VERSION, create_app


def deepseek_text_response(content: str = "ok") -> dict:
    return {
        "id": "chatcmpl_text",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


def deepseek_tool_call_response(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "id": "chatcmpl_tool",
        "object": "chat.completion",
        "created": 1,
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 1,
            "total_tokens": 2,
        },
    }


class RecordingDeepSeekClient:
    base_url = "https://api.deepseek.test"

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def chat_completions(self, payload: dict) -> dict:
        self.calls.append(payload)
        if not self.responses:
            raise AssertionError("unexpected chat_completions call")
        return self.responses.pop(0)

    async def user_balance(self) -> dict:
        return {"is_available": True, "balance_infos": []}


def test_deepseek_proxy_account_namespace_expands_to_proxy_tools(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    fake_client = RecordingDeepSeekClient([deepseek_text_response("namespace registered")])

    client = TestClient(create_app(deepseek_client=fake_client))
    response = client.post(
        "/v1/responses",
        json={
            "model": "deepseek-v4-pro",
            "input": "Check proxy account tools.",
            "tools": [
                {"type": "namespace", "namespace": "deepseek_proxy_account"},
            ],
        },
    )

    assert response.status_code == 200, response.text

    tool_names = {
        (tool.get("function") or {}).get("name")
        for tool in fake_client.calls[0]["tools"]
    }
    assert {
        "proxy_status",
        "proxy_usage_summary",
        "proxy_usage_events",
        "proxy_balance",
    }.issubset(tool_names)

    compat_warnings = json.loads(Path(".debug/last_compat_warnings.json").read_text())
    assert not [item for item in compat_warnings if item["kind"].startswith("unsupported")]

    mapped_namespaces = [
        item for item in compat_warnings
        if item["kind"] == "mapped_tool_namespace"
    ]
    assert mapped_namespaces
    assert mapped_namespaces[0]["namespace"] == "deepseek_proxy_account"
    assert {
        "proxy_status",
        "proxy_usage_summary",
        "proxy_usage_events",
        "proxy_balance",
    }.issubset(set(mapped_namespaces[0]["mapped_to"]))


def test_proxy_status_namespace_tool_executes_in_tool_bridge(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")

    fake_client = RecordingDeepSeekClient(
        [
            deepseek_tool_call_response("call_status", "proxy_status", {}),
            deepseek_text_response("status consumed"),
        ]
    )

    client = TestClient(create_app(deepseek_client=fake_client))
    response = client.post(
        "/v1/responses",
        json={
            "model": "deepseek-v4-pro",
            "input": "Use proxy_status.",
            "tools": [
                {"type": "namespace", "namespace": "deepseek_proxy_account"},
            ],
        },
    )

    assert response.status_code == 200, response.text
    assert len(fake_client.calls) == 2

    tool_messages = [
        message for message in fake_client.calls[1]["messages"]
        if message["role"] == "tool"
    ]
    assert len(tool_messages) == 1

    tool_result = json.loads(tool_messages[0]["content"])
    assert tool_result["ok"] is True
    assert tool_result["tool"] == "proxy_status"
    assert tool_result["version"] == PROXY_VERSION
    assert tool_result["tool_bridge"]["enabled"] is True
