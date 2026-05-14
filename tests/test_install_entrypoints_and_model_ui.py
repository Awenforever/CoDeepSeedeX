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
    assert "Configure model API now?" in text
    assert "Configure web search API now?" in text
    assert "Configure image generation API now?" in text
    assert "DeepSeek" in text
    assert "Kimi / Moonshot" in text
    assert "Zhipu / BigModel domestic general" in text
    assert "Zhipu / BigModel domestic Coding Plan" in text
    assert "Z.AI international general" in text
    assert "Z.AI international Coding Plan" in text
    assert "Qwen / DashScope Beijing pay-as-you-go" in text
    assert "Qwen / DashScope Singapore pay-as-you-go" in text
    assert "Qwen / DashScope US Virginia pay-as-you-go" in text
    assert "Mimo" not in text
    assert "Baichuan" not in text
    assert "GLM / Z.AI" not in text
    assert 'provider_option_line "4" "Qwen / DashScope" "supported"' not in text
    assert "SerpAPI" in text
    assert "Tavily" in text
    assert "Exa" in text
    assert "Firecrawl" in text
    assert "Brave" not in text

def test_installer_guided_api_provider_catalogs_include_new_providers_and_other() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Tavily" in text
    assert "Brave Search" not in text
    assert "Qwen Image / DashScope" in text
    assert "Other custom server" in text
    assert "set-image-api-key" in text
    assert "zhipu" in text
    assert "zai" in text
    assert "serpapi|tavily|exa|firecrawl" in text
    assert "zhipu|zai|qwen_image" in text

def test_developer_handbook_provider_handoff_exists() -> None:
    handbook = INSTALL_SH.parent.parent / "docs" / "developer-handbook.md"
    text = handbook.read_text(encoding="utf-8")
    assert "Provider and custom API handoff" in text
    assert "Web search tool bridge" in text
    assert "Image generation tool bridge" in text
    assert "dsproxy doctor providers --live --allow-spend" in text
    assert "deepseek_responses_proxy/app.py" in text

def test_installer_guided_api_provider_catalogs_include_second_wave_providers() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Exa" in text
    assert "Firecrawl" in text
    assert "Stability AI" in text
    assert "fal.ai" in text
    assert "serpapi|tavily|exa|firecrawl" in text
    assert "zhipu|zai|qwen_image_beijing|qwen_image_singapore|stability|fal" in text


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





def _install_function_body(function_name: str, next_function_name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    start_marker = f"{function_name}() {{"
    end_marker = f"{next_function_name}() {{"
    start = text.index(start_marker)
    end = text.index(end_marker, start + len(start_marker))
    return text[start:end]


def test_installer_codex_unknown_backup_happens_only_after_ownership_gate() -> None:
    body = _install_function_body("write_codex_wrapper", "uninstall")
    gate = body.index('require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER" || return 1')
    move = body.index('mv "$wrapper_path" "$backup_path"')
    write = body.index('cat > "$wrapper_path" <<EOF')
    empty_real_check = body.index('if [ -z "$real_codex" ]; then')
    assert gate < move < empty_real_check < write
    assert 'existing_wrapper_is_unknown="1"' in body
    assert 'grep -q "CoDeepSeedeX codex wrapper"' not in body
    assert 'backup existing %q to %q\\n' not in body[:gate]


def test_installer_dsproxy_overwrite_gate_blocks_wrapper_write() -> None:
    body = _install_function_body("write_dsproxy_wrapper", "write_codex_wrapper")
    gate = body.index('require_safe_local_bin_overwrite "$BIN_DIR/dsproxy" "dsproxy command wrapper" "dsproxy" "$FORCE_DSPROXY_WRAPPER" || return 1')
    write = body.index('cat > "$BIN_DIR/dsproxy" <<EOF')
    assert gate < write


def test_installer_gates_unknown_local_bin_overwrites() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'FORCE_CODEX_WRAPPER="${DEEPSEEK_PROXY_FORCE_CODEX_WRAPPER:-0}"' in text
    assert 'FORCE_DSPROXY_WRAPPER="${DEEPSEEK_PROXY_FORCE_DSPROXY_WRAPPER:-0}"' in text
    assert "is_codeepseedex_managed_local_bin()" in text
    assert "require_safe_local_bin_overwrite()" in text
    assert 'require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER" || return 1' in text
    assert 'require_safe_local_bin_overwrite "$BIN_DIR/dsproxy" "dsproxy command wrapper" "dsproxy" "$FORCE_DSPROXY_WRAPPER" || return 1' in text
    assert "Refusing to overwrite unknown existing $label in non-interactive mode" in text
    assert "DEEPSEEK_PROXY_FORCE_CODEX_WRAPPER=1" in text
    assert "DEEPSEEK_PROXY_FORCE_DSPROXY_WRAPPER=1" in text


def test_installer_recognizes_only_codeepseedex_managed_local_bins() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "CoDeepSeedeX codex wrapper|CODEEPSEEDEX_DSPROXY|deepseek-responses-proxy|start_dsproxy_profile" in text
    assert "CoDeepSeedeX|deepseek-responses-proxy|\\.venv/bin/dsproxy" in text
    assert 'backup_local_file_before_overwrite "$ENV_FILE" "local env file"' in text
    assert 'backup_local_file_before_overwrite "$HOME/.codex/config.toml" "Codex config"' in text


def test_installer_sync_checkout_logging_uses_defined_shell_command() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'log "Synchronizing installed checkout to ref: $requested_ref"' not in text
    assert "printf '+ Synchronizing installed checkout to ref: %s\\n'" in text


def test_installer_syncs_installed_checkout_before_editable_install() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "sync_install_checkout_to_ref()" in text
    assert 'git fetch --tags origin' in text
    assert 'installed-checkout-dirty-$(date +%Y%m%d_%H%M%S).patch' in text
    assert 'installed-checkout-untracked-$(date +%Y%m%d_%H%M%S).tar.gz' in text
    assert 'git checkout -B "$requested_ref" "origin/$requested_ref"' in text
    assert 'git checkout -f "$requested_ref"' in text
    assert 'sync_install_checkout_to_ref "$INSTALL_TARGET_REF"' in text
    assert text.index('sync_install_checkout_to_ref "$INSTALL_TARGET_REF"') > text.index('INSTALL_TARGET_REF="$(resolve_install_ref)"')
    assert text.index('sync_install_checkout_to_ref "$INSTALL_TARGET_REF"') < text.index('run_quiet "Virtual environment ready"')
    assert "Installation cannot refresh package code." in text


def test_installer_backs_up_local_files_before_refreshing_wrappers_and_config() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'LOCAL_BACKUP_DIR="${DEEPSEEK_PROXY_BACKUP_DIR:-/tmp/codeepseedex-install-backups-$(date +%Y%m%d_%H%M%S)}"' in text
    assert "backup_local_file_before_overwrite()" in text
    assert 'backup_local_file_before_overwrite "$ENV_FILE" "local env file"' in text
    assert 'require_safe_local_bin_overwrite "$BIN_DIR/dsproxy" "dsproxy command wrapper" "dsproxy" "$FORCE_DSPROXY_WRAPPER" || return 1' in text
    assert 'require_safe_local_bin_overwrite "$wrapper_path" "codex command wrapper" "codex" "$FORCE_CODEX_WRAPPER" || return 1' in text
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
    assert 'read_menu_choice_from_tty "Select model provider" "1"' in text
    assert '"1|DeepSeek|supported"' in text
    assert '"2|Kimi / Moonshot|supported"' in text
    assert '"3|Zhipu / BigModel domestic general|supported"' in text
    assert '"4|Zhipu / BigModel domestic Coding Plan|supported"' in text
    assert '"5|Z.AI international general|supported"' in text
    assert '"6|Z.AI international Coding Plan|supported"' in text
    assert '"7|Qwen / DashScope Beijing pay-as-you-go|supported"' in text
    assert '"8|Qwen / DashScope Singapore pay-as-you-go|supported"' in text
    assert '"9|Qwen / DashScope US Virginia pay-as-you-go|supported"' in text
    assert '"10|Other OpenAI-compatible server|custom"' in text

def test_installer_codex_wrapper_sets_random_terminal_title_for_deepseek_profiles() -> None:
    body = _install_function_body("write_codex_wrapper", "uninstall")
    assert "set_codeepseedex_terminal_title()" in body
    assert 'local emojis=("✨" "💞" "🐦‍🔥" "🔥" "❄️" "💫" "🌈" "⚡" "🌀" "🚀" "🍁" "🍒" "🧬" "🪄" "💎" "🦞" "🐋" "😻")' in body
    assert r'local title="\${emojis[\$idx]}CoDeepSeedeX"' in body
    assert "printf '\\033]0;%s\\007' \"\\$title\" 2>/dev/null || true" in body
    title_function_idx = body.index("set_codeepseedex_terminal_title()")
    start_function_idx = body.index("start_dsproxy_profile()")
    title_call_idx = body.index("set_codeepseedex_terminal_title", start_function_idx)
    start_call_idx = body.index(r'start_dsproxy_profile "\$profile"', title_call_idx)
    exec_idx = body.index(r'exec "\$REAL_CODEX" "\$@"')
    assert title_function_idx < start_function_idx
    assert title_call_idx < start_call_idx < exec_idx


def test_installer_guided_provider_menus_use_arrow_selector() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "read_menu_choice_from_tty()" in text
    assert "read_yes_no_menu()" in text
    assert "Use ↑/↓ or j/k, Enter to select" in text
    assert 'provider="$(read_menu_choice_from_tty "Select model provider" "1"' in text
    assert 'provider="$(read_menu_choice_from_tty "Select web search provider" "1"' in text
    assert 'provider="$(read_menu_choice_from_tty "Select image generation provider" "1"' in text
    assert "CODEEPSEEDEX_NO_ARROW_MENUS" in text
    assert "qwen_image_beijing|qwen-image-beijing" in text
    assert "qwen_image_singapore|qwen-image-singapore" in text
