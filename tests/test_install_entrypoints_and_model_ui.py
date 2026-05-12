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
    assert "GLM / CogView" in text
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
    assert "glm|qwen_image" in text
