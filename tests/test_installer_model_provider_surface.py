from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INSTALL = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")


def _shell_function(name: str) -> str:
    match = re.search(rf"{name}\(\) \{{\n.*?\n\}}", INSTALL, re.S)
    assert match, f"missing shell function: {name}"
    return match.group(0)


def test_installer_model_api_prompt_uses_explicit_site_plan_region_choices() -> None:
    assert "Zhipu / BigModel domestic general" in INSTALL
    assert "Zhipu / BigModel domestic Coding Plan" in INSTALL
    assert "Z.AI international general" in INSTALL
    assert "Z.AI international Coding Plan" in INSTALL
    assert "Qwen / DashScope Beijing pay-as-you-go" in INSTALL
    assert "Qwen / DashScope Singapore pay-as-you-go" in INSTALL
    assert "Qwen / DashScope US Virginia pay-as-you-go" in INSTALL

    assert 'PROMPTED_MODEL_PROVIDER="zhipu"' in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="zhipu-coding"' in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="zai"' in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="zai-coding"' in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="qwen-beijing"' in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="qwen-singapore"' in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="qwen-us"' in INSTALL

    assert 'PROMPTED_MODEL_PROVIDER="glm"' not in INSTALL
    assert 'PROMPTED_MODEL_PROVIDER="qwen"' not in INSTALL


def test_installer_model_api_defaults_keep_zhipu_zai_and_qwen_regions_separate() -> None:
    base_url = _shell_function("model_api_base_url")
    default_model = _shell_function("model_api_default_model")

    assert "zhipu|zhipuai|bigmodel)" in base_url
    assert "https://open.bigmodel.cn/api/paas/v4" in base_url
    assert "zhipu-coding|zhipu_coding|bigmodel-coding|bigmodel_coding)" in base_url
    assert "https://open.bigmodel.cn/api/coding/paas/v4" in base_url
    assert "zai|z.ai|glm)" in base_url
    assert "https://api.z.ai/api/paas/v4" in base_url
    assert "zai-coding|zai_coding|z.ai-coding|z.ai_coding)" in base_url
    assert "https://api.z.ai/api/coding/paas/v4" in base_url

    assert "qwen-beijing|qwen_beijing|qwen|dashscope|aliyun)" in base_url
    assert "https://dashscope.aliyuncs.com/compatible-mode/v1" in base_url
    assert "qwen-singapore|qwen_singapore|dashscope-singapore|dashscope_singapore)" in base_url
    assert "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" in base_url
    assert "qwen-us|qwen_us|qwen-us-virginia|qwen_us_virginia|dashscope-us|dashscope_us)" in base_url
    assert "https://dashscope-us.aliyuncs.com/compatible-mode/v1" in base_url

    assert "zai-coding|zai_coding|z.ai-coding|z.ai_coding)" in default_model
    assert "glm-4.7" in default_model
    assert "qwen-us|qwen_us|qwen-us-virginia|qwen_us_virginia|dashscope-us|dashscope_us)" in default_model
    assert "qwen-plus-us" in default_model
