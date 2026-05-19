import pytest
from fastapi.testclient import TestClient

from deepseek_responses_proxy.app import PROXY_VERSION, create_app


def test_proxy_status_exposes_tool_bridge_provider_config(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_BRIDGE", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_TOOL_MAX_ROUNDS", "7")
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "serpapi")
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_MAX_RESULTS", "6")
    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("SERPAPI_API_KEY", "dummy-serpapi-key")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "glm")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_MODEL", "cogView-test")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_SIZE", "512x512")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_N", "2")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "true")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_OUTPUT_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_API_KEY", "dummy-image-key")

    client = TestClient(create_app())
    data = client.get("/v1/proxy/status").json()

    assert data["status"] == "ok"
    assert data["version"] == PROXY_VERSION
    assert data["tool_bridge"]["enabled"] is True
    assert data["tool_bridge"]["max_rounds"] == 7

    web_search = data["tool_bridge"]["web_search"]
    assert web_search["provider"] == "serpapi"
    assert web_search["is_mock"] is False
    assert web_search["max_results"] == 6
    assert web_search["timeout_seconds"] == 12.5
    assert web_search["api_key_configured"] is True

    image_generation = data["tool_bridge"]["image_generation"]
    assert image_generation["provider"] == "glm"
    assert image_generation["is_mock"] is False
    assert image_generation["model"] == "cogView-test"
    assert image_generation["size"] == "512x512"
    assert image_generation["n"] == 2
    assert image_generation["download_enabled"] is True
    assert image_generation["output_dir"] == str(tmp_path / "images")
    assert image_generation["api_key_configured"] is True


def test_dedicated_tool_bridge_status_route(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", raising=False)
    monkeypatch.delenv("IMAGE_PROVIDER", raising=False)

    client = TestClient(create_app())
    data = client.get("/v1/proxy/tool-bridge/status").json()

    assert data["status"] == "ok"
    assert data["version"] == PROXY_VERSION
    assert data["tool_bridge"]["enabled"] is True
    assert data["tool_bridge"]["web_search"]["provider"] == "mock"
    assert data["tool_bridge"]["web_search"]["is_mock"] is True
    assert data["tool_bridge"]["image_generation"]["provider"] == "mock"
    assert data["tool_bridge"]["image_generation"]["is_mock"] is True


def test_proxy_status_exposes_semantic_compaction_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_AUDIT", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_POLICY_DRY_RUN", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_SUMMARY_CHARS", "888")

    app = create_app()
    client = TestClient(app)

    data = client.get("/v1/proxy/status").json()
    semantic = data["semantic_compaction"]

    assert semantic["config"]["semantic_audit"]["enabled"] is True
    assert semantic["config"]["semantic_policy_dry_run"]["enabled"] is True
    assert semantic["config"]["semantic_payload_compaction"]["mode"] == "dry_run"
    assert semantic["config"]["semantic_payload_compaction"]["enabled"] is False
    assert semantic["config"]["semantic_payload_compaction"]["summary_chars"] == 888
    assert semantic["config"]["semantic_payload_canary"]["guard_enabled"] is True
    assert semantic["config"]["semantic_payload_canary"]["allow_enabled"] is False
    assert semantic["latest"]["semantic_audit"]["present"] is False
    assert semantic["latest"]["semantic_policy_dry_run"]["present"] is False
    assert semantic["latest"]["semantic_payload_compaction"]["present"] is False
    assert semantic["rollout"]["safe_to_enable_payload_compaction"] is False
    assert semantic["rollout"]["current_payload_mode"] == "dry_run"
    assert "semantic_audit_event_missing" in semantic["rollout"]["blockers"]
    assert "semantic_policy_dry_run_event_missing" in semantic["rollout"]["blockers"]
    assert "semantic_payload_compaction_event_missing" in semantic["rollout"]["blockers"]
    assert semantic["rollout"]["recommendation"] == "keep_dry_run_until_blockers_clear"


def test_proxy_debug_semantic_selftest_route(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")

    app = create_app()
    client = TestClient(app)

    data = client.get("/v1/proxy/debug/semantic-selftest").json()

    assert data["status"] == "ok"
    assert data["version"] == PROXY_VERSION
    assert data["kind"] == "semantic_compaction_selftest"
    assert data["assertions"]["original_messages_unchanged"] is True
    assert data["assertions"]["dry_run_not_applied"] is True
    assert data["assertions"]["enabled_applied"] is True
    assert data["assertions"]["low_risk_test_output_compacted"] is True
    assert data["assertions"]["medium_stacktrace_preserved"] is True
    assert data["assertions"]["high_chatty_terminal_preserved"] is True
    assert data["assertions"]["recent_low_risk_preserved"] is True
    assert data["synthetic_rollout"]["safe_to_enable_payload_compaction"] is True


def test_proxy_debug_semantic_canary_check_route_blocks_without_allow(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")
    monkeypatch.delenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", raising=False)

    app = create_app()
    client = TestClient(app)

    data = client.get("/v1/proxy/debug/semantic-canary-check").json()

    assert data["status"] == "blocked"
    assert data["kind"] == "semantic_compaction_canary_check"
    assert data["ready_for_limited_enabled_session"] is False
    assert "semantic_payload_canary_allow_enabled_not_set" in data["blockers"]


def test_proxy_debug_semantic_canary_check_route_ready_with_allow(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE", "dry_run")
    monkeypatch.setenv("DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_CANARY_ALLOW_ENABLED", "1")

    app = create_app()
    client = TestClient(app)

    data = client.get("/v1/proxy/debug/semantic-canary-check").json()

    assert data["status"] == "ok"
    assert data["ready_for_limited_enabled_session"] is True
    assert data["guard"]["allowed"] is True
    assert data["selftest"]["status"] == "ok"
    assert data["required_enable_env"]["DEEPSEEK_PROXY_FLATTENED_TOOL_SEMANTIC_PAYLOAD_COMPACTION_MODE"] == "enabled"


def test_proxy_debug_long_session_route_without_trace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    app = create_app()
    client = TestClient(app)

    data = client.get("/v1/proxy/debug/long-session?limit=25&mode=aggregate").json()

    assert data["status"] == "ok"
    assert data["version"] == PROXY_VERSION
    assert data["kind"] == "runtime_long_session_observability"
    assert data["mode"] == "aggregate"
    assert data["limit"] == 25
    assert data["trace_file_count"] == 0
    assert data["trace_event_count"] == 0
    assert data["context_budget"]["event_count"] == 0
    assert data["recommendation"] == "collect_more_trace_data"

@pytest.mark.asyncio
async def test_proxy_web_search_tavily_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Tavily result",
                        "url": "https://example.test/tavily",
                        "content": "Tavily snippet",
                        "published_date": "2026-05-12",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://api.tavily.com/search"
            assert headers["Authorization"] == "Bearer tvly-test-key"
            assert json["query"] == "provider test"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_web_search({"query": "provider test", "max_results": 1})
    assert result["ok"] is True
    assert result["provider"] == "tavily"
    assert result["results"][0]["snippet"] == "Tavily snippet"


@pytest.mark.asyncio
async def test_proxy_web_search_brave_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "brave")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "web": {
                    "results": [
                        {
                            "title": "Brave result",
                            "url": "https://example.test/brave",
                            "description": "Brave snippet",
                            "age": "May 12, 2026",
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers=None, params=None):
            assert url == "https://api.search.brave.com/res/v1/web/search"
            assert headers["X-Subscription-Token"] == "brave-test-key"
            assert params["q"] == "provider test"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_web_search({"query": "provider test", "max_results": 1})
    assert result["ok"] is True
    assert result["provider"] == "brave"
    assert result["results"][0]["snippet"] == "Brave snippet"


@pytest.mark.asyncio
async def test_proxy_image_generation_qwen_image_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "qwen_image")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_API_KEY", "dashscope-test-key")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "0")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"image": "https://example.test/qwen-image.png"}
                                ]
                            }
                        }
                    ]
                }
            }

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            assert headers["Authorization"] == "Bearer dashscope-test-key"
            assert json["model"] == "qwen-image-2.0-pro"
            assert json["input"]["messages"][0]["content"][0]["text"] == "draw a test image"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_image_generate({"prompt": "draw a test image"})
    assert result["ok"] is True
    assert result["provider"] == "qwen_image"
    assert result["model"] == "qwen-image-2.0-pro"
    assert result["images"][0]["url"] == "https://example.test/qwen-image.png"


@pytest.mark.asyncio
async def test_proxy_image_generation_zhipu_provider_uses_domestic_endpoint(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "zhipu")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_API_KEY", "zhipu-test-key")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "0")
    monkeypatch.delenv("DEEPSEEK_PROXY_IMAGE_BASE_URL", raising=False)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"url": "https://example.test/zhipu-image.png"}]}

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://open.bigmodel.cn/api/paas/v4/images/generations"
            assert headers["Authorization"] == "Bearer zhipu-test-key"
            assert json["model"] == "cogView-4-250304"
            assert json["prompt"] == "draw a zhipu image"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_image_generate({"prompt": "draw a zhipu image"})
    assert result["ok"] is True
    assert result["provider"] == "zhipu"
    assert result["images"][0]["url"] == "https://example.test/zhipu-image.png"


@pytest.mark.asyncio
async def test_proxy_image_generation_zai_provider_uses_international_endpoint(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "zai")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_API_KEY", "zai-test-key")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "0")
    monkeypatch.delenv("DEEPSEEK_PROXY_IMAGE_BASE_URL", raising=False)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"url": "https://example.test/zai-image.png"}]}

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://api.z.ai/api/paas/v4/images/generations"
            assert headers["Authorization"] == "Bearer zai-test-key"
            assert json["model"] == "cogView-4-250304"
            assert json["prompt"] == "draw a zai image"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_image_generate({"prompt": "draw a zai image"})
    assert result["ok"] is True
    assert result["provider"] == "zai"
    assert result["images"][0]["url"] == "https://example.test/zai-image.png"


@pytest.mark.asyncio
async def test_proxy_web_search_exa_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "exa")
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "title": "Exa result",
                        "url": "https://example.test/exa",
                        "text": "Exa snippet",
                        "publishedDate": "2026-05-12",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://api.exa.ai/search"
            assert headers["x-api-key"] == "exa-test-key"
            assert json["query"] == "provider test"
            assert json["numResults"] == 1
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_web_search({"query": "provider test", "max_results": 1})
    assert result["ok"] is True
    assert result["provider"] == "exa"
    assert result["results"][0]["snippet"] == "Exa snippet"


@pytest.mark.asyncio
async def test_proxy_web_search_firecrawl_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER", "firecrawl")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "firecrawl-test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "title": "Firecrawl result",
                        "url": "https://example.test/firecrawl",
                        "description": "Firecrawl snippet",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://api.firecrawl.dev/v2/search"
            assert headers["Authorization"] == "Bearer firecrawl-test-key"
            assert json["query"] == "provider test"
            assert json["limit"] == 1
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_web_search({"query": "provider test", "max_results": 1})
    assert result["ok"] is True
    assert result["provider"] == "firecrawl"
    assert result["results"][0]["snippet"] == "Firecrawl snippet"


@pytest.mark.asyncio
async def test_proxy_image_generation_stability_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "stability")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_API_KEY", "stability-test-key")

    class FakeResponse:
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"image": "ZmFrZS1pbWFnZQ=="}

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, files=None):
            assert url == "https://api.stability.ai/v2beta/stable-image/generate/core"
            assert headers["Authorization"] == "Bearer stability-test-key"
            assert files["prompt"][1] == "draw a stability image"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_image_generate({"prompt": "draw a stability image"})
    assert result["ok"] is True
    assert result["provider"] == "stability"
    assert result["model"] == "stable-image-core"
    assert result["images"][0]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_proxy_image_generation_fal_provider(monkeypatch):
    import importlib

    app_module = importlib.import_module("deepseek_responses_proxy.app")

    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_PROVIDER", "fal")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_API_KEY", "fal-test-key")
    monkeypatch.setenv("DEEPSEEK_PROXY_IMAGE_DOWNLOAD", "0")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "images": [
                    {
                        "url": "https://example.test/fal-image.png",
                        "content_type": "image/png",
                    }
                ]
            }

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None):
            assert url == "https://fal.run/fal-ai/flux/schnell"
            assert headers["Authorization"] == "Key fal-test-key"
            assert json["prompt"] == "draw a fal image"
            return FakeResponse()

    monkeypatch.setattr(app_module.httpx, "AsyncClient", FakeClient)

    result = await app_module._proxy_image_generate({"prompt": "draw a fal image"})
    assert result["ok"] is True
    assert result["provider"] == "fal"
    assert result["model"] == "fal-ai/flux/schnell"
    assert result["images"][0]["url"] == "https://example.test/fal-image.png"



def test_weclaw_http_profile_status_reports_effective_model_contract(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from deepseek_responses_proxy.app import create_app

    codex_config = tmp_path / "config.toml"
    codex_config.write_text(
        "[profiles.deepseek-thinking]\n"
        "model = \"glm-5.1\"\n"
        "model_provider = \"deepseek-thinking-proxy\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    client = TestClient(create_app())
    data = client.get("/v1/proxy/weclaw/profile-status?profile=deepseek-thinking").json()

    assert data["status"] == "ok"
    assert data["profile"] == "deepseek-thinking"
    assert data["model"]["codex_model"] == "glm-5.1"
    assert data["model"]["effective_model"] == "deepseek-v4-flash"
    assert data["model"]["force_model_enabled"] is True
    assert data["model"]["model_conflict"] is True
    assert data["model"]["display_hint"] is None
    assert data["model"]["diagnostic_hint"] == "Codex profile model differs from forced upstream model; dsproxy effective_model is authoritative."
    assert data["model"]["user_visible"] is False
    assert data["context_window"]["effective_safe_window_tokens"] == 750000
    assert data["context_window"]["used_tokens"] is None
    assert data["context_window"]["used_tokens_available"] is False
    assert data["context_window"]["used_tokens_source"] == "not_reported"
    assert "codex_profile_model_differs_from_effective_upstream_model" in data["health"]["warnings"]


def test_weclaw_http_status_exposes_runtime_context_contract(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from deepseek_responses_proxy.app import create_app

    codex_config = tmp_path / "config.toml"
    codex_config.write_text(
        "[profiles.deepseek-thinking]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_CONTEXT_COMPACTION", "1")
    monkeypatch.setenv("DEEPSEEK_PROXY_CONTEXT_COMPACTION_TRIGGER_CHARS", "12345")
    monkeypatch.setenv("DEEPSEEK_PROXY_CONTEXT_COMPACTION_TARGET_CHARS", "6789")

    client = TestClient(create_app())
    data = client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking").json()

    assert data["status"] == "ok"
    assert data["profile"] == "deepseek-thinking"
    assert data["context_window"]["codex_profile"]["unit"] == "tokens"
    assert data["context_window"]["used_tokens"] is None
    assert data["context_window"]["used_tokens_available"] is False
    assert data["context_window"]["used_tokens_source"] == "dsproxy_usage_ledger.latest_primary_turn.summary.prompt_tokens"
    assert data["context_window"]["runtime"]["unit"] == "chars"
    assert data["context_window"]["runtime"]["available"] is True
    assert data["runtime_payload_guard"]["available"] is False
    assert data["runtime_payload_guard"]["reason"] == "no_live_runtime_payload_guard_observation_yet"
    assert data["runtime_payload_guard"]["compaction"]["trigger_chars"] == 900000
    assert data["runtime_payload_guard"]["trimming"]["max_context_chars"] == 1500000
    assert data["compaction"]["available"] is True
    assert "tokens" in data
    assert data["tokens"]["last_turn"]["available"] is False

def test_weclaw_http_status_exposes_round3_contract_foundation(monkeypatch, tmp_path):
    catalog_path = tmp_path / "model-catalog.json"
    catalog_path.write_text(
        '{"models":[{"model":"deepseek-v4-flash","context_window_tokens":1000000}]}',
        encoding="utf-8",
    )
    codex_config = tmp_path / "config.toml"
    codex_config.write_text(
        "[profiles.deepseek-thinking]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n"
        f"model_catalog_json = \"{catalog_path}\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_TOKENIZER_RESOURCE_DIR", str(tmp_path / "missing-tokenizer-resources"))

    client = TestClient(create_app())
    profile_data = client.get("/v1/proxy/weclaw/profile-status?profile=deepseek-thinking").json()
    status_data = client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking").json()

    assert profile_data["context_window"]["model_catalog"]["available"] is True
    assert profile_data["context_window"]["model_catalog"]["context_window_tokens"] == 1000000
    assert profile_data["context_window"]["used_tokens_action"]
    assert profile_data["context_window"]["used_tokens_precision"] == "unavailable"
    assert profile_data["diagnostics"]["available"] is True
    assert "context_window.used_tokens" in {
        item["path"] for item in profile_data["diagnostics"]["degraded_fields"]
    }

    assert status_data["semantic_compaction"]["rollout"]["action"]
    assert status_data["semantic_compaction"]["rollout"]["missing_events"]
    assert "source_url" in status_data["pricing"]
    assert "ttl_seconds" in status_data["pricing"]
    assert status_data["pricing"]["refresh"]["available"] is True
    assert status_data["pricing"]["refresh"]["action"]
    assert status_data["diagnostics"]["available"] is True
    paths = {item["path"] for item in status_data["diagnostics"]["degraded_fields"]}
    assert "tokens.last_turn" in paths
    assert "pricing.refresh" not in paths
    assert "semantic_compaction.rollout" in paths


def test_weclaw_http_status_exposes_token_attribution_boundaries(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from deepseek_responses_proxy.app import create_app

    codex_config = tmp_path / "config.toml"
    codex_config.write_text(
        "[profiles.deepseek-thinking]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_TOKENIZER_RESOURCE_DIR", str(tmp_path / "missing-tokenizer-resources"))

    client = TestClient(create_app())
    data = client.get("/v1/proxy/weclaw/status?profile=deepseek-thinking&include_balance=false").json()

    assert data["status"] == "ok"
    tokens = data["tokens"]
    assert tokens["taxonomy"]["version"] == 9
    assert tokens["taxonomy"]["precision"]["provider_usage_totals"] == "exact_provider_reported"
    assert tokens["taxonomy"]["precision"]["purpose_attribution"] == "exact_dsproxy_call_purpose"
    assert tokens["taxonomy"]["precision"]["prompt_subcategory_split"] == "unavailable"

    assert tokens["attribution"]["provider_usage_totals"]["precision"] == "exact_provider_reported"
    assert tokens["attribution"]["purpose_attribution"]["precision"] == "exact_dsproxy_call_purpose"
    assert tokens["attribution"]["profile_tokenizer"]["available"] is False
    assert tokens["attribution"]["profile_tokenizer"]["billing_authoritative"] is False

    assert tokens["profile_tokenizer"]["available"] is False
    assert tokens["profile_tokenizer"]["summary"]["available"] is False
    assert tokens["prompt_subcategory_split"]["available"] is False
    assert tokens["prompt_subcategory_split"]["precision"] == "unavailable"
    assert tokens["prompt_subcategory_split"]["reason"] == "profile_tokenizer_json_not_found"
    assert "profile_tokenizer_resource" in tokens["prompt_subcategory_split"]["missing"]
