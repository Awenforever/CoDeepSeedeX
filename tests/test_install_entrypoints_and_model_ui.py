from __future__ import annotations

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[1]
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
    assert "test_image_api_key()" in text or "test_image_generation_api_key()" in text
    assert "Web search API key validated for provider" in text
    assert "Image generation API key accepted by non-generating validation for provider" in text
    assert "Received ${#candidate} characters" in text
    assert "Press Enter three times to skip" in text
    assert "Web search API key was not saved because validation failed" in text
    assert "Image generation API key was not saved because validation failed" in text

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
    assert "menu_render_option_line()" in text
    assert "menu_truncate_line()" in text
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to go back." in text
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
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to go back." in menu_func


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
    assert "menu_back_value()" in text
    assert "Use ↑/↓ or j/k to move, Enter to select, Backspace to go back." in text
    assert "Press a listed number for a quick choice" not in text
    assert "Type a number/text for fallback" not in text
    assert "menu_value_exists()" not in text
    assert "[0-9])" not in text
    assert "[0-9A-Za-z_./:-])" not in text
    assert "$'\\x7f'|$'\\b')" in text
    assert "\\033[7;1m%s\\033[0m" in text
    assert "menu_print_separator" in text



def test_installer_port_prompts_use_dim_default_hint() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'read_from_tty "Stable proxy port" "$DEFAULT_STABLE_PORT"' in text
    assert 'read_from_tty "Thinking proxy port" "$DEFAULT_THINKING_PORT"' in text
    assert "press Enter to keep default" not in text
    assert "\\033[2m[Enter keeps %s]\\033[0m: " in text


def test_installer_logo_colors_version() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert "CoDeepSeedeX \\033[1;35m%s\\033[0m" in text


def test_installer_menu_selected_and_unselected_value_columns_align() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert 'local prefix="  "' in text
    assert 'prefix="▶ "' in text
    assert "row=\"$(printf " in text
    assert "%s%s. %s  %s" in text
    assert "\"$prefix\" \"$value\" \"$label\" \"$suffix\")" in text
