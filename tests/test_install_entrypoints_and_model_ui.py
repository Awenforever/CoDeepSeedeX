from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "scripts" / "install.sh"


def test_install_output_uses_absolute_uninstall_command() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert 'bash %s --uninstall' in text
    assert '"$INSTALL_DIR/scripts/install.sh"' in text


def test_install_repairs_codex_model_catalog_before_final_output() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    marker = "codeepseedex_repair_codex_model_catalog_json_v2746a1"
    final_output = 'sub_title "Installation files"'
    assert marker in text
    assert text.index(marker) < text.index(final_output)
    assert "profiles.deepseek-thinking" in text
    assert "model_catalog_json" in text


def test_docs_include_latest_tag_fallback_install_domains() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh" in readme
    assert "fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh" in readme
    assert "github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh" in readme
    assert "@master/bootstrap.sh" not in readme
    assert "refs/heads/master/bootstrap.sh" not in readme
def test_troubleshooting_mentions_model_path_resolution() -> None:
    text = (ROOT / "TROUBLESHOOTING.md").read_text(encoding="utf-8")
    assert "/model" in text
    assert "command -v codex" in text
    assert "deepseek-thinking" in text

def test_installer_passes_model_catalog_to_both_codex_profiles() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")

    deepseek = re.search(
        r'install-codex-profile \\\n'
        r'\s+--name deepseek \\\n'
        r'(?P<body>.*?)(?=\n\n\s+run_quiet "Codex profile installed: deepseek-thinking")',
        text,
        re.DOTALL,
    )
    assert deepseek is not None
    assert '"${MODEL_CATALOG_ARGS[@]}"' in deepseek.group("body")

    thinking = re.search(
        r'install-codex-profile \\\n'
        r'\s+--name deepseek-thinking \\\n'
        r'(?P<body>.*?)(?=\nfi\n\nwrite_codex_wrapper)',
        text,
        re.DOTALL,
    )
    assert thinking is not None
    assert '"${MODEL_CATALOG_ARGS[@]}"' in thinking.group("body")

def test_installer_guided_api_provider_catalogs_are_visible() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Configure model API now? [Y/n]" in text
    assert "Configure web search API now? [y/N]" in text
    assert "Configure image generation API now? [y/N]" in text
    assert "DeepSeek" in text
    assert "Kimi / Moonshot" in text
    assert "Mimo" in text
    assert "Qwen" in text
    assert "SerpAPI" in text
    assert "Tavily" in text
    assert "ZhipuAI / BigModel" in text
    assert "Qwen Image" in text
    assert "Unsupported" in text
    assert "dsproxy config wizard" in text

def test_installer_guided_api_provider_catalogs_include_new_providers_and_other() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Tavily" in text
    assert "Brave Search" in text
    assert "Qwen Image / DashScope" in text
    assert "Other custom server" in text
    assert "docs/custom_api_handoff.md" in text
    assert "serpapi|tavily|brave" in text
    assert "zhipu|zai|qwen_image" in text

def test_custom_api_handoff_doc_exists() -> None:
    handoff = INSTALL_SH.parent.parent / "docs" / "custom_api_handoff.md"
    text = handoff.read_text(encoding="utf-8")
    assert "Custom API handoff" in text
    assert "Web search tool bridge" in text
    assert "Image generation tool bridge" in text
    assert "deepseek_responses_proxy/app.py" in text
    assert "Do not create public Release tags unless the user explicitly asks." in text

def test_installer_guided_api_provider_catalogs_include_second_wave_providers() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Exa" in text
    assert "Firecrawl" in text
    assert "Stability AI" in text
    assert "fal.ai" in text
    assert "serpapi|tavily|brave|exa|firecrawl" in text
    assert "zhipu|zai|qwen_image|stability|fal" in text


def test_installer_validates_web_and_image_provider_keys_before_saving() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "test_web_search_api_key()" in text
    assert "test_image_generation_api_key()" in text
    assert "Web search API key validated for provider" in text
    assert "Image generation API key accepted by non-generating validation for provider" in text
    assert "This does not prove real image generation works" in text
    assert "Web search API key was not saved because validation failed" in text
    assert "Image generation API key was not saved because validation failed" in text
    assert "DeepSeek API key was not saved because validation failed" in text


def test_installer_image_validation_requires_error_body_for_non_generation_probes() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "PYCODEEPSEEDEX_INSTALL_IMAGE_VALIDATION_P28A3" in text
    assert "has_provider_error_body" in text
    assert "(400, 422), True" in text
    assert "non-generating validation" in text
    assert "api.stability.ai/v1/user/balance" in text
    assert "api.fal.ai/v1/models" in text

def test_installer_non_interactive_image_provider_defaults_to_zhipu() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-zhipu}"' in text
    assert 'PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-glm}"' not in text




def test_installer_backs_up_local_files_before_refreshing_wrappers_and_config() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'LOCAL_BACKUP_DIR="${DEEPSEEK_PROXY_BACKUP_DIR:-/tmp/codeepseedex-install-backups-$(date +%Y%m%d_%H%M%S)}"' in text
    assert "backup_local_file_before_overwrite()" in text
    assert 'backup_local_file_before_overwrite "$ENV_FILE" "local env file"' in text
    assert 'backup_local_file_before_overwrite "$BIN_DIR/dsproxy" "dsproxy command wrapper"' in text
    assert 'backup_local_file_before_overwrite "$wrapper_path" "codex command wrapper"' in text
    assert 'backup_local_file_before_overwrite "$HOME/.codex/config.toml" "Codex config"' in text
    assert 'write_dsproxy_wrapper' in text
    assert 'write_codex_wrapper "$STABLE_PORT" "$THINKING_PORT"' in text


def test_codex_wrapper_prefers_public_dsproxy_and_tolerates_start_drift() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'DSPROXY="\\${CODEEPSEEDEX_DSPROXY:-$BIN_DIR/dsproxy}"' in text
    assert 'if [ ! -x "\\$DSPROXY" ] && [ -x "$INSTALL_DIR/.venv/bin/dsproxy" ]; then' in text
    assert 'DSPROXY="$INSTALL_DIR/.venv/bin/dsproxy"' in text
    assert 'start_dsproxy_profile()' in text
    assert '"\\$DSPROXY" start >/dev/null 2>&1 || "\\$DSPROXY" status >/dev/null 2>&1 || true' in text
    assert '"\\$DSPROXY" start thinking >/dev/null 2>&1 || "\\$DSPROXY" status thinking >/dev/null 2>&1 || true' in text
    assert 'exec "\\$REAL_CODEX" "\\$@"' in text


def test_installer_guided_model_provider_catalogs_include_openai_compatible_options() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'provider_option_line "1" "DeepSeek" "supported"' in text
    assert 'provider_option_line "2" "Kimi / Moonshot" "supported"' in text
    assert 'provider_option_line "3" "GLM / Z.AI" "supported"' in text
    assert 'provider_option_line "4" "Qwen / DashScope" "supported"' in text
    assert 'provider_option_line "5" "Mimo" "custom endpoint required"' in text
    assert 'provider_option_line "6" "Baichuan" "custom endpoint required"' in text
    assert "https://api.moonshot.ai/v1" in text
    assert "https://api.z.ai/api/paas/v4" in text
    assert "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" in text
    assert "DEEPSEEK_BASE_URL" in text
    assert "DEEPSEEK_PROXY_MODEL_PROVIDER" in text
    assert "PYCODEEPSEEDEX_INSTALL_MODEL_API_VALIDATION_P28A4" in text
    assert "dsproxy config set-api-key --provider deepseek|kimi|glm|qwen|custom" in text
