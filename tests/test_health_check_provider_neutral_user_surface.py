from pathlib import Path


SCRIPT = Path("health_check.sh").read_text(encoding="utf-8")


def test_health_check_uses_codexchange_provider_neutral_labels() -> None:
    forbidden = [
        "ds_proxy_health_text",
        "ds_proxy_health_stream",
        "DeepSeek balance",
        "All proxy HTTP health checks passed.",
    ]

    for phrase in forbidden:
        assert phrase not in SCRIPT

    assert "cox_health_text" in SCRIPT
    assert "cox_health_stream" in SCRIPT
    assert "All CodeXchange HTTP health checks passed." in SCRIPT
    assert "== provider balance ==" in SCRIPT


def test_health_check_supports_provider_model_and_balance_overrides() -> None:
    assert 'HEALTH_MODEL="${HEALTH_MODEL:-${MODEL:-deepseek-v4-flash}}"' in SCRIPT
    assert 'CHECK_PROVIDER_BALANCE="${CHECK_PROVIDER_BALANCE:-${CHECK_DEEPSEEK_BALANCE:-0}}"' in SCRIPT
    assert 'os.environ["HEALTH_MODEL"]' in SCRIPT
    assert 'if [ "$CHECK_PROVIDER_BALANCE" = "1" ]; then' in SCRIPT


def test_health_check_keeps_legacy_balance_env_only_as_compatibility_fallback() -> None:
    assert SCRIPT.count("CHECK_DEEPSEEK_BALANCE") == 1
    assert "DeepSeek balance" not in SCRIPT
