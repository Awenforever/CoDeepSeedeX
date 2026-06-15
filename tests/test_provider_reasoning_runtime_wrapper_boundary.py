import importlib
import inspect

proxy_app = importlib.import_module("codexchange_proxy.app")


class FakeReasoningAdapter:
    def __init__(self):
        self.values = []

    def normalize_reasoning_effort(self, value):
        self.values.append(value)
        mapping = {
            "tiny": "low",
            "xhigh": "max",
            "high": "high",
            "max": "max",
            None: None,
        }
        return mapping.get(value)


def test_extract_provider_request_reasoning_effort_uses_selected_adapter(monkeypatch):
    fake = FakeReasoningAdapter()
    monkeypatch.setattr(proxy_app, "get_provider_adapter", lambda provider_id: fake)

    assert proxy_app._extract_provider_request_reasoning_effort("fake-provider", {"reasoning_effort": "tiny"}) == "low"
    assert fake.values == ["tiny"]

    fake.values.clear()
    assert proxy_app._extract_provider_request_reasoning_effort(
        "fake-provider",
        {"reasoning": {"effort": "xhigh"}},
    ) == "max"
    assert fake.values == [None, None, "xhigh"]


def test_provider_reasoning_effort_config_uses_provider_wrapper(monkeypatch):
    fake = FakeReasoningAdapter()
    monkeypatch.setattr(proxy_app, "get_provider_adapter", lambda provider_id: fake)
    monkeypatch.setattr(proxy_app, "_thinking_enabled", lambda: True)

    assert proxy_app._provider_reasoning_effort_config("fake-provider", {"model_reasoning_effort": "tiny"}) == "low"
    assert fake.values == [None, "tiny"]


def test_provider_reasoning_effort_config_uses_env_fallback(monkeypatch):
    fake = FakeReasoningAdapter()
    monkeypatch.setattr(proxy_app, "get_provider_adapter", lambda provider_id: fake)
    monkeypatch.setattr(proxy_app, "_thinking_enabled", lambda: True)
    monkeypatch.setenv("COX_REASONING_EFFORT", "xhigh")

    assert proxy_app._provider_reasoning_effort_config("fake-provider", {}) == "max"
    assert fake.values[-1] == "xhigh"


def test_legacy_deepseek_reasoning_config_delegates_to_provider_wrapper(monkeypatch):
    seen = {}

    def fake_provider_config(provider_id, payload=None):
        seen["provider_id"] = provider_id
        seen["payload"] = payload
        return "high"

    monkeypatch.setattr(proxy_app, "_provider_reasoning_effort_config", fake_provider_config)

    payload = {"reasoning_effort": "high"}
    assert proxy_app._deepseek_reasoning_effort_config(payload) == "high"
    assert seen == {"provider_id": "deepseek", "payload": payload}


def test_reasoning_runtime_source_uses_provider_wrapper_for_live_route():
    create_app_source = inspect.getsource(proxy_app.create_app)
    chat_usage_source = inspect.getsource(proxy_app._chat_completions_with_usage)
    provider_config_source = inspect.getsource(proxy_app._provider_reasoning_effort_config)
    legacy_config_source = inspect.getsource(proxy_app._deepseek_reasoning_effort_config)

    assert '_provider_reasoning_effort_config("deepseek", payload)' in create_app_source
    assert '_provider_reasoning_effort_config("deepseek", payload)' in chat_usage_source
    assert "_deepseek_reasoning_effort_config(payload)" not in create_app_source
    assert "_deepseek_reasoning_effort_config(payload)" not in chat_usage_source

    assert "_normalize_provider_reasoning_effort(" in provider_config_source
    assert "_normalize_deepseek_reasoning_effort(" not in provider_config_source
    assert 'return _provider_reasoning_effort_config("deepseek", payload)' in legacy_config_source
