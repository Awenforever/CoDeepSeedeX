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
