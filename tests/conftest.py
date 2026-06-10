from __future__ import annotations

import os

import pytest

_CODEEPSEEDEX_EXTERNAL_ENV_PREFIXES = (
    "DEEPSEEK_",
    "CODEEPSEEDEX_",
)

_CODEEPSEEDEX_EXTERNAL_ENV_KEYS = {
    "CODEX_CONFIG_FILE",
    "OPENAI_API_KEY",
    "SERPAPI_API_KEY",
    "TAVILY_API_KEY",
    "EXA_API_KEY",
    "FIRECRAWL_API_KEY",
    "ZHIPUAI_API_KEY",
    "BIGMODEL_API_KEY",
    "DASHSCOPE_API_KEY",
}


def _codeepseedex_external_env_keys() -> list[str]:
    return [
        key
        for key in list(os.environ)
        if key in _CODEEPSEEDEX_EXTERNAL_ENV_KEYS
        or any(key.startswith(prefix) for prefix in _CODEEPSEEDEX_EXTERNAL_ENV_PREFIXES)
    ]


# Import-time cleanup is intentional: deepseek_responses_proxy.app binds selected
# defaults from os.environ at import time. A configured developer shell must not
# make the test suite inherit the user's active provider/model.
for _key in _codeepseedex_external_env_keys():
    os.environ.pop(_key, None)


@pytest.fixture(autouse=True)
def _isolate_codeepseedex_external_env(monkeypatch: pytest.MonkeyPatch):
    for key in _codeepseedex_external_env_keys():
        monkeypatch.delenv(key, raising=False)
