from __future__ import annotations

from pathlib import Path
import re
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "scripts" / "install.sh"


def test_install_output_uses_absolute_uninstall_command() -> None:
    text = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert 'bash %s --uninstall' in text
    assert '"$INSTALL_DIR/scripts/install.sh"' in text




def test_readmes_document_product_uninstall_entrypoint_and_scope() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
    combined = readme + "\n" + readme_zh

    assert "## Uninstall" in readme
    assert "## 卸载" in readme_zh
    assert "installer, not `dsproxy uninstall`" in readme
    assert "安装器，不是`dsproxy uninstall`" in readme_zh
    assert "bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall" in combined
    assert "bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall --remove-files" in combined
    assert "deepseek-thinking" in combined
    assert "restores the previous `codex` command backup" in readme
    assert "恢复旧`codex`命令" in readme_zh
    assert "removes the `dsproxy` wrapper" in readme
    assert "移除CoDeepSeedeX安装的`dsproxy` wrapper" in readme_zh
    assert "~/.local/share/deepseek-responses-proxy" in combined
    assert "env file" in readme
    assert "env文件" in readme_zh
    assert "must not delete unrelated user files" in readme
    assert "不得删除无关用户文件" in readme_zh


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
    assert "ZhipuAI / BigModel" in text
    assert "Z.AI" in text
    assert "Qwen / DashScope" in text
    assert "Mimo|unsupported" in text
    assert "Baichuan|unsupported" in text
    assert "Select ZhipuAI / BigModel endpoint" in text
    assert "Domestic Token API / general endpoint" in text
    assert "Domestic Coding Plan API endpoint" in text
    assert "Select Z.AI endpoint" in text
    assert "International Token API / general endpoint" in text
    assert "International Coding Plan API endpoint" in text
    assert "Select Qwen / DashScope endpoint" in text
    assert "Beijing pay-as-you-go OpenAI-compatible endpoint" in text
    assert "Singapore pay-as-you-go OpenAI-compatible endpoint" in text
    assert "US Virginia pay-as-you-go OpenAI-compatible endpoint" in text
    assert "SerpAPI" in text
    assert "Tavily" in text
    assert "Exa" in text
    assert "Firecrawl" in text
    assert "ZhipuAI / BigModel image API key" in text
    assert "Z.AI image API key" in text
    assert "Select Qwen Image / DashScope region" in text
    assert "Stability AI" in text
    assert "fal.ai" in text

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
    assert "test_image_api_key() {" in text
    assert "if test_image_api_key \"$PROMPTED_IMAGE_PROVIDER\" \"$candidate\"; then" in text
    assert "Web search API key validated for provider" in text
    assert "Image generation API key validated by live image generation for provider" in text
    assert "Received ${#candidate} characters" in text
    assert "Press Enter three times to skip" in text
    assert "Web search API key was not saved because validation failed" in text
    assert "Image generation API key was not saved because live validation failed" in text

def test_installer_image_validation_is_live_generation_not_non_generation_probe() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "PYCODEEPSEEDEX_INSTALL_LIVE_IMAGE_VALIDATION_P210A24" in text
    assert "A breathtaking glamorous adult anime-style woman" in text
    assert "safe for work, fully clothed, no nudity" in text
    assert "Live image validation workspace:" in text
    assert "test image saved:" in text
    assert ("PYCODEEPSEEDEX_INSTALL_IMAGE_VALIDATION_" + "P28A3") not in text
    assert ("non-" + "generating validation") not in text

def test_installer_non_interactive_image_provider_defaults_to_zhipu() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'PROMPTED_IMAGE_PROVIDER="$(env_file_value DEEPSEEK_PROXY_IMAGE_PROVIDER)"' in text
    assert 'PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-zhipu}"' in text
    assert 'PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-glm}"' not in text


def test_installer_non_interactive_preserves_existing_model_provider_env() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    model_prompt = text[text.index("prompt_deepseek_api_key() {"):text.index("local configure=", text.index("prompt_deepseek_api_key() {"))]
    assert 'PROMPTED_MODEL_PROVIDER="$(env_file_value DEEPSEEK_PROXY_MODEL_PROVIDER)"' in model_prompt
    assert 'PROMPTED_MODEL_PROVIDER="${DEEPSEEK_PROXY_MODEL_PROVIDER:-}"' in model_prompt
    assert model_prompt.index('PROMPTED_MODEL_PROVIDER="$(env_file_value DEEPSEEK_PROXY_MODEL_PROVIDER)"') < model_prompt.index('PROMPTED_MODEL_PROVIDER="${DEEPSEEK_PROXY_MODEL_PROVIDER:-}"')
    assert 'PROMPTED_MODEL_BASE_URL="$(env_file_value DEEPSEEK_BASE_URL)"' in model_prompt
    assert 'PROMPTED_MODEL_BASE_URL="${DEEPSEEK_BASE_URL:-}"' in model_prompt
    assert model_prompt.index('PROMPTED_MODEL_BASE_URL="$(env_file_value DEEPSEEK_BASE_URL)"') < model_prompt.index('PROMPTED_MODEL_BASE_URL="${DEEPSEEK_BASE_URL:-}"')
    assert 'PROMPTED_MODEL_NAME="$(env_file_value DEEPSEEK_PROXY_MODEL)"' in model_prompt
    assert 'PROMPTED_MODEL_NAME="${DEEPSEEK_PROXY_MODEL:-}"' in model_prompt
    assert model_prompt.index('PROMPTED_MODEL_NAME="$(env_file_value DEEPSEEK_PROXY_MODEL)"') < model_prompt.index('PROMPTED_MODEL_NAME="${DEEPSEEK_PROXY_MODEL:-}"')
    assert 'RESOLVED_MODEL_PROVIDER="$final_model_provider"' in text
    assert 'RESOLVED_MODEL_NAME="$final_model_name"' in text
    assert 'if [ -n "${RESOLVED_MODEL_NAME:-}" ] && [ "${RESOLVED_MODEL_PROVIDER:-deepseek}" != "deepseek" ]; then' in text
    assert '--model "$PROFILE_THINKING_MODEL"' in text


def test_installer_non_interactive_prefers_target_env_file_over_ambient_shell_env() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    model_prompt = text[text.index("prompt_deepseek_api_key() {"):text.index("local configure=", text.index("prompt_deepseek_api_key() {"))]
    assert "Existing installer env file is the migration source of truth" in model_prompt
    assert model_prompt.index('PROMPTED_API_KEY="$(env_file_value DEEPSEEK_API_KEY)"') < model_prompt.index('PROMPTED_API_KEY="${DEEPSEEK_API_KEY:-}"')

    web_prompt = text[text.index("prompt_serpapi_api_key() {"):text.index("local configure=", text.index("prompt_serpapi_api_key() {"))]
    assert 'PROMPTED_WEB_SEARCH_PROVIDER="$(env_file_value DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER)"' in web_prompt
    assert 'PROMPTED_WEB_SEARCH_PROVIDER="${DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER:-serpapi}"' in web_prompt
    assert web_prompt.index('PROMPTED_WEB_SEARCH_PROVIDER="$(env_file_value DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER)"') < web_prompt.index('PROMPTED_WEB_SEARCH_PROVIDER="${DEEPSEEK_PROXY_WEB_SEARCH_PROVIDER:-serpapi}"')
    assert 'PROMPTED_SERPAPI_API_KEY="$(env_file_value TAVILY_API_KEY)"' in web_prompt

    image_prompt = text[text.index("prompt_image_generation_api_key() {"):text.index("local configure=", text.index("prompt_image_generation_api_key() {"))]
    assert 'PROMPTED_IMAGE_PROVIDER="$(env_file_value DEEPSEEK_PROXY_IMAGE_PROVIDER)"' in image_prompt
    assert 'PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-zhipu}"' in image_prompt
    assert image_prompt.index('PROMPTED_IMAGE_PROVIDER="$(env_file_value DEEPSEEK_PROXY_IMAGE_PROVIDER)"') < image_prompt.index('PROMPTED_IMAGE_PROVIDER="${DEEPSEEK_PROXY_IMAGE_PROVIDER:-zhipu}"')
    assert 'PROMPTED_IMAGE_API_KEY="$(env_file_value DEEPSEEK_PROXY_IMAGE_API_KEY)"' in image_prompt





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




def test_installer_codex_wrapper_repairs_managed_profile_before_launch() -> None:
    body = _install_function_body("write_codex_wrapper", "uninstall")
    assert "repair_codeepseedex_managed_profile_contract()" in body
    assert "profile repair --managed-only --json" in body
    assert r'profile status "\$profile_name" --json' in body
    assert "CODEEPSEEDEX_ALLOW_PROFILE_MODEL_CONFLICT" in body
    assert "Refusing to launch Codex with a stale or incompatible profile" in body
    repair_idx = body.index(r'repair_codeepseedex_managed_profile_contract "\$profile"')
    start_idx = body.index(r'start_dsproxy_profile "\$profile"')
    real_idx = body.index(r'"\$REAL_CODEX" "\$@"')
    assert repair_idx < start_idx < real_idx

def test_installer_recognizes_only_codeepseedex_managed_local_bins() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "CoDeepSeedeX codex wrapper|CODEEPSEEDEX_DSPROXY|deepseek-responses-proxy|start_dsproxy_profile" in text
    assert "CoDeepSeedeX|deepseek-responses-proxy|\\.venv/bin/dsproxy" in text
    assert 'backup_local_file_before_overwrite "$ENV_FILE" "local env file"' in text
    assert 'backup_local_file_before_overwrite "$HOME/.codex/config.toml" "Codex main config"' in text


def test_installer_sync_checkout_logging_uses_defined_shell_command() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'log "Synchronizing installed checkout to ref: $requested_ref"' not in text
    assert "printf '+ Synchronizing installed checkout to ref: %s\\n'" in text


def test_installer_syncs_installed_checkout_before_editable_install() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "sync_install_checkout_to_ref()" in text
    assert "git fetch --tags --force origin" in text
    assert "git fetch --tags origin" not in text
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
    assert 'backup_local_file_before_overwrite "$HOME/.codex/config.toml" "Codex main config"' in text
    assert 'write_dsproxy_wrapper' in text
    assert 'write_codex_wrapper "$STABLE_PORT" "$THINKING_PORT"' in text


def test_codex_wrapper_prefers_public_dsproxy_and_fails_closed_on_unhealthy_proxy() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    body = _install_function_body("write_codex_wrapper", "uninstall")

    start_idx = body.index("start_dsproxy_profile() {")
    run_idx = body.index("run_codeepseedex_codex() {", start_idx)
    start_fn = body[start_idx:run_idx]
    run_end_idx = body.index("\n}\n\ntrap", run_idx) + len("\n}")
    run_fn = body[run_idx:run_end_idx]

    assert "CODEEPSEEDEX_DSPROXY" in body
    assert "DSPROXY=" in body
    assert 'if [ ! -x "\\$DSPROXY" ]' in body
    assert 'start_args=(start)' in start_fn
    assert 'start_args=(start thinking)' in start_fn
    assert 'status_args=(status)' in start_fn
    assert 'status_args=(status thinking)' in start_fn
    assert '"\\$DSPROXY" "\\${start_args[@]}" >/dev/null 2>&1' in start_fn
    assert '"\\$DSPROXY" "\\${status_args[@]}" >/dev/null 2>&1' in start_fn
    assert "|| true" not in start_fn

    assert r'case "\$profile" in' in run_fn
    assert r'start_dsproxy_profile "\$profile"' in run_fn
    assert "schedule_codeepseedex_terminal_title_refresh" in run_fn
    assert r'"\$REAL_CODEX" "\$@"' in run_fn
    assert r'exec "\$REAL_CODEX" "\$@"' not in body
    assert "stop_codeepseedex_terminal_title_keeper" in run_fn
    assert r'return "\$codex_rc"' in run_fn
    assert "trap 'stop_codeepseedex_terminal_title_keeper' INT TERM HUP" in body


def test_installer_uninstall_restores_previous_codex_command_from_manifest_backup() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    install_body = _install_function_body("write_codex_wrapper", "uninstall")
    uninstall_start = text.index("uninstall() {")
    uninstall_body = text[uninstall_start:]
    assert 'CODEX_WRAPPER_BACKUP="$backup_path"' in install_body
    assert 'backup_path="${CODEX_WRAPPER_BACKUP:-}"' in uninstall_body
    assert 'rm -f "$wrapper_path"' in uninstall_body
    assert 'mv "$backup_path" "$wrapper_path"' in uninstall_body
    assert 'ok "Previous codex command restored"' in uninstall_body
    assert uninstall_body.index('rm -f "$wrapper_path"') < uninstall_body.index('mv "$backup_path" "$wrapper_path"')


def test_installer_documents_codex_plan_effort_alias() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Plan mode reasoning is pinned to high for DeepSeek profiles" in text
    assert 'plan_mode_reasoning_effort = "high"' in text
    assert "Codex may display medium, proxy maps it to DeepSeek high" not in text


def test_installer_guided_model_provider_catalogs_include_openai_compatible_options() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'read_menu_choice_from_tty "Select model provider family" "1"' in text
    assert '"1|DeepSeek|supported"' in text
    assert '"2|Kimi / Moonshot|experimental"' in text
    assert '"3|ZhipuAI / BigModel|experimental"' in text
    assert '"4|Z.AI|experimental"' in text
    assert '"5|Qwen / DashScope|experimental"' in text
    assert '"6|Mimo|unsupported"' in text
    assert '"7|Baichuan|unsupported"' in text
    assert '"8|Other OpenAI-compatible server|custom"' in text
    assert "Select ZhipuAI / BigModel endpoint" in text
    assert "Select Z.AI endpoint" in text
    assert "Select Qwen / DashScope endpoint" in text
    assert "PROMPTED_MODEL_PROVIDER=\"zhipu\"" in text
    assert "PROMPTED_MODEL_PROVIDER=\"zhipu-coding\"" in text
    assert "PROMPTED_MODEL_PROVIDER=\"zai\"" in text
    assert "PROMPTED_MODEL_PROVIDER=\"zai-coding\"" in text
    assert "PROMPTED_MODEL_PROVIDER=\"qwen-beijing\"" in text
    assert "PROMPTED_MODEL_PROVIDER=\"qwen-singapore\"" in text
    assert "PROMPTED_MODEL_PROVIDER=\"qwen-us\"" in text






def test_installer_codex_wrapper_sets_random_terminal_title_for_deepseek_profiles() -> None:
    body = _install_function_body("write_codex_wrapper", "uninstall")
    assert "set_codeepseedex_terminal_title()" in body
    assert "schedule_codeepseedex_terminal_title_refresh()" in body
    assert "CODEEPSEEDEX_TITLE_KEEPER_PID" in body
    assert "stop_codeepseedex_terminal_title_keeper()" in body
    assert 'kill "\\$CODEEPSEEDEX_TITLE_KEEPER_PID" >/dev/null 2>&1 || true' in body
    assert 'wait "\\$CODEEPSEEDEX_TITLE_KEEPER_PID" >/dev/null 2>&1 || true' in body
    assert "run_codeepseedex_codex()" in body
    assert "set +e" in body
    assert "local codex_rc=\\$?" in body
    assert 'return "\\$codex_rc"' in body
    assert "trap 'stop_codeepseedex_terminal_title_keeper' INT TERM HUP" in body
    assert body.count("🐦‍🔥") == 1
    assert 'local emojis=("✨" "💞" "🐦‍🔥" "🔥" "❄️" "💫" "🌈" "⚡" "🌀" "🚀" "🍁" "🍒" "🧬" "🪄" "💎" "🦞" "🐋" "😻")' in body
    assert r'local title="\${CODEEPSEEDEX_TERMINAL_TITLE:-}"' in body
    assert "if [ ! -w /dev/tty ] && [ ! -t 1 ]; then" in body
    assert r'max_seconds="\${CODEEPSEEDEX_TITLE_KEEPER_SECONDS:-60}"' in body
    assert r'interval_seconds="\${CODEEPSEEDEX_TITLE_KEEPER_INTERVAL_SECONDS:-1}"' in body
    assert r'while [ "\$i" -le "\$max_seconds" ]; do' in body
    assert r'sleep "\$interval_seconds"' in body
    assert "sleep 8" not in body
    assert "sleep 4" not in body
    assert "printf '\\033]0;%s\\007\\033]2;%s\\007' \"\\$title\" \"\\$title\" > /dev/tty 2>/dev/null || true" in body
    assert r'exec "\$REAL_CODEX" "\$@"' not in body
    case_idx = body.index(r'case "\$profile" in')
    start_call_idx = body.index(r'start_dsproxy_profile "\$profile"', case_idx)
    schedule_call_idx = body.index("schedule_codeepseedex_terminal_title_refresh", start_call_idx)
    real_codex_idx = body.index(r'"\$REAL_CODEX" "\$@"', schedule_call_idx)
    cleanup_idx = body.index("stop_codeepseedex_terminal_title_keeper", real_codex_idx)
    return_idx = body.index(r'return "\$codex_rc"', cleanup_idx)
    assert start_call_idx < schedule_call_idx < real_codex_idx < cleanup_idx < return_idx


def test_installer_guided_provider_menus_use_arrow_selector() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "read_menu_choice_from_tty()" in text
    assert "read_yes_no_menu()" in text
    assert "menu_render_option_line()" in text
    assert "menu_truncate_line()" in text
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step." in text
    assert 'family="$(read_menu_choice_from_tty "Select model provider family" "1"' in text
    assert 'endpoint="$(read_menu_choice_from_tty "Select Qwen / DashScope endpoint" "1"' in text
    assert 'family="$(read_menu_choice_from_tty "Select image generation provider family" "1"' in text
    assert 'region="$(read_menu_choice_from_tty "Select Qwen Image / DashScope region" "1"' in text
    assert '"Y|$yes_label|plain"' in text
    assert '"Y|$yes_label|supported"' not in text

def test_installer_marks_non_deepseek_model_providers_experimental() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert '"1|DeepSeek|supported"' in text
    assert '"2|Kimi / Moonshot|experimental"' in text
    assert '"3|ZhipuAI / BigModel|experimental"' in text
    assert '"4|Z.AI|experimental"' in text
    assert '"5|Qwen / DashScope|experimental"' in text
    assert '"6|Mimo|unsupported"' in text
    assert '"7|Baichuan|unsupported"' in text
    assert "Only DeepSeek is marked Supported" in text
    assert "Domestic Token API / general endpoint|experimental" in text
    assert "Domestic Coding Plan API endpoint|experimental" in text
    assert "International Token API / general endpoint|experimental" in text
    assert "International Coding Plan API endpoint|experimental" in text
    assert "Beijing pay-as-you-go OpenAI-compatible endpoint|experimental" in text
    assert "Singapore pay-as-you-go OpenAI-compatible endpoint|experimental" in text
    assert "US Virginia pay-as-you-go OpenAI-compatible endpoint|experimental" in text

def test_bootstrap_install_ref_uses_release_asset_installer_url(tmp_path) -> None:
    bootstrap = REPO_ROOT / "bootstrap.sh"
    text = bootstrap.read_text(encoding="utf-8")
    assert "--install-ref)" in text
    assert "https://github.com/Awenforever/CoDeepSeedeX/releases/download/${fallback_ref}/install.sh" in text
    assert "DEEPSEEK_PROXY_INSTALLER_SOURCE" in text
    assert "installer source:" in text
    assert "requested install ref:" in text

    result = subprocess.run(
        ["bash", str(bootstrap), "--dry-run", "--install-ref", "v0.3.8-alpha", "--", "--non-interactive"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=60,
        check=True,
    )
    output = result.stdout + result.stderr
    assert "would download install.sh from https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.3.8-alpha/install.sh" in output
    assert "would pass DEEPSEEK_PROXY_INSTALL_REF=v0.3.8-alpha" in output
    assert "would pass DEEPSEEK_PROXY_INSTALLER_SOURCE=https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.3.8-alpha/install.sh" in output


def test_installer_logs_source_without_verbose_visible_source_block() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "show_version_source()" in text
    assert "show_version_source\n\n" not in text
    assert ">> \"$INSTALL_LOG\"" in text
    assert 'sub_title "Version source"' in text


def test_installer_arrow_menu_uses_dev_tty_when_stdout_is_logged() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    start = text.index("read_menu_choice_from_tty() {")
    end = text.index("\nread_yes_no_menu()", start)
    menu_func = text[start:end]

    assert "menu_tty_printf()" in text
    assert "[ ! -r /dev/tty ]" in menu_func
    assert "[ ! -w /dev/tty ]" in menu_func
    assert "[ ! -t 0 ]" not in menu_func
    assert "[ ! -t 1 ]" not in menu_func
    assert "printf \"$@\" > /dev/tty" in text
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step." in menu_func


def test_installer_source_logging_uses_install_log_variable() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert '"$LOG_FILE"' not in text
    assert '"$INSTALL_LOG"' in text
    assert 'printf \'Install ref: %s\\n\'' in text
    assert 'printf \'Installer source: %s\\n\'' in text
    assert 'printf \'Repository source: %s\\n\'' in text


def test_installer_p210a15_provider_flow_and_archive_fallback() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "printf \'  CoDeepSeedeX \\033[1;35m%s\\033[0m\\n\' \"${INSTALL_REF:-GitHub Latest}\"" in text
    assert '"Y|$yes_label|plain"' in text
    assert '"Y|$yes_label|supported"' not in text
    assert "Select model provider family" in text
    assert "Select ZhipuAI / BigModel endpoint" in text
    assert "Select Z.AI endpoint" in text
    assert "Select Qwen / DashScope endpoint" in text
    assert "Mimo|unsupported" in text
    assert "Baichuan|unsupported" in text
    assert "Select image generation provider family" in text
    assert "Select Qwen Image / DashScope region" in text
    assert "Received ${#candidate} characters" in text
    assert "Press Enter three times to skip" in text
    assert "download_source_archive_to_install_dir()" in text
    assert "prepare_install_checkout()" in text
    assert "codeload.github.com/Awenforever/CoDeepSeedeX/tar.gz/refs/tags/$ref" in text
    assert "DEEPSEEK_API_KEY is empty; configure later with: dsproxy config set-model --provider deepseek" not in text


def test_installer_logo_function_renders_without_backtick_substitution(tmp_path) -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "cat <<'CODEEPSEEDEX_INSTALLER_LOGO_ART'" in text
    assert "printf '  CoDeepSeedeX \\033[1;35m%s\\033[0m\\n' \"${INSTALL_REF:-GitHub Latest}\"" in text

    start = text.index("logo() {")
    end = text.index("\nshow_version_source()", start) if "\nshow_version_source()" in text[start:] else text.index("\nrun_quiet()", start)
    logo_func = text[start:end]
    script = tmp_path / "logo-smoke.sh"
    script.write_text(
        "set -euo pipefail\n"
        "INSTALL_REF=v0.3.8-alpha\n"
        f"{logo_func}\n"
        "logo\n",
        encoding="utf-8",
    )
    result = subprocess.run(["bash", str(script)], text=True, capture_output=True, timeout=20, check=True)
    assert "CoDeepSeedeX " in result.stdout
    assert "v0.3.8-alpha" in result.stdout
    assert "\x1b[1;35m" in result.stdout
    assert "Codex × DeepSeek local Responses proxy" in result.stdout



def test_installer_menu_renderer_is_arrow_only_and_backspace_aware() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert text.count("read_menu_choice_from_tty() {") == 1
    assert "menu_terminal_cols()" in text
    assert "menu_truncate_line()" in text
    assert "menu_render_option_line()" in text
    assert "__CODEEPSEEDEX_BACK__" in text
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step." in text
    assert "Press a listed number for a quick choice" not in text
    assert "Type a number/text for fallback" not in text
    assert "menu_value_exists()" not in text
    assert "[0-9])" not in text
    assert "[0-9A-Za-z_./:-])" not in text
    assert "$'\\x7f'|$'\\b')" in text
    assert "\\033[7;1m" not in text
    assert "\\033[1;38;5;75m" in text
    assert "ui_box_line" in text
    assert "ui_box_line_styled()" in text

def test_installer_ports_are_auto_selected_without_prompting() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'choose_available_port "$DEFAULT_STABLE_PORT"' in text
    assert 'choose_available_port "$DEFAULT_THINKING_PORT" "$STABLE_PORT"' in text
    assert 'read_from_tty "Non-Thinking proxy port"' not in text
    assert 'read_from_tty "Thinking proxy port"' not in text
    assert "press Enter to keep default" not in text
    assert "\\033[2m[Enter keeps %s]\\033[0m: " in text


def test_installer_logo_colors_version() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "CoDeepSeedeX \\033[1;35m%s\\033[0m" in text



def test_installer_menu_selected_and_unselected_value_columns_align() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'marker="●"' in text
    assert 'marker="○"' in text
    assert 'row="$(printf '"'"'%s [%s] %s'"'"' "$marker" "$value" "$label")"' in text
    assert 'row="$(printf '"'"'%s [%s] %s  %s'"'"' "$marker" "$value" "$label" "$suffix")"' in text
    assert 'menu_render_option_line "0" "$value" "$label" "$status" "$width"' in text
    assert "menu_truncate_line" in text
    assert "ui_box_line" in text
    assert "menu_step_label_for_prompt()" in text

def test_installer_secret_prompt_keeps_existing_key_without_counting_it_as_new_input() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "read_secret_from_tty()" in text
    assert "__CODEEPSEEDEX_KEEP_EXISTING__" in text
    assert "Existing model API key kept for provider:" in text
    assert "optional, type a new key to replace the existing one" in text
    assert "Model API key (optional; press Enter three times to skip)" not in text
    assert "\\033[2m(%s) [hidden, Enter keeps existing]\\033[0m: " in text
    assert "\\033[2m(%s) [hidden]\\033[0m: " in text
    assert "press Enter to keep existing" not in text


def test_installer_codex_wrapper_prompt_explains_profile_usage() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "After installing, use codex --profile deepseek or codex --profile deepseek-thinking." in text
    assert "The wrapper starts or refreshes the local dsproxy backend automatically." in text




def test_installer_menu_prints_detail_between_prompt_and_global_help() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    help_line = "Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step."
    assert "CODEEPSEEDEX_NEXT_MENU_DETAIL" in text
    assert 'local detail="${CODEEPSEEDEX_NEXT_MENU_DETAIL:-}"' in text
    hint_marker = 'ui_box_line_styled "Hint" "$width" "\\033[2m"'
    assert hint_marker in text
    hint_pos = text.index(hint_marker)
    help_pos = text.index(help_line)
    detail_block = text[hint_pos:help_pos]
    assert "$detail" in detail_block
    assert 'CODEEPSEEDEX_NEXT_MENU_DETAIL=""' in text
    assert hint_pos < help_pos

def test_installer_wrapper_help_not_printed_as_standalone_line() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "CODEEPSEEDEX_NEXT_MENU_DETAIL" in text
    assert "printf '  \\033[2mAfter installing, use codex --profile" not in text


def test_cli_upgrade_reinstalls_deepseek_profile_with_high_effort() -> None:
    text = (ROOT / "deepseek_responses_proxy" / "cli.py").read_text(encoding="utf-8")
    start = text.index('"install_codex_profile_stable"')
    end = text.index('"install_codex_profile_thinking"', start)
    block = text[start:end]
    assert '"--reasoning-effort",' in block
    assert '"high",' in block
    assert '"medium",' not in block


def test_installer_project_like_shell_calls_are_defined() -> None:
    import re

    text = INSTALL_SH.read_text(encoding="utf-8")
    defined = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\(\)\s*\{", text, flags=re.MULTILINE))
    prefixes = ("test_", "prompt_", "read_", "download_", "prepare_", "sync_", "write_", "ensure_", "is_")
    ignored = {"test"}
    missing = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(?:if|while|until)\s+([A-Za-z_][A-Za-z0-9_]*)\b", line)
        if not match:
            continue
        name = match.group(1)
        if name in ignored:
            continue
        if name.startswith(prefixes) and name not in defined:
            missing.append(name)

    assert "test_image_api_key" in defined
    assert not sorted(set(missing))

def test_installer_uses_force_tag_fetch_for_moved_prerelease_tags() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "git fetch --tags --force origin" in text
    assert "git fetch --tags origin" not in text


def test_installer_image_validation_function_is_defined_before_prompt_use() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    definition = text.index("test_image_api_key() {")
    prompt = text.index("prompt_image_generation_api_key() {")
    call = text.index('if test_image_api_key "$PROMPTED_IMAGE_PROVIDER" "$candidate"; then')
    assert definition < prompt < call
    assert "PYCODEEPSEEDEX_INSTALL_LIVE_IMAGE_VALIDATION_P210A24" in text
    assert "Live image validation workspace:" in text
    assert "test image saved:" in text

def test_installer_prints_combined_install_logs() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'BOOTSTRAP_LOG="${DEEPSEEK_PROXY_BOOTSTRAP_LOG:-}"' in text
    assert "print_install_logs() {" in text
    assert 'sub_title "Install logs"' in text
    assert "bootstrap" in text
    assert "install" in text
    assert 'sub_title "Install log"' not in text

def test_installer_image_validation_is_live_and_quota_warning_is_visible() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "Live image validation will generate one safe test image and may consume provider credits." in text
    assert "Choose Skip to avoid unexpected charges." in text
    assert "A breathtaking glamorous adult anime-style woman" in text
    assert "safe for work, fully clothed, no nudity" in text
    assert "Creating one safe test image with provider" in text
    assert "Image generation API key validated by live image generation" in text
    assert "test image saved:" in text
    assert ("Image generation API key accepted by " + "non-" + "generating validation") not in text
    assert "This does not prove real image generation" not in text
    assert "PYCODEEPSEEDEX_INSTALL_LIVE_IMAGE_VALIDATION_P210A24" in text

def test_installer_live_image_validation_supports_primary_providers() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "https://open.bigmodel.cn/api/paas/v4/images/generations" in text
    assert "https://api.z.ai/api/paas/v4/images/generations" in text
    assert "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation" in text
    assert "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation" in text
    assert "https://api.stability.ai/v2beta/stable-image/generate/core" in text
    assert "https://fal.run/fal-ai/fast-sdxl" in text


def test_installer_uses_source_archive_for_existing_non_git_install_dir() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "existing non-git install directory" in text
    assert "download_source_archive_to_install_dir \"$target_ref\"" in text


def test_installer_uses_quiet_pip_commands() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "PIP_DISABLE_PIP_VERSION_CHECK=1" in text
    assert "PIP_PROGRESS_BAR=off" in text
    assert "pip install --quiet --no-input -e" in text



def test_legacy_profile_markers_are_absent_from_production_sources() -> None:
    paths = [
        ROOT / "deepseek_responses_proxy" / "app.py",
        ROOT / "deepseek_responses_proxy" / "cli.py",
        ROOT / "scripts" / "dsproxy-config",
        ROOT / "scripts" / "install.sh",
        ROOT / "README.md",
        ROOT / "README.zh-CN.md",
        ROOT / "docs" / "developer-handbook.md",
        ROOT / "docs" / "developer-handbook.zh-CN.md",
        ROOT / "docs" / "development-log.md",
    ]
    pattern = re.compile(r"\[profiles\.(deepseek|deepseek-thinking)\]|profile = \\\"deepseek")
    offenders = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_cli_wizard_prompt_text_does_not_reintroduce_old_numeric_prompts() -> None:
    text = (ROOT / "deepseek_responses_proxy" / "cli.py").read_text(encoding="utf-8")
    assert "Select model API provider" not in text
    assert "Select image generation provider" not in text
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to previous step." in text

def test_terminal_ui_uses_boxed_install_and_wizard_surfaces() -> None:
    install_text = INSTALL_SH.read_text(encoding="utf-8")
    cli_text = (ROOT / "deepseek_responses_proxy" / "cli.py").read_text(encoding="utf-8")
    assert "ui_terminal_width()" in install_text
    assert "ui_wrap_text()" in install_text
    assert "ui_step_footer()" in install_text
    assert "ui_box_top \"CoDeepSeedeX\"" in install_text
    assert "menu_render_option_line()" in install_text
    assert "\\033[7;1m" not in install_text
    assert "╭─ %s %s╮" not in install_text
    assert "╰" not in install_text
    assert "\\033[K" in install_text
    assert "Step interactive" not in install_text
    assert "_wizard_render_panel(" in cli_text
    assert "_wizard_print_box_line(" in cli_text
    assert "_wizard_render_menu(" in cli_text
    assert "_wizard_yes_no_choice(" in cli_text
    assert "wizard_step = 2" in cli_text
    assert "\\033[K" in cli_text
    assert "textwrap.wrap" in cli_text
    assert "\\033[1;44m" not in cli_text
    assert "Step interactive" not in cli_text
    assert "Step 2/5" in cli_text

def test_terminal_ui_uses_fixed_step_labels_instead_of_interactive_placeholder() -> None:
    install_text = INSTALL_SH.read_text(encoding="utf-8")
    cli_text = (ROOT / "deepseek_responses_proxy" / "cli.py").read_text(encoding="utf-8")
    assert "Step interactive" not in install_text
    assert "Step interactive" not in cli_text
    assert "Step 2/5" in install_text
    assert "Step 5/5" in install_text
    assert "__CODEEPSEEDEX_BACK__" in install_text
    assert "Step 2/5" in cli_text
    assert "\\033[2J\\033[3J\\033[H" in install_text


def test_installer_backspace_returns_previous_step_sentinel() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "printf '%s\\n' \"__CODEEPSEEDEX_BACK__\"" in text
    assert 'WRAPPER_CHOICE" = "__CODEEPSEEDEX_BACK__"' in text
    assert 'guided_step=4' in text
    assert 'return 20' in text



def test_terminal_ui_omits_inner_menu_separators_for_boxed_layout() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    start = text.index("read_menu_choice_from_tty() {")
    end = text.index("\nread_yes_no_menu()", start)
    menu_func = text[start:end]
    assert "ui_box_separator" not in menu_func
    assert "╭" not in menu_func
    assert "╮" not in menu_func
    assert "╰" not in menu_func
    assert "│" not in menu_func
    assert "\\033[2J\\033[3J\\033[H" in menu_func
    assert "\\033[K" in text

def test_installer_language_choice_is_first_user_decision() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "choose_installer_language" in text
    assert "Choose your language / 选择语言" in text
    assert "zh-CN|简体中文" in text
    assert "Step 1/5" in text


def test_installer_backspace_step_loop_is_sete_safe() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "if prompt_image_generation_api_key; then" in text
    assert "step_rc=$?" in text
    assert "__CODEEPSEEDEX_BACK__" in text


def test_installer_excludes_managed_resources_from_git_status() -> None:
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "scripts" / "install.sh").read_text(encoding="utf-8")
    assert "ensure_managed_resources_git_excluded" in text
    assert "git -C \"$INSTALL_DIR\" rev-parse --git-path info/exclude" in text
    assert "resources/" in text
    assert "resources/tokenizers/" in text


def test_installer_latest_release_api_falls_back_to_packaged_public_tag() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'CODEEPSEEDEX_PUBLIC_RELEASE_TAG="${DEEPSEEK_PROXY_LATEST_RELEASE_FALLBACK_TAG:-v0.4.3-alpha}"' in text
    assert "Latest Release API fallback used" in text
    assert "falling back to packaged public release tag" in text
