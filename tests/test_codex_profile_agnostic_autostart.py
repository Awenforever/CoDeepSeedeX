from pathlib import Path


WRAPPER = Path("scripts/codex-wrapper.bash").read_text(encoding="utf-8")


def test_codex_wrapper_has_profile_agnostic_runtime_autostart_contract():
    assert "PROFILE-AGNOSTIC RUNTIME AUTOSTART" in WRAPPER
    assert "__codeepseek_profile_runtime_autostart" not in WRAPPER
    assert "__codeepseedex_profile_runtime_autostart" in WRAPPER
    assert "codex --profile <name>" in WRAPPER
    assert "__codeepseedex_profile_arg" in WRAPPER
    assert "--profile=*" in WRAPPER
    assert "--profile)" in WRAPPER


def test_codex_wrapper_autostarts_only_local_responses_proxy_routes():
    assert "__codeepseedex_provider_base_url" in WRAPPER
    assert "__codeepseedex_local_proxy_port_from_base_url" in WRAPPER
    assert "http://127.0.0.1:*" in WRAPPER
    assert "http://localhost:*" in WRAPPER
    assert "/v1/models" in WRAPPER
    assert "127.0.0.1:${port}/v1/models" in WRAPPER


def test_codex_wrapper_sets_profile_specific_runtime_environment():
    assert 'export DEEPSEEK_PROXY_PORT="$port"' in WRAPPER
    assert 'export DEEPSEEK_PROXY_MODEL="$model"' in WRAPPER
    assert "DEEPSEEK_THINKING=enabled" in WRAPPER
    assert "DEEPSEEK_PROXY_CUSTOM_PROVIDER_NAME" in WRAPPER
    assert "DEEPSEEK_PROXY_INSTALL_DIR" in WRAPPER


def test_codex_wrapper_fail_closed_before_native_codex_on_unhealthy_local_port():
    assert "refusing to enter Codex" in WRAPPER
    assert (
        '__codeepseedex_profile_runtime_autostart "$@" || return $?' in WRAPPER
        or '__codeepseedex_profile_runtime_autostart "$@" || exit $?' in WRAPPER
    )
    assert not WRAPPER.rstrip().endswith('__codeepseedex_profile_runtime_autostart "$@" || exit $?')


def test_codex_wrapper_is_also_valid_executable_dispatcher():
    assert "EXECUTABLE WRAPPER DISPATCHER" in WRAPPER
    assert "__codeepseedex_resolve_real_codex" in WRAPPER
    assert "__codeepseedex_executable_wrapper_main" in WRAPPER
    assert 'if [ "${BASH_SOURCE[0]}" = "$0" ]; then' in WRAPPER
    assert 'exec "$__codeepseedex_real_codex" "$@"' in WRAPPER
    assert 'type -P -a codex' in WRAPPER
    assert "CODEEPSEEDEX_REAL_CODEX" in WRAPPER


def test_codex_executable_dispatcher_runs_autostart_before_native_exec():
    autostart = WRAPPER.index('__codeepseedex_profile_runtime_autostart "$@" || exit $?')
    native_exec = WRAPPER.index('exec "$__codeepseedex_real_codex" "$@"')
    assert autostart < native_exec


def test_codex_native_resolver_scans_npm_and_has_nonrecursive_fallback():
    assert "__codeepseedex_emit_executable_if_not_self" in WRAPPER
    assert "__codeepseedex_emit_npm_codex_bin" in WRAPPER
    assert "npm root -g" in WRAPPER
    assert "@openai/codex" in WRAPPER
    assert "npm exec --offline --package @openai/codex" in WRAPPER
    assert "npx --yes @openai/codex" in WRAPPER
    assert '"$HOME/.local/bin/codex") return 1 ;;' in WRAPPER
