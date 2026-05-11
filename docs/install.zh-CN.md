# 安装指南

## 推荐环境

优先推荐Linux、macOS或WSL。

要求：

- Python 3.11+
- Git
- Codex CLI
- DEEPSEEK_API_KEY

## 从源码安装

    git clone https://github.com/Awenforever/CoDeepSeedeX.git ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

## 初始化配置

    .venv/bin/dsproxy config init

默认配置路径：

    ~/.config/deepseek-responses-proxy/config.toml

## 安装Codex profile

    .venv/bin/dsproxy install-codex-profile

默认写入：

    ~/.codex/config.toml

这些命令会写入用户级配置。安装器或升级测试应在一次性虚拟机或显式隔离的测试HOME中运行，不要直接使用开发账号。

生成profile：

    deepseek-thinking

## 启动proxy

    export DEEPSEEK_API_KEY="..."
    .venv/bin/dsproxy start thinking
    .venv/bin/dsproxy doctor --thinking

## 运行Codex

    codex --profile deepseek-thinking

## 预览安装脚本

    bash scripts/install.sh

正式公开前，需要替换scripts/install.sh中的占位仓库地址。

## 升级

如果需要从旧版本升级，安装后可参见[升级](upgrade.zh-CN.md)。
