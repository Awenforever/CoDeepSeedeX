from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


def test_installer_model_provider_family_and_endpoint_flow() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")

    assert "Select model provider family" in text
    assert "DeepSeek|supported" in text
    assert "Kimi / Moonshot|experimental" in text
    assert "ZhipuAI / BigModel|experimental" in text
    assert "Z.AI|experimental" in text
    assert "Qwen / DashScope|experimental" in text
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


def test_installer_image_provider_family_and_region_flow() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")

    assert "Select image generation provider family" in text
    assert "ZhipuAI / BigModel|supported" in text
    assert "Z.AI / CogView|supported" in text
    assert "Qwen Image / DashScope|supported" in text
    assert "Kolors|unsupported" in text
    assert "Hunyuan Image|unsupported" in text
    assert "Volcengine Ark|unsupported" in text

    assert "Select Qwen Image / DashScope region" in text
    assert "Beijing multimodal generation endpoint" in text
    assert "Singapore multimodal generation endpoint" in text
    assert "US Virginia endpoint; qwen-image-2.0-pro currently unavailable" in text
    assert "Germany Frankfurt endpoint; qwen-image-2.0-pro currently unavailable" in text
