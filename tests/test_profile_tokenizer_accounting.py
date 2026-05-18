from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from deepseek_responses_proxy.app import (
    DeepSeekClient,
    SQLiteResponseStore,
    _profile_tokenizer_report_for_messages,
    _weclaw_tokens_contract,
    create_app,
)
from deepseek_responses_proxy.cli import (
    _sync_deepseek_tokenizer_resource,
    _tokenizer_resource_status,
)


def _write_test_tokenizer(path: Path) -> None:
    tokenizer = Tokenizer(
        WordLevel(
            {
                "[UNK]": 0,
                "You": 1,
                "are": 2,
                "concise": 3,
                "Hello": 4,
                "token": 5,
                "accounting": 6,
                "Previous": 7,
                "answer": 8,
                "tool": 9,
                "output": 10,
                "text": 11,
                "deepseek": 12,
                "proxy": 13,
                "persistent": 14,
                "compaction": 15,
                "summary": 16,
                "older": 17,
                "context": 18,
                "from": 19,
                "WeClaw": 20,
                "Runtime": 21,
                "status": 22,
                "prompt": 23,
            },
            unk_token="[UNK]",
        )
    )
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.save(str(path))


@pytest.fixture()
def tokenizer_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "tokenizer.json"
    _write_test_tokenizer(path)
    monkeypatch.setenv("DEEPSEEK_PROXY_DEEPSEEK_TOKENIZER_JSON", str(path))
    return path


def test_profile_tokenizer_counts_prompt_subcategories_with_env_tokenizer(tokenizer_json: Path) -> None:
    report = _profile_tokenizer_report_for_messages(
        [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": "Hello token accounting."},
            {"role": "assistant", "content": "Previous answer."},
            {"role": "tool", "content": "tool output text"},
            {
                "role": "user",
                "content": "[deepseek-proxy persistent compaction summary]\nolder context",
            },
        ],
        profile="deepseek",
        model="deepseek-v4-flash",
        provider="deepseek",
    )

    assert report["available"] is True
    assert report["tokenizer"]["tokenizer_kind"] == "deepseek_official_current"
    assert report["tokenizer"]["source"] == str(tokenizer_json)
    split = report["prompt_subcategory_split"]
    assert split["available"] is True
    assert split["is_estimated"] is True
    assert split["precision"] == "local_profile_tokenizer_content_estimate"
    assert split["categories"]["user"]["tokens"] > 0
    assert split["categories"]["system"]["tokens"] > 0
    assert split["categories"]["assistant_history"]["tokens"] > 0
    assert split["categories"]["tool_output"]["tokens"] > 0
    assert split["categories"]["compaction_summary"]["tokens"] > 0
    assert split["total_tokens"] == report["summary"]["total_content_tokens"]


def test_weclaw_tokens_contract_exposes_profile_tokenizer_split_when_available(tmp_path: Path, tokenizer_json: Path) -> None:
    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    store.record_usage(
        response_id="resp_1",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=False,
        usage_numbers={
            "prompt_tokens": 20,
            "completion_tokens": 5,
            "total_tokens": 25,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.001,
        purpose="primary",
        call_index=0,
        request_id="req_1",
        requested_model="deepseek-v4-flash",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )
    report = _profile_tokenizer_report_for_messages(
        [{"role": "user", "content": "Hello from WeClaw."}],
        profile="deepseek",
        model="deepseek-v4-flash",
        provider="deepseek",
    )

    tokens = _weclaw_tokens_contract(store, profile="deepseek", profile_tokenizer_report=report)

    assert tokens["taxonomy"]["version"] == 4
    assert tokens["profile_tokenizer"]["available"] is True
    assert tokens["prompt_subcategory_split"]["available"] is True
    assert tokens["prompt_subcategory_split"]["categories"]["user"]["tokens"] > 0
    assert tokens["last_turn"]["summary"]["prompt_tokens"] == 20
    assert tokens["attribution"]["provider_usage_totals"]["precision"] == "exact_provider_reported"
    assert tokens["attribution"]["profile_tokenizer"]["billing_authoritative"] is False


def test_tokenizer_sync_installs_official_zip_entries_from_local_source(tmp_path: Path) -> None:
    tokenizer = tmp_path / "tokenizer.json"
    _write_test_tokenizer(tokenizer)
    config = tmp_path / "tokenizer_config.json"
    config.write_text(json.dumps({"tokenizer_class": "LlamaTokenizerFast"}), encoding="utf-8")

    archive_path = tmp_path / "deepseek-tokenizer.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(tokenizer, "deepseek_v3_tokenizer/tokenizer.json")
        archive.write(config, "deepseek_v3_tokenizer/tokenizer_config.json")

    expected_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    resource_root = tmp_path / "resources"

    result = _sync_deepseek_tokenizer_resource(
        source_url=str(archive_path),
        expected_sha256=expected_sha,
        resource_root=str(resource_root),
        timeout=5,
        force=True,
    )

    assert result["status"] == "ok"
    assert result["changed"] is True
    assert Path(result["tokenizer_json"]).is_file()
    status = _tokenizer_resource_status("deepseek", resource_root=str(resource_root))
    assert status["available"] is True
    assert status["manifest"]["source_zip_sha256"] == expected_sha
    assert status["manifest"]["upstream_archive_internal_dir"] == "deepseek_v3_tokenizer"


@pytest.mark.asyncio
async def test_runtime_weclaw_status_includes_latest_profile_tokenizer_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tokenizer_json: Path,
) -> None:
    codex_config = tmp_path / "codex.toml"
    codex_config.write_text(
        "[model_providers.deepseek-proxy]\n"
        "base_url = \"http://127.0.0.1:8000/v1\"\n\n"
        "[profiles.deepseek]\n"
        "model = \"deepseek-v4-flash\"\n"
        "model_provider = \"deepseek-proxy\"\n"
        "model_context_window = 1000000\n"
        "model_auto_compact_token_limit = 750000\n"
        "model_reasoning_effort = \"xhigh\"\n"
        "plan_mode_reasoning_effort = \"high\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_CONFIG_FILE", str(codex_config))
    monkeypatch.setenv("DEEPSEEK_PROXY_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("DEEPSEEK_PROXY_FORCE_MODEL", "1")

    store = SQLiteResponseStore(tmp_path / "usage.sqlite3")
    app = create_app(deepseek_client=DeepSeekClient(), store=store)
    report = _profile_tokenizer_report_for_messages(
        [{"role": "user", "content": "Runtime status prompt."}],
        profile="deepseek",
        model="deepseek-v4-flash",
        provider="deepseek",
    )
    app.state.last_profile_tokenizer_report_by_profile["deepseek"] = report
    store.record_usage(
        response_id="resp_2",
        previous_response_id=None,
        model="deepseek-v4-flash",
        thinking_enabled=False,
        usage_numbers={
            "prompt_tokens": 30,
            "completion_tokens": 5,
            "total_tokens": 35,
            "cached_tokens": 0,
            "reasoning_tokens": 0,
        },
        estimated_cost_usd=0.001,
        purpose="primary",
        call_index=0,
        request_id="req_2",
        requested_model="deepseek-v4-flash",
        effective_model="deepseek-v4-flash",
        upstream_model="deepseek-v4-flash",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/proxy/weclaw/status?profile=deepseek&include_balance=false")

    assert response.status_code == 200
    data = response.json()
    assert data["tokens"]["profile_tokenizer"]["available"] is True
    assert data["tokens"]["prompt_subcategory_split"]["available"] is True
    assert data["tokens"]["last_turn"]["summary"]["prompt_tokens"] == 30
