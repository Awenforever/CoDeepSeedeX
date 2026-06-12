from __future__ import annotations

from pathlib import Path


def test_provider_contract_describes_qwen_regions_as_native_adapters() -> None:
    text = Path("docs/provider-adapter-contract.md").read_text(encoding="utf-8")

    assert "Qwen region ids `qwen_beijing`, `qwen_singapore`, and `qwen_us` use native `qwen` adapters" in text
    assert "resolve through the generic `openai_compatible` adapter path with a selection warning" in text
    assert "qwen_singapore` and `zhipu_coding` map to the generic `openai_compatible` adapter until native adapters are added" not in text


def test_handbooks_distinguish_qwen_public_ids_from_native_adapter_ids() -> None:
    en = Path("docs/developer-handbook.md").read_text(encoding="utf-8")
    zh = Path("docs/developer-handbook.zh-CN.md").read_text(encoding="utf-8")

    assert "`qwen-beijing`, `qwen-singapore`, `qwen-us`" in en
    assert "`qwen_beijing`, `qwen_singapore`, `qwen_us`" in en
    assert "`qwen-beijing`、`qwen-singapore`、`qwen-us`" in zh
    assert "`qwen_beijing`、`qwen_singapore`、`qwen_us`" in zh
