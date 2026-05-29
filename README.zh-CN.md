# CoDeepSeedeX

[English](README.md) | 中文说明

<!-- CODEEPSEEDEX_LOGO_START -->
<p align="center">
  <img src="docs/logo.png" alt="CoDeepSeedeX logo" width="220">
</p>
<!-- CODEEPSEEDEX_LOGO_END -->

CoDeepSeedeX是一个本地OpenAI Responses兼容代理，用来让Codex通过OpenAI兼容的model API provider运行，包括DeepSeek兼容模型、Kimi/Moonshot、Zhipu/BigModel、Z.AI、Qwen/DashScope和其他受管provider。它保留原始`codex`命令，新增`deepseek`和`deepseek-thinking`两个受管profile，并提供`dsproxy`用于安装、配置、状态检查、升级、provider诊断、价格缓存和WeClaw联动。

## 安装前准备

先安装OpenAI Codex CLI，并确认`codex`已在`PATH`中。

```bash
codex --version
```

如果还没有安装Codex CLI：

```bash
npm install -g @openai/codex
```

## 安装

默认通道，使用GitHub Latest Release资产：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

显式pre-release通道，当前为`v0.4.2-alpha`：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.4.2-alpha/bootstrap.sh | bash -s -- --install-ref v0.4.2-alpha
```

如果GitHub Release资产、raw GitHub或CDN路由不稳定，使用备用下载命令：

```bash
tag="v0.4.2-alpha"
tmp="$(mktemp -d)"
bs="$tmp/bootstrap.sh"
(
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://github.com/Awenforever/CoDeepSeedeX/releases/download/${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://cdn.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh" -o "$bs" ||
  curl -fL --retry 5 --retry-all-errors --retry-delay 3 "https://fastly.jsdelivr.net/gh/Awenforever/CoDeepSeedeX@${tag}/bootstrap.sh" -o "$bs"
) && bash "$bs" --install-ref "$tag"
```

安装器会把CoDeepSeedeX放到`~/.local/share/deepseek-responses-proxy`，创建`dsproxy`命令，创建`deepseek`和`deepseek-thinking`两个Codex profile，并可安装一个窄作用域`codex`wrapper，只接管这两个受管profile。

## 验证

```bash
dsproxy --version
dsproxy status
dsproxy status thinking
```

版本输出应包含两行：

```text
public version: v0.x.y-alpha | <public-release-commit>
internal version: p2.x-topic | <internal-commit>
```

通过受管profile启动Codex：

```bash
codex --profile deepseek
codex --profile deepseek-thinking
```

## 配置模型API

不确定应配置哪个provider时，使用引导菜单：

```bash
dsproxy config wizard
```

查看已保存配置，不打印密钥明文：

```bash
dsproxy config show
```

配置Codex本身使用的模型provider：

```bash
dsproxy config set-model --provider deepseek
dsproxy config set-model --provider kimi
dsproxy config set-model --provider zhipu
dsproxy config set-model --provider zhipu-coding
dsproxy config set-model --provider zai
dsproxy config set-model --provider zai-coding
dsproxy config set-model --provider qwen-beijing
dsproxy config set-model --provider qwen-singapore
dsproxy config set-model --provider qwen-us
```

非交互式写法，文档中只使用fake key：

```bash
dsproxy config set-model --provider deepseek --value sk-fake-deepseek-api-key
```

自定义provider示例：

```bash
dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --skip-validation
dsproxy config set-model provider-model-name --provider custom --base-url https://api.example.com/v1 --value sk-fake-custom-api-key --skip-validation
dsproxy config set-model qwen3-coder-plus --provider custom --base-url https://coding-intl.dashscope.aliyuncs.com/v1 --skip-validation
```

API key会保存到本地CoDeepSeedeX env文件，并使用较严格的文件权限。交互式命令会在隐藏输入提示处读取密钥；隐藏输入只是不在屏幕上显示密钥，不等于加密保存。API key应通过`--value`或隐藏输入传入，不是放在命令末尾当位置参数。

## 可选工具provider

配置引导中支持的web search provider包括SerpAPI、Tavily、Exa和Firecrawl。

```bash
dsproxy config set-web-search-api-key --provider serpapi
dsproxy config set-web-search-api-key --provider tavily
dsproxy config set-web-search-api-key --provider exa
dsproxy config set-web-search-api-key --provider firecrawl
```

非交互式web search示例，文档中只使用fake key：

```bash
dsproxy config set-web-search-api-key --provider serpapi --value fake-serpapi-api-key --skip-validation
```

支持的文生图provider包括ZhipuAI/BigModel、Z.AI、Qwen Image/DashScope、Stability AI和fal.ai。

```bash
dsproxy config set-image-api-key --provider zhipu
dsproxy config set-image-api-key --provider zai
dsproxy config set-image-api-key --provider qwen_image
dsproxy config set-image-api-key --provider stability
dsproxy config set-image-api-key --provider fal
```

非交互式文生图provider示例，文档中只使用fake key：

```bash
dsproxy config set-image-api-key --provider zhipu --value fake-zhipu-api-key --skip-validation
```

Qwen Image区域provider名显式列出，便于验证和排障：

```text
qwen_image_beijing    # 北京
qwen_image_singapore  # 新加坡
qwen_image_us         # 美国弗吉尼亚
德国法兰克福             # 已记录的不支持区域参考
```

provider诊断：

```bash
dsproxy doctor providers --json
dsproxy doctor providers --live --allow-spend --json
```

live诊断会调用外部API，可能消耗额度或产生费用。

## 启动和停止proxy

```bash
dsproxy start
dsproxy start thinking
dsproxy status
dsproxy status thinking
dsproxy stop
dsproxy stop thinking
```

`deepseek`使用non-thinking代理路由。`deepseek-thinking`使用thinking代理路由。wrapper会在为这两个受管profile启动Codex前自动启动或刷新对应proxy。

## 价格和费用元数据

查看当前本地价格表和元数据：

```bash
dsproxy pricing show --json
```

抓取并验证DeepSeek官方价格HTML，但不写入cache：

```bash
dsproxy pricing refresh --json
```

抓取并持久化验证后的官方价格cache：

```bash
dsproxy pricing refresh --write-cache --json
```

费用估算必须保留价格来源标识。内置兜底价格与新抓取的`official_docs_html`cache必须区分展示。

## 升级

默认升级路径跟随GitHub Latest Release：

```bash
dsproxy upgrade
dsproxy upgrade --dry-run
```

pre-release升级路径跟随最新非draft GitHub pre-release：

```bash
dsproxy upgrade --alpha
```

显式指定tag或ref：

```bash
dsproxy upgrade --tag v0.4.2-alpha
```

不要同时使用`--alpha`和`--tag`。

如果旧安装还没有`dsproxy upgrade`，重新运行安装命令。带有p2.14a9 fallback的source-archive/非git安装也可以使用`dsproxy upgrade --alpha`；该命令会用解析出的`--install-ref`重新运行Release bootstrap安装器。

## 卸载

完整产品卸载入口是安装器，不是`dsproxy uninstall`。

移除CoDeepSeedeX集成，但保留配置文件和安装目录：

```bash
bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall
```

移除集成，同时删除CoDeepSeedeX安装目录、env文件和安装manifest：

```bash
bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall --remove-files
```

卸载范围：

```text
- 移除CoDeepSeedeX管理的Codex profiles：`deepseek`和`deepseek-thinking`
- 移除CoDeepSeedeX管理的`codex` wrapper，并在存在备份时恢复旧`codex`命令
- 移除CoDeepSeedeX安装的`dsproxy` wrapper
- 使用`--remove-files`时，额外删除`~/.local/share/deepseek-responses-proxy`、CoDeepSeedeX env文件和安装manifest
```

卸载器不得删除无关用户文件或非CoDeepSeedeX配置。

## WeClaw联动

CoDeepSeedeX可以作为`weclaw_dev`的DeepSeek/Codex运行后端。

如果WeClaw联动使用CoDeepSeedeX `v0.4.2-alpha`、`v0.4.0-alpha`或`v0.3.9-alpha`，WeClaw版本必须不低于：

```text
weclaw_dev >= v0.1.9-alpha
```

机器可读status契约：

```bash
dsproxy status thinking --weclaw-json
```

WeClaw重点消费字段包括：

```text
context_window.used_tokens
context_window.latest_upstream_prompt_tokens
context_window.limit_explanation
tokens.attribution
pricing.source_trust
pricing.official_reference_url
pricing.official_source
cost.pricing_source_kind
cost.official_pricing_available
diagnostics.degraded_fields
semantic_compaction
```

当可用时，`context_window.used_tokens`是由最新上游provider `prompt_tokens`提供的显式估算值。它不是Codex内部context-window精确占用，也不能用累计session totals替代。

## 安全和数据边界

CoDeepSeedeX把本地配置保存在当前用户账号下。只有安装、升级、刷新profile或修改配置时，才会改动用户级Codex profile文件。

除非明确接受风险，不要把真实API key直接写进shell历史。优先使用隐藏输入或安全密钥工作流。

## 文档入口

用户入口：

```text
README.md
README.zh-CN.md
```

维护入口：

```text
docs/developer-handbook.md
docs/developer-handbook.zh-CN.md
docs/development-log.md
```

历史Release说明和长期开发记录应放在`docs/development-log.md`，不要继续堆进README。

## WeClaw状态遥测

CoDeepSeedeX通过`dsproxy status thinking --weclaw-json`向WeClaw提供结构化状态遥测。

当前面向WeClaw的字段包括：
- 来自provider usage的token用量；
- 基于本地DeepSeekprofile tokenizer的Details估算；
- 面向`user`、`user_history`、`tool_output`、`environment`等桶的脱敏prompt分段；
- 基于DeepSeek中文官方价格页的CNY优先Pricing/Cost字段；
- 逐turn费用账本，避免混合模型或route的session被当前active model价格重新计算；
- 使用完整受管`model_context_window_tokens`的token-first context-window展示，并单独暴露auto-compact触发阈值；
- 通过`runtime_payload_guard`暴露的token-only Compact和Trim运行态进度；
- 用于compaction审计的脱敏Compact prompt fingerprint和dry-run material分类；
- Compact audit metadata通过runtime/WeClaw status和CLI fallback契约暴露；
- 为跳过compaction报告生成Compact audit dry-run metadata，不调用模型、不改变payload；
- Compact audit通过WeClaw status可见性的HTTP端到端回归覆盖；
- token-first TRIM dry-run、类型枚举、first-image保护和静态块保护；
- 低风险文本payload的类型感知生产TRIM，并通过脱敏状态metadata暴露；
- 非保护image payload的图像语义信封，并保留first-image原文；
- GitHub源码支撑的Codex原生本地Compact prompt对齐，同时明确remote `responses/compact`受provider门控，不声称第三方DeepSeek route具备该能力。

WeClaw应消费dsproxy提供的结构化JSON字段，不应自行重算token分类、币种换算或session费用。
