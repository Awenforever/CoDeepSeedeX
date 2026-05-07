# CoDeepSeedeX

[English](README.md) | 中文说明

<!-- CODEEPSEEDEX_LOGO_START -->
<p align="center">
  <img src="docs/logo.png" alt="CoDeepSeedeX logo" width="220">
</p>
<!-- CODEEPSEEDEX_LOGO_END -->

CoDeepSeedeX是一个本地代理，用来让Codex通过DeepSeek模型运行。它不会替换你的Codex，只会新增`deepseek`和`deepseek-thinking`两个入口。

## ✅ 安装前准备

安装CoDeepSeedeX之前，请先确认你已经安装OpenAI Codex CLI，并且终端里可以直接运行`codex`命令。

    codex --version

如果还没有安装Codex CLI，请先安装：

    npm install -g @openai/codex

然后再运行CoDeepSeedeX的一行安装命令。

## ⚡ 一行安装

    curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash

安装向导会完成这些事：

- 把CoDeepSeedeX安装到`~/.local/share/deepseek-responses-proxy`
- 创建`dsproxy`命令
- 创建两个Codex配置：`deepseek`和`deepseek-thinking`
- 询问是否安装安全的`codex`包装器，只接管这两个profile
- 询问stable/thinking端口和DeepSeek API key
- 把API key写入权限为`chmod 600`的本地env文件

API key输入时不会回显，也不会打印到终端。这是基于本地文件权限的保存方式，不是严格意义上的加密存储。

## 🚀 快速开始

安装完成后：

    codex --profile deepseek
    codex --profile deepseek-thinking

如果你接受了推荐的codex wrapper，上面两个命令会在进入Codex前自动启动对应的本地proxy。

继续已有Codex对话：

    codex --profile deepseek-thinking resume

## 🧠 deepseek和deepseek-thinking有什么区别？

区别很简单：

- `deepseek`表示调用DeepSeek时不开启thinking。
- `deepseek-thinking`表示调用DeepSeek时开启thinking。

它们不是两个不同的Codex，而是两个Codex profile，分别连接到CoDeepSeedeX的两种本地proxy模式。

| Profile | 本地端口 | DeepSeek模式 | 适合场景 |
|---|---:|---|---|
| `deepseek` | 8000 | non-thinking，不开启thinking | 快速问答、轻量修改、低成本任务 |
| `deepseek-thinking` | 8001 | thinking，开启thinking | 长任务、多步骤代码修改、工具调用较多的agent流程 |

换句话说，`deepseek-thinking`不是指Codex本身变了，而是CoDeepSeedeX在向上游DeepSeek发请求时启用了thinking模式。

## 🤖 已支持的DeepSeek模型

CoDeepSeedeX当前主要面向DeepSeek官方V4 API模型名。

同一个DeepSeek V4模型可以用两种模式调用：

- non-thinking模式：不开启thinking，模型直接返回回答。
- thinking模式：开启thinking，模型先进行推理过程，再返回回答。

| 上游模型 | non-thinking模式 | thinking模式 | CoDeepSeedeX推荐用法 |
|---|---|---|---|
| `deepseek-v4-pro` | 支持 | 支持 | 默认用于`deepseek-thinking`，适合长任务、代码修改和更强推理 |
| `deepseek-v4-flash` | 支持 | 支持 | 默认用于`deepseek`，适合快速任务、轻量修改和低成本使用 |

旧模型名兼容关系：

| 旧模型名 | 实际含义 | 状态 |
|---|---|---|
| `deepseek-chat` | `deepseek-v4-flash`不开启thinking | 兼容旧名称 |
| `deepseek-reasoner` | `deepseek-v4-flash`开启thinking | 兼容旧名称 |

CoDeepSeedeX默认配置：

| Codex profile | 默认上游模型 | DeepSeek模式 |
|---|---|---|
| `deepseek` | `deepseek-v4-flash` | non-thinking，不开启thinking |
| `deepseek-thinking` | `deepseek-v4-pro` | thinking，开启thinking |

可以用`dsproxy config set-model deepseek-v4-pro`或`dsproxy config set-model deepseek-v4-flash`切换上游模型。进入Codex TUI后，也可以用`/model`调整Codex侧的模型或推理设置。

## 🧭 Codex TUI内置命令

进入Codex后可以直接用这些slash commands：

    /status

查看当前会话和运行状态。

    /model

在Codex内部切换模型或推理强度。

    /plan

先规划任务，再进入实现。

你也可以直接发送自然语言消息，例如：

    check balance

或者：

    检查余额

Codex通常会调用本地工具执行`dsproxy balance`。如果你想要最稳定的结果，可以直接在shell中运行：

    dsproxy balance

## 🔧 常用shell操作

检查proxy状态：

    dsproxy doctor --thinking

查看DeepSeek余额：

    dsproxy balance

查看本地配置：

    dsproxy config show

切换DeepSeek上游模型：

    dsproxy config set-model deepseek-v4-pro
    dsproxy config set-model deepseek-v4-flash

切换Codex推理强度：

    dsproxy config set-effort medium
    dsproxy config set-effort high
    dsproxy config set-effort xhigh
    dsproxy config set-effort max

查看用量：

    dsproxy usage --thinking --summary

查看完整帮助：

    dsproxy -H

## 🧹 卸载和还原

移除CoDeepSeedeX写入的Codex profiles和wrapper：

    bash scripts/install.sh --uninstall

如果安装器曾经替换过安装目录中的`codex`命令，它会记录备份路径，并在卸载时尽量恢复原文件。

默认卸载只移除wrapper和Codex配置，不删除源码安装目录和本地env文件。如果也要删除这些文件：

    bash scripts/install.sh --uninstall --remove-files

## 📦 从源码安装

    git clone https://github.com/Awenforever/CoDeepSeedeX.git ~/deepseek-responses-proxy
    cd ~/deepseek-responses-proxy
    python3 -m venv .venv
    .venv/bin/python -m pip install -e .

初始化：

    .venv/bin/dsproxy config init
    .venv/bin/dsproxy install-codex-profile --name deepseek --base-url http://127.0.0.1:8000/v1
    .venv/bin/dsproxy install-codex-profile --name deepseek-thinking --base-url http://127.0.0.1:8001/v1

## 🔐 安全说明

CoDeepSeedeX只建议在本地使用，不要暴露到公网。

Codex可能根据你的配置调用工具、修改文件、执行命令或访问MCP服务器。

建议先阅读：

- docs/security.zh-CN.md
- docs/security.en.md
