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
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/${tag}/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 https://fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh -o "$bs"
) && bash "$bs"
```

安装向导会完成这些事：

- 把CoDeepSeedeX安装到`~/.local/share/deepseek-responses-proxy`
- 创建`dsproxy`命令
- 创建两个Codex配置：`deepseek`和`deepseek-thinking`
- 询问是否安装安全的`codex`包装器，只接管这两个profile
- 询问stable/thinking端口
- 进入API配置引导菜单，用于配置model API、可选web search provider和可选文生图provider
- 在对应的隐藏输入提示处要求你粘贴API key
- 保存前自动验证已配置的API key，除非你跳过验证或跳过该provider
- 把验证通过的API key写入权限为`chmod 600`的本地env文件

- 只在当前用户账号下修改Codex/profile相关用户级文件

维护者安全提示：安装、升级、卸载和升级矩阵测试可能修改真实用户级路径，例如`~/.local`、`~/.config`、`~/.codex`、`~/.bashrc`或`~/.profile`。除非明确要修改开发账号，否则应在一次性虚拟机或显式隔离的测试HOME中运行。

当安装器或`dsproxy config wizard`要求输入API key时，把密钥直接粘贴到对应的隐藏输入提示处，然后按Enter。隐藏输入表示你输入或粘贴时屏幕上不会显示密钥。这是基于本地文件权限的保存方式，不是严格意义上的加密存储。验证失败时不会保存密钥，配置引导也允许跳过，后续可再配置。

bootstrap脚本会在apt系系统上自动安装缺失的基础依赖，包括`git`、`curl`、`ca-certificates`和供安装器使用的Python 3.11+解释器。

## ⬆️ 升级

**强烈建议所有版本在`v0.3.3-alpha`之前的用户，用`curl`那条命令更新一次，以后都可以直接用`dsproxy upgrade`无缝更新了。**

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

默认情况下，`dsproxy upgrade`会解析GitHub Latest Release tag并checkout到该受控Release版本，重新安装包，刷新`deepseek`和`deepseek-thinking`两个Codex profile，重启本地proxy，并在模型、web search或文生图API仍未配置时进入API配置引导。该引导仍允许跳过。

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

这里有三层配置：

1. model API key是Codex通过CoDeepSeedeX调用上游模型所必需的密钥。
2. web search API key是可选配置。只有当你希望Codex工具调用使用网页搜索时才需要配置。
3. 文生图API key是可选配置。只有当你希望Codex工具调用生成图片时才需要配置。

安装脚本和`dsproxy config wizard`会在保存前验证API密钥。本地env文件默认路径为`~/.config/deepseek-responses-proxy/env`，并设置受限文件权限。命令要求输入密钥时，把API key粘贴到隐藏的`API key:`提示处并按Enter。密钥不会回显到终端。

常用命令：

```bash
# 查看已保存的provider配置。密钥内容不会明文打印。
dsproxy config show

# 打开交互式配置菜单。不确定要配置哪个provider时，优先使用这个。
dsproxy config wizard

# 配置Codex本身使用的model API provider。
dsproxy config set-model --provider deepseek
dsproxy config set-model --provider kimi
dsproxy config set-model --provider zhipu
dsproxy config set-model --provider zhipu-coding
dsproxy config set-model --provider zai
dsproxy config set-model --provider zai-coding
dsproxy config set-model --provider qwen-beijing
dsproxy config set-model --provider qwen-singapore
dsproxy config set-model --provider qwen-us
dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --skip-validation

# 测试当前已配置的model API key。
dsproxy config test-api-key

# 配置可选web search工具provider。
dsproxy config set-web-search-api-key --provider serpapi
dsproxy config set-web-search-api-key --provider tavily
dsproxy config set-web-search-api-key --provider exa
dsproxy config set-web-search-api-key --provider firecrawl

Brave Search不再显示在配置引导中，因为其API key创建需要付费订阅，无法提供免费live probe路径。

# 配置可选文生图工具provider。
dsproxy config set-image-api-key --provider zhipu
dsproxy config set-image-api-key --provider zai
dsproxy config set-image-api-key --provider qwen_image
dsproxy config set-image-api-key --provider stability
dsproxy config set-image-api-key --provider fal
```

只有在你明确想跳过在线provider验证时才添加`--skip-validation`，例如当前离线、provider验证接口临时不可用，或正在配置无法自动验证的custom provider：

```bash
dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --skip-validation
dsproxy config set-web-search-api-key --provider serpapi --skip-validation
dsproxy config set-image-api-key --provider zhipu --skip-validation
```

下面是使用fake API的输入示例：

```bash
# 推荐的交互式写法。运行命令后，把真实API key粘贴到隐藏输入提示处。
dsproxy config set-model --provider deepseek
# 命令会显示类似下面的提示：
# DeepSeek API key: <在这里粘贴真实key；输入内容不会显示>

# 非交互式写法。API key必须放在--value后面，不是放在命令末尾当位置参数。
# 文档中只使用fake值；真实密钥不建议写进shell历史。
dsproxy config set-model --provider deepseek --value sk-fake-deepseek-api-key
dsproxy config set-web-search-api-key --provider serpapi --value fake-serpapi-api-key
dsproxy config set-image-api-key --provider zhipu --value fake-zhipu-api-key

# 自定义model provider示例。
dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --value sk-fake-custom-api-key --skip-validation
```

安装脚本也会把该env文件和`dsproxy`包装命令目录接入shell profile。新终端可以直接找到`dsproxy`，Codex也可以读取已配置的model API key。如果当前终端仍提示找不到`dsproxy`，打开新终端，或执行安装脚本最后打印的`source`命令。

安装脚本写入Codex profile时会携带项目内置model catalog metadata，避免`deepseek-v4-pro`和`deepseek-v4-flash`回退到未知模型元数据。


### Provider申请入口速查

CoDeepSeedeX只保留轻量配置说明。免费额度、试用额度和限速规则经常变化，使用前请以各provider官方pricing或credits页面为准。web search和文生图与model API是分开的：model API负责让Codex回答和执行任务，web search和文生图只在Codex需要当前网页结果或生成图片时作为可选工具provider使用。Web search密钥验证会使用固定低结果数查询，可能消耗极少量search额度。文生图密钥验证尽量不生成图片：Stability使用账户余额探测，fal.ai使用模型元数据探测，Zhipu/Z.AI和Qwen/DashScope使用非生成式认证探测。验证失败时不会保存密钥，除非显式传入`--skip-validation`。

#### Model API provider速查

Model API配置必须明确区分站点、地区和plan。文档中不要继续使用旧的`glm`或`qwen`快捷入口，因为它会隐藏endpoint选择。

| Model API路径 | 当前状态 | 配置命令 |
| --- | --- | --- |
| DeepSeek | 现有主路径 | `dsproxy config set-model --provider deepseek` |
| Kimi / Moonshot | endpoint可达，但已测试key返回HTTP 401 | `dsproxy config set-model --provider kimi` |
| Zhipu / BigModel国内通用 | `/models`验证通过 | `dsproxy config set-model --provider zhipu` |
| Zhipu / BigModel国内Coding Plan | `/models`验证通过，必须与通用endpoint区分 | `dsproxy config set-model --provider zhipu-coding` |
| Z.AI国际通用 | `/models`验证通过 | `dsproxy config set-model --provider zai` |
| Z.AI国际Coding Plan | `/models`验证通过，必须与通用endpoint区分 | `dsproxy config set-model --provider zai-coding` |
| Qwen / DashScope北京按量计费 | `/models`验证通过 | `dsproxy config set-model --provider qwen-beijing` |
| Qwen / DashScope新加坡按量计费 | `/models`验证通过 | `dsproxy config set-model --provider qwen-singapore` |
| Qwen / DashScope美国弗吉尼亚按量计费 | `/models`验证通过 | `dsproxy config set-model --provider qwen-us` |
| Qwen Coding Plan / Token Plan | 未做普通脚本live probe，需要走对应工具路径验证 | 只在验证对应工具路径时按`custom`配置，例如`dsproxy config set-model qwen3-coder-plus --provider custom --base-url https://coding-intl.dashscope.aliyuncs.com/v1 --skip-validation` |

| 工具 | 已支持provider | 配置命令 | 申请/额度页面 |
| --- | --- | --- | --- |
| Web search | SerpAPI | `dsproxy config set-web-search-api-key --provider serpapi` | https://serpapi.com/pricing |
| Web search | Tavily | `dsproxy config set-web-search-api-key --provider tavily` | https://docs.tavily.com/documentation/api-credits |
| Web search | Exa | `dsproxy config set-web-search-api-key --provider exa` | https://exa.ai/ |
| Web search | Firecrawl | `dsproxy config set-web-search-api-key --provider firecrawl` | https://www.firecrawl.dev/ |
| 文生图 | 智谱AI / BigModel国内站CogView | `dsproxy config set-image-api-key --provider zhipu` | https://www.bigmodel.cn/ |
| 文生图 | Z.AI国际站CogView | `dsproxy config set-image-api-key --provider zai` | https://docs.z.ai/ |
| 文生图 | Qwen Image / DashScope | `dsproxy config set-image-api-key --provider qwen_image` | https://help.aliyun.com/zh/model-studio/qwen-image-api |

如需测试或使用DashScope区域endpoint，请先将`DEEPSEEK_PROXY_IMAGE_BASE_URL`设置为目标区域的multimodal generation endpoint，再运行`dsproxy doctor providers --kind image --provider qwen_image --live --allow-spend`。DashScope API key和服务域名具有区域绑定关系。
| 文生图 | Stability AI | `dsproxy config set-image-api-key --provider stability` | https://platform.stability.ai/ |
| 文生图 | fal.ai | `dsproxy config set-image-api-key --provider fal` | https://fal.ai/ |

自定义tool server可在引导菜单中选择`Other`，然后让agent阅读`docs/developer-handbook.zh-CN.md`协助配置。具体交接清单见`docs/developer-handbook.zh-CN.md`。

Provider诊断：

```bash
# 只检查provider密钥是否已配置，不调用外部API。
dsproxy doctor providers

# 执行真实低结果数web search探测。该操作可能消耗provider搜索额度。
dsproxy doctor providers --kind web-search --provider serpapi --live --allow-spend

# 执行真实文生图探测。该操作会创建测试图片，可能消耗额度。
dsproxy doctor providers --kind image --provider zhipu --live --allow-spend
```


## 行为变化表

Release notes需要说明里程碑式行为变化。README也保留这个简表，用来记录会永久改变CLI行为或用户工作流的变化。

| 版本 | 改变对象 | 此前行为 | 以后行为 | 迁移提示 |
|---|---|---|---|---|



| unreleased / p2.10a12 | Bootstrap install-ref与Release资产解析 | `bootstrap.sh --install-ref v0.3.8-alpha`仍会优先下载Latest的`install.sh`，导致pre-release全新VM测试进入旧安装器。 | Bootstrap现在会消费`--install-ref`，优先下载对应Release资产中的`install.sh`，并在banner下显示bootstrap/installer来源。 | VM复测前需重建`v0.3.8-alpha`pre-release资产。 |
| unreleased / p2.10a11 | 模型provider支持级别标记 | 非DeepSeek模型provider此前标为Supported，但目前只验证过API连通性。 | 只有DeepSeek保留Supported。Kimi、Zhipu / BigModel、Z.AI和Qwen / DashScope模型provider改为Experimental，直到完整Codex工作流验证通过。 | 这是支持级别分类和交互提示修正。 |
| unreleased / p2.10a10 | 安装器provider选择交互 | 安装器provider菜单主要依赖数字输入，部分image provider提示仍使用泛化Qwen名称。 | 引导式安装菜单优先使用方向键选择，并保留数字/文本fallback。image provider提示改为显式Qwen地区名称。 | 仅修改安装器交互体验，不移动Release tag。 |
| v0.3.8-alpha / p2.10a8 | Alpha升级通道和Codex选项卡标题 | `dsproxy upgrade`只跟随GitHub Latest Release，Codex wrapper不会设置终端选项卡标题。 | `dsproxy upgrade --alpha`现在跟随最新的非draft GitHub pre-release，普通`dsproxy upgrade`仍跟随Latest Release。Codex wrapper会在`deepseek`和`deepseek-thinking`profile启动时随机设置`[emoji]CoDeepSeedeX`格式的tab标题。 | 在VM中用`dsproxy upgrade --alpha`验证pre-release。验证完全通过后，再把该GitHub pre-release标记为Latest。 |
| v0.3.8-alpha / p2.10a6 | 安装器model API引导配置 | 安装器曾把model provider归入`GLM / Z.AI`或泛化`Qwen / DashScope`等含混入口，并把Mimo、Baichuan这类需要custom endpoint验证的选项放在公开引导选择中。 | 安装器现在与显式model provider surface保持一致，分别展示Zhipu / BigModel国内通用、Zhipu / BigModel国内Coding Plan、Z.AI国际通用、Z.AI国际Coding Plan，以及Qwen / DashScope北京、新加坡、美国弗吉尼亚按量计费入口。 | 只有依赖安装器交互式model API配置时才需要重新运行安装器。既有CLI配置保持兼容，旧`glm`和`qwen`快捷入口只保留为兼容别名，不作为公开推荐命令。 |
| v0.3.8-alpha / p2.10a4 | Model API配置命令 | `set-api-key`是主要的model API配置入口，`set-model`只修改当前上游模型。 | `set-model`成为model provider、模型和可选API key的主配置入口。`set-api-key`保留为兼容别名，并返回废弃提示。 | 后续优先使用`dsproxy config set-model --provider <provider>`配置model API。既有`set-api-key`脚本在兼容期内仍可继续运行。 |
| unreleased / p2.10a3 | provider验证和Qwen Image地区展示 | 文生图非生成式验证可能把HTTP 200加provider error body泛化成validation failed。Qwen Image只显示为一个泛化DashScope入口。 | 没有auth error时，HTTP 200加provider error body可作为非生成式认证/账户探测通过。Qwen Image现在显式列出北京、新加坡为可用选择，美国弗吉尼亚、德国法兰克福为模型暂不可用选择。 | 使用Qwen Image时重新执行`dsproxy config set-image-api-key --provider qwen_image_beijing`或`qwen_image_singapore`。 |
| unreleased / p2.10a2 | 配置生效和reasoning effort | API key、model和effort写入后，用户需要自己判断运行中的proxy是否要重启。用户文档中仍可能出现`medium`effort，但DeepSeek proxy路径会把它归一化为`high`。 | 配置写入成功后会刷新已经运行的本地stable/thinking proxy，并报告`all updates applied`。用户侧effort说明统一推荐`high`，`low`/`medium`仍作为兼容输入接受并保存为`high`。 | 重新运行安装器，或执行`dsproxy config set-effort high`刷新已安装Codex profile。 |

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
- 大型`image_payload`输出会完整保存为本地JSON artifact，并在模型上下文中替换为轻量级`image_payload_artifact_ref`元数据，保留path/URI/hash等恢复字段。
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
| `image_payload` | 图片查看或图片返回工具的大型结构化payload | 将完整超大payload保存为本地JSON artifact，模型上下文只保留轻量级`image_payload_artifact_ref`，避免破坏性裁剪，同时允许Codex按路径恢复完整图像payload。 |
| `search` | web/search类工具输出 | 单独分类，避免把搜索结果简单等同于shell日志。超大输出走保守裁剪。 |
| `file_read` | 文件检查或文件读取工具 | 单独分类以保留文件读取语义。超大输出走保守裁剪。 |
| `user_interaction` | prompts、approvals或用户交互类工具输出 | 单独分类并保守处理，因为其中可能包含交互状态。 |
| `unknown` | 未知工具 | 只在超大时使用保守fallback裁剪，保证proxy不依赖固定本地工具表。 |

结构化list/dict工具输出会先序列化为紧凑JSON，再进入裁剪逻辑。这样大型结构化payload也能进入统一预算路径。

受控维护者验证流程见`docs/developer-handbook.zh-CN.md`。

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

CoDeepSeedeX默认仍面向DeepSeek官方V4 API模型名，同时安装器和`dsproxy config`已支持若干OpenAI兼容的model API provider，包括DeepSeek、Kimi/Moonshot、GLM/Z.AI、Qwen/DashScope以及自定义endpoint。

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

检查thinking proxy健康状态和配置：

    dsproxy doctor --thinking

查看当前model provider支持的余额信息：

    dsproxy balance

查看本地provider、模型、工具和验证配置，密钥不会明文打印：

    dsproxy config show

切换CoDeepSeedeX调用的上游模型：

    dsproxy config set-model deepseek-v4-pro
    dsproxy config set-model deepseek-v4-flash

切换已安装profile的Codex侧推理强度：

    dsproxy config set-effort high
    dsproxy config set-effort xhigh
    dsproxy config set-effort max

查看thinking proxy的本地用量统计：

    dsproxy usage --thinking --summary

查看完整CLI帮助：

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

- TROUBLESHOOTING.md
- TROUBLESHOOTING.md

### C4命令风险gate可见性

proxy会通过`proxy_status`暴露`command_risk_policy`状态。

`DEEPSEEK_PROXY_COMMAND_RISK_POLICY_MODE`支持：

- `off`：关闭命令风险策略报告和gate。
- `dry_run`：只记录风险报告，不改变工具执行。
- `enabled`：启用C4 suppress-only gate。

该gate遵循Codex边界。项目内`apply_patch`、项目文件写入、缓存清理、`/tmp`清理、依赖安装和项目内破坏性开发操作仍交给Codex沙箱和审批机制处理。proxy只抑制`C4_catastrophic_or_out_of_sandbox`，例如删除根目录、删除home、删除整块挂载盘、格式化磁盘、写块设备、删除生产数据库或强推受保护分支。

C4抑制是suppress-only。它只返回assistant说明，不支持通过“继续”自动恢复执行。

## 文档

- Troubleshooting: `TROUBLESHOOTING.md`
- Developer handbook, English primary: `docs/developer-handbook.md`
- Developer handbook, Chinese mirror: `docs/developer-handbook.zh-CN.md`
- Detailed development log: `docs/development-log.md`

### Qwen Image区域provider状态

| Provider | 地区 | 状态 | 命令 |
|---|---|---|---|
| `qwen_image` | 北京 | 兼容旧命令的北京默认别名 | `dsproxy config set-image-api-key --provider qwen_image` |
| `qwen_image_beijing` | 北京 | 支持 | `dsproxy config set-image-api-key --provider qwen_image_beijing` |
| `qwen_image_singapore` | 新加坡 | 支持 | `dsproxy config set-image-api-key --provider qwen_image_singapore` |
| `qwen_image_us` | 美国弗吉尼亚 | qwen-image-2.0-pro模型暂不可用 | 为避免误解而列出，实际请选择北京或新加坡 |
| `qwen_image_germany` | 德国法兰克福 | qwen-image-2.0-pro模型暂不可用 | 为避免误解而列出，实际请选择北京或新加坡 |
