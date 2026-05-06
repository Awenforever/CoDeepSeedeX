# deepseek-responses-proxy

`deepseek-responses-proxy`是一个本地实验性OpenAI Responses兼容代理，用于让Codex通过DeepSeek上游模型运行。

目标是让：

    codex --profile deepseek-thinking

尽量接近原生Codex使用体验。

## 当前状态

技术预览版。建议公开发布标记：

    v0.1.0-alpha

不要将其描述为生产稳定版，也不要宣称完全替代原生Codex。

## 功能

- 面向Codex的Responses兼容本地API
- DeepSeek ChatCompletions上游桥接
- Codex工具调用归一化与协议强化
- Codex工具默认转发
- 上下文裁剪与持久本地压缩
- agent loop活性守卫
- 轻量LLM活性判定
- 内部调用usage归因
- 自适应压缩预算策略
- dsproxy统一CLI

## 安全提示

仅建议监听本地地址，不要暴露到公网。

Codex可能根据配置调用工具、修改文件、执行命令和访问MCP服务器。

请阅读：

    docs/security.zh-CN.md

## 环境要求

- Linux、macOS或WSL
- Python 3.11+
- Git
- Codex CLI
- DEEPSEEK_API_KEY

Windows原生支持仍处于实验阶段，优先推荐WSL。

## 从源码安装

    git clone https://github.com/Awenforever/CoDeepSeedeX.git ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

## 初始化

    .venv/bin/dsproxy config init
    .venv/bin/dsproxy install-codex-profile

## 启动

    export DEEPSEEK_API_KEY="..."
    .venv/bin/dsproxy start --thinking
    .venv/bin/dsproxy doctor --thinking

## 使用Codex

    codex --profile deepseek-thinking


## 日常操作

查看余额：

    dsproxy balance

查看本地proxy配置：

    dsproxy config show

切换DeepSeek上游模型：

    dsproxy config set-model deepseek-v4-pro
    dsproxy config set-model deepseek-v4-flash

切换Codex推理强度：

    dsproxy config set-effort medium
    dsproxy config set-effort high
    dsproxy config set-effort xhigh

启动thinking proxy：

    dsproxy start --thinking

继续已有Codex对话：

    codex --profile deepseek-thinking resume

完整帮助：

    dsproxy -H

## 查看用量

    .venv/bin/dsproxy usage --thinking --summary
    .venv/bin/dsproxy usage --thinking --summary --purpose primary
    .venv/bin/dsproxy usage --thinking --summary --purpose tool_bridge
    .venv/bin/dsproxy usage --thinking --summary --purpose compaction
    .venv/bin/dsproxy usage --thinking --summary --purpose liveness_judge
