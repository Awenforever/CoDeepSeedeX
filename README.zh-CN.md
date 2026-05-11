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

    curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash

推荐的一行安装入口默认从最新GitHub Release asset分发。下面的fallback下载命令保留raw GitHub和CDN镜像作为备用入口。

### 备用安装命令

如果GitHub Release asset、`raw.githubusercontent.com`或CDN镜像不稳定，使用下面的fallback下载命令：

```bash
tmp="$(mktemp -d)"
bs="$tmp/bootstrap.sh"
(
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://github.com/Awenforever/CoDeepSeedeX/raw/refs/heads/master/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@master/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@master/bootstrap.sh -o "$bs"
) && bash "$bs"
```

安装完成后，重新打开shell，或执行`source ~/.bashrc`，确保`~/.local/bin`优先进入PATH。可用`command -v codex`和`command -v dsproxy`确认。

安装向导会完成这些事：

- 把CoDeepSeedeX安装到`~/.local/share/deepseek-responses-proxy`
- 创建`dsproxy`命令
- 创建两个Codex配置：`deepseek`和`deepseek-thinking`
- 询问是否安装安全的`codex`包装器，只接管这两个profile
- 询问stable/thinking端口和DeepSeek API key
- 把API key写入权限为`chmod 600`的本地env文件

- 只在当前用户账号下修改Codex/profile相关用户级文件

维护者安全提示：安装、升级、卸载和升级矩阵测试可能修改真实用户级路径，例如`~/.local`、`~/.config`、`~/.codex`、`~/.bashrc`或`~/.profile`。除非明确要修改开发账号，否则应在一次性虚拟机或显式隔离的测试HOME中运行。

API key输入时不会回显，也不会打印到终端。这是基于本地文件权限的保存方式，不是严格意义上的加密存储。

bootstrap脚本会在apt系系统上自动安装缺失的基础依赖，包括`git`、`curl`、`ca-certificates`和供安装器使用的Python 3.11+解释器。

## ⬆️ 升级

CoDeepSeedeX支持两种互相兼容的升级方式。

### 方式A：`dsproxy upgrade`

适用于已经包含`upgrade`命令的新版本：

```bash
dsproxy upgrade
```

先预览升级计划：

```bash
dsproxy upgrade --dry-run
```

默认情况下，`dsproxy upgrade`会把git checkout更新到`origin/master`上的最新`master`，重新安装包，刷新`deepseek`和`deepseek-thinking`两个Codex profile，并重启本地proxy。

如果确实需要固定到某个release或分支，可以显式指定ref：

```bash
dsproxy upgrade --tag <tag-or-branch>
```

### 方式B：再次运行one-line installer

适用于从`v0.1.0-alpha`等旧版本升级，或当前环境还没有`dsproxy upgrade`命令的情况：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

该方式与方式A兼容。bootstrap入口会拉取当前Release安装器，刷新安装目录和profile，并默认保留本地env和Codex配置。

任一方式完成后验证：

```bash
dsproxy --version
dsproxy doctor --thinking
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```


### API密钥和模型元数据

安装脚本会把DeepSeek API密钥保存到本地env文件，默认路径为`~/.config/deepseek-responses-proxy/env`，并设置受限文件权限。可使用：

```bash
dsproxy config show
dsproxy config set-api-key
dsproxy config test-api-key
dsproxy config set-web-search-api-key --provider serpapi
dsproxy config set-image-api-key --provider glm
```

安装脚本也会把该env文件和`dsproxy`包装命令目录接入shell profile。新终端可以直接找到`dsproxy`，Codex也可以读取`DEEPSEEK_API_KEY`。如果当前终端仍提示找不到`dsproxy`，打开新终端，或执行安装脚本最后打印的`source`命令。

安装脚本写入Codex profile时会携带项目内置model catalog metadata，避免`deepseek-v4-pro`和`deepseek-v4-flash`回退到未知模型元数据。

## 🚀 快速开始

安装完成后：

    codex --profile deepseek
    codex --profile deepseek-thinking

如果你接受了推荐的codex wrapper，上面两个命令会在进入Codex前自动启动对应的本地proxy。

继续已有Codex对话：

    codex --profile deepseek-thinking resume

## 🔌 v2.6a+的MCP行为

CoDeepSeedeX现在默认把Codex MCP配置作为信任边界。

- 默认MCP策略：`codex`
- 默认MCP后端：`stdio`
- 默认不需要proxy侧MCP allowlist
- 默认不拒绝写入型MCP tool
- 目标server必须存在于`~/.codex/config.toml`
- 目标tool必须存在于server运行时`tools/list`
- 当前支持的MCP传输：stdio `command` + `args`
- 暂不支持：HTTP/SSE/远程MCP传输

## 🧠 v2.7a+长会话compaction行为

CoDeepSeedeX v2.7a+通过在超大工具输出重新进入模型上下文之前进行裁剪，降低`deepseek-thinking`长会话中的重复上下文增长。

行为摘要：

- `deepseek-thinking`默认启用tool-outputtrimming。
- `deepseek`stable模式保持不变。
- 超大的`shell_command`和`interactive_shell`输出会以头尾保留方式裁剪。
- 大型结构化工具输出会尽量先紧凑序列化，再进入裁剪路径。
- `image_payload`输出有额外的12000字符单项上限。
- 裁剪发生在previous-response function-call过滤之前，因此仍能先识别工具输出类别，同时避免重复assistant tool-call replay。

最新真实验证快照：

| 指标 | 数值 |
| --- | --- |
| 发生裁剪的类别 | `shell_command`、`interactive_shell` |
| 实际裁掉字符数 | `44822` |
| latest observed context size | `270012`字符 |
| max observed context size | `405107`字符 |
| 裁掉字符数占latest context比例 | 约`16.6%` |
| 裁掉字符数占max context比例 | 约`11.1%` |

这些数值是最新aggregate trace快照，不是固定压缩率，也不是整个会话生命周期的总收益。由于历史工具输出会在后续turn中反复进入上下文，移除超大的历史输出会减少后续请求中的重复上下文增长。因此，累计prompt预算收益可能大于一次性的removed-char计数。

代价：超大输出的中间部分可能被省略。保留的头部和尾部通常能覆盖命令前置信息、摘要、退出结果和最近错误上下文。如果必须保留完整输出，应把日志保存为文件，再显式检查或上传该文件。

查看当前长会话状态：

```bash
dsproxy debug behavioral --thinking --limit 200 --timeout 5
```

## 🧩 当前compaction策略

工具输出会先分类，再裁剪。只有超大输出会被重写。

| 类别 | 常见来源 | 当前行为 |
| --- | --- | --- |
| `shell_command` | 非交互式shell命令、测试、日志 | 对超大输出执行头尾保留式裁剪，中间部分可能省略。 |
| `interactive_shell` | 长时间运行或PTY风格命令会话 | 对超大输出执行头尾保留式裁剪，尽量保留最近交互上下文。 |
| `image_payload` | 图片查看或图片返回工具的大型结构化payload | 尽量先紧凑序列化结构化输出，再应用image专用12000字符单项上限。 |
| `search` | web/search类工具输出 | 单独分类，避免把搜索结果简单等同于shell日志。超大输出走保守裁剪。 |
| `file_read` | 文件检查或文件读取工具 | 单独分类以保留文件读取语义。超大输出走保守裁剪。 |
| `user_interaction` | prompts、approvals或用户交互类工具输出 | 单独分类并保守处理，因为其中可能包含交互状态。 |
| `unknown` | 未知工具 | 只在超大时使用保守fallback裁剪，保证proxy不依赖固定本地工具表。 |

结构化list/dict工具输出会先序列化为紧凑JSON，再进入裁剪逻辑。这样大型结构化payload也能进入统一预算路径。

受控维护者验证流程见`docs/real-long-session-validation.md`。

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
### 🤝 WeClaw联动

<!-- CODEEPSEEDEX_WECLAW_DEV_INTEGRATION_START -->

CoDeepSeedeX可以和[weclaw_dev](https://github.com/Awenforever/weclaw_dev)联动，作为WeClaw类聊天和自动化流程中的DeepSeek/Codex运行后端。

当前联动能力边界：

- WeClaw可以把用户消息路由到由CoDeepSeedeX支撑的Codex profile。
- CoDeepSeedeX负责本地DeepSeek Responses兼容代理、运行时模型控制、MCP工具桥接和升级路径。
- WeClaw负责消息入口、会话路由、命令交互和用户侧机器人行为。
- CoDeepSeedeX不会替代WeClaw，WeClaw也不直接改变CoDeepSeedeX的proxy内部实现。

<!-- CODEEPSEEDEX_WECLAW_DEV_INTEGRATION_END -->

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

### C4命令风险gate可见性

proxy会通过`proxy_status`暴露`command_risk_policy`状态。

`DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE`支持：

- `off`：关闭命令风险策略报告和gate。
- `dry_run`：只记录风险报告，不改变工具执行。
- `enabled`：启用C4 suppress-only gate。

该gate遵循Codex边界。项目内`apply_patch`、项目文件写入、缓存清理、`/tmp`清理、依赖安装和项目内破坏性开发操作仍交给Codex沙箱和审批机制处理。proxy只抑制`C4_catastrophic_or_out_of_sandbox`，例如删除根目录、删除home、删除整块挂载盘、格式化磁盘、写块设备、删除生产数据库或强推受保护分支。

C4抑制是suppress-only。它只返回assistant说明，不支持通过“继续”自动恢复执行。
