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
    assert semantic["latest"]["semantic_audit"]["present"] is False
    assert semantic["latest"]["semantic_policy_dry_run"]["present"] is False
    assert semantic["latest"]["semantic_payload_compaction"]["present"] is False
