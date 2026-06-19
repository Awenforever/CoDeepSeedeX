from __future__ import annotations

import pytest

from codexchange_proxy import cli


def test_config_set_effort_contract_uses_provider_neutral_compatibility_note():
    contract = cli._reasoning_effort_contract("medium")

    assert contract is not None
    note = str(contract["compatibility_note"])

    assert "DeepSeek" not in note
    assert "CodeXchange high" in note
    assert "CodeXchange max" in note
    assert "Codex profile stores xhigh" in note


def test_config_set_effort_help_uses_provider_neutral_compatibility_wording(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(["config", "set-effort", "--help"])

    assert raised.value.code == 0
    help_text = capsys.readouterr().out

    assert "DeepSeek compatibility" not in help_text
    assert "provider compatibility" in help_text
    assert "set Codex reasoning effort" in help_text
