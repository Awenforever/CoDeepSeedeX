from pathlib import Path

APP_SOURCE = Path("codexchange_proxy/app.py").read_text(encoding="utf-8")


def test_remote_compact_guard_action_wording_is_provider_neutral() -> None:
    assert "unsupported_remote_compaction_for_deepseek_proxy" not in APP_SOURCE
    assert "provider-routed third-party route" in APP_SOURCE
    assert (
        "report unsupported remote compaction for the provider-routed third-party route "
        "and audit provider capability drift"
    ) in APP_SOURCE
