# CoDeepSeedeX

[English](README.md) | [中文文档](README.zh-CN.md)

面向Codex和DeepSeek模型的本地OpenAI Responses兼容代理。

## 一行安装

    curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash

安装向导会询问stable proxy端口、thinking proxy端口和DeepSeek API key。API key输入时不回显，并写入权限为chmod 600的本地env文件。这不是严格意义上的加密存储。

安装完成后：

    dsproxy start --thinking
    codex --profile deepseek-thinking

继续已有Codex对话：

    codex --profile deepseek-thinking resume

## 这个项目做什么

CoDeepSeedeX是一个本地实验性OpenAI Responses兼容代理，用于让Codex通过DeepSeek上游模型运行。

它提供：

- 面向Codex的Responses兼容本地API
- DeepSeek ChatCompletions上游桥接
- Codex工具调用归一化与协议强化
- Codex工具默认转发
- 上下文裁剪与持久本地压缩
- agent loop活性恢复
- 轻量LLM活性判定
- 内部调用usage归因
- 自适应压缩预算策略
- dsproxy统一CLI

## 日常shell命令

检查proxy状态：

    dsproxy doctor --thinking

查看DeepSeek余额：

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

启动或停止thinking proxy：

    dsproxy start --thinking
    dsproxy stop --thinking

查看用量统计：

    dsproxy usage --thinking --summary
    dsproxy usage --thinking --summary --purpose primary
    dsproxy usage --thinking --summary --purpose tool_bridge
    dsproxy usage --thinking --summary --purpose compaction
    dsproxy usage --thinking --summary --purpose liveness_judge

查看完整CLI帮助：

    dsproxy -H

## Codex TUI内置命令

进入Codex：

    codex --profile deepseek-thinking

进入后，也可以使用Codex TUI内置的slash commands。

查看当前会话和运行状态：

    /status

在Codex内部切换模型或推理强度：

    /model

进入或使用plan模式，在执行前先做任务规划：

    /plan

这些slash commands由Codex TUI处理。dsproxy负责提供本地模型端点和配置辅助，但/status、/model、/plan本身属于Codex侧控制命令。

## 从源码安装

    git clone https://github.com/Awenforever/CoDeepSeedeX.git ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

初始化：

    .venv/bin/dsproxy config init
    .venv/bin/dsproxy install-codex-profile

启动：

    export DEEPSEEK_API_KEY="..."
    .venv/bin/dsproxy start --thinking
    .venv/bin/dsproxy doctor --thinking

## 安全提示

仅建议监听本地地址，不要暴露到公网。

Codex可能根据配置调用工具、修改文件、执行命令和访问MCP服务器。

请阅读：

- docs/security.zh-CN.md
- docs/security.en.md

## 当前状态

技术预览版。建议公开发布标记：

    v0.1.0-alpha

不要将其描述为生产稳定版，也不要宣称完全替代原生Codex。
