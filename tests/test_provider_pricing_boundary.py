from __future__ import annotations

import inspect

import importlib

from codexchange_proxy.providers import get_provider_adapter

app_module = importlib.import_module("codexchange_proxy.app")


def test_deepseek_pricing_metadata_is_provider_owned() -> None:
    adapter = get_provider_adapter("deepseek")
    source = adapter.official_pricing_source()
    assert source["provider"] == "deepseek"
    assert source["source_url"] == app_module.DEEPSEEK_OFFICIAL_PRICING_URL
    assert source["parser"] == "deepseek_official_docs_html_bilingual_v3_discount_aware"


def test_app_deepseek_pricing_wrappers_delegate_to_provider_adapter() -> None:
    parse_source = inspect.getsource(app_module._parse_deepseek_official_pricing_html)
    refresh_source = inspect.getsource(app_module._refresh_deepseek_pricing_from_official_docs)
    discount_source = inspect.getsource(app_module._deepseek_discount_window_from_text)

    assert 'get_provider_adapter("deepseek").parse_official_pricing_html' in parse_source
    assert 'get_provider_adapter("deepseek").refresh_pricing_from_official_docs' in refresh_source
    assert 'get_provider_adapter("deepseek").discount_window_from_pricing_text' in discount_source


def test_deepseek_adapter_parser_matches_public_app_wrapper() -> None:
    html = """
    <table>
      <tr><th>类型</th><th>deepseek-v4-flash</th><th>deepseek-v4-pro</th></tr>
      <tr><td>百万tokens输入（缓存命中）</td><td>0.02元</td><td>0.025元（2.5折）~~0.1元~~</td></tr>
      <tr><td>百万tokens输入（缓存未命中）</td><td>1元</td><td>3元（2.5折）~~12元~~</td></tr>
      <tr><td>百万tokens输出</td><td>2元</td><td>6元（2.5折）~~24元~~</td></tr>
    </table>
    优惠期至 2026/09/06 16:00
    """
    adapter = get_provider_adapter("deepseek")
    adapter_result = adapter.parse_official_pricing_html(
        html,
        include_metadata=True,
        clean_pricing_html_cell=app_module._clean_pricing_html_cell,
        parse_pricing_cell_details=app_module._parse_pricing_cell_details,
    )
    wrapper_result = app_module._parse_deepseek_official_pricing_html(html, include_metadata=True)
    assert adapter_result == wrapper_result
    assert adapter_result["deepseek-v4-pro"]["input_cache_hit"] == 0.025
    assert adapter_result["__model_metadata__"]["deepseek-v4-pro"]["discount"]["validity_confidence"] == "official_note"


def test_public_release_tag_is_synchronized_to_v049() -> None:
    assert app_module.PROXY_PUBLIC_VERSION == "v0.4.10-alpha"
