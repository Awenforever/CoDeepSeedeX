# CoDeepSeedeX开发者手册

本文件是英文主手册`docs/developer-handbook.md`的中文镜像，给你阅读和核对使用。以后给AI的新对话启动上下文，应优先使用英文主手册。详尽历史流水账放在`docs/development-log.md`，只有需要回溯时再读取。

## 1. 文档架构

用户文档：

- `README.md`：英文用户入口。
- `README.zh-CN.md`：中文用户入口。
- `TROUBLESHOOTING.md`：用户排障入口。

维护文档：

- `docs/developer-handbook.md`：英文主开发者手册，也是AI新对话主入口。
- `docs/developer-handbook.zh-CN.md`：中文镜像，给你看。
- `docs/development-log.md`：详尽长期开发日志，按需回溯。

不再维护`OPERATIONS.md`、`docs/install.*.md`、`docs/usage.*.md`、`docs/upgrade.*.md`、`docs/security.*.md`、`docs/troubleshooting.*.md`、`docs/handoff-for-developers.*.md`、`docs/custom_api_handoff.md`和`docs/release-notes-*`这类碎片文档。若测试仍读取旧路径，应修改测试契约，而不是保留幽灵文档。

## 2. 当前项目状态

- 项目路径：`~/projects/deepseek-responses-proxy`
- GitHub仓库：`Awenforever/CoDeepSeedeX`
- 主分支：`master`
- 当前公开Release：`v0.3.7-alpha`
- 公开Release commit：`466706f`
- Release内部tag：`p2.9a18-release-v0.3.7-alpha`
- p2.9a20文档基线：`p2.9a20-docs-consolidation = b160525`
- 旧公开tag不能移动：`v0.3.6-alpha = 7fd8fb6`，`v0.3.5-alpha = 53897ad`
- 普通错误tag`v0.3.5`必须不存在。

p2.9a21完成后，`master`、`origin/master`和`p2.9a21-handbook-bilingual-restoration`应指向同一个新commit。

## 3. 关键文件地图

- `deepseek_responses_proxy/app.py`：运行时核心、Responses兼容接口、DeepSeek桥接、工具桥接、provider分发、版本元数据、debug trace。
- `deepseek_responses_proxy/cli.py`：`dsproxy`命令入口、配置、provider设置、doctor命令、升级逻辑。
- `scripts/install.sh`：安装器，负责installed checkout同步、venv、wrapper、Codex profile和配置初始化。
- `bootstrap.sh`：一键安装入口，负责依赖和安装器获取。
- `tests/`：回归测试、文档契约测试、provider和安装器测试。
- `docs/development-log.md`：详尽开发日志。

## 4. 版本和tag规则

`dsproxy --version`必须输出两行：

```text
public version: v0.3.x-alpha | <public_release_commit>
internal version: p2.9aN-topic | <internal_commit>
```

公开Release tag在alpha阶段使用`v0.3.x-alpha`，不得创建不带`-alpha`的`v0.3.x`公开tag。内部开发tag使用`p`前缀，不创建GitHubRelease。

Release时通常需要同步：

- `deepseek_responses_proxy/app.py`
- `pyproject.toml`
- `tests/test_version_metadata.py`
- `tests/test_cli.py`

这些文件职责不同，不能强制每个文件都包含public和internal tag。

## 5. Release发布流程

Release必须按状态机执行：

1. 只读审计branch、HEAD、origin/master、工作区、旧public tag、目标public tag、GitHubRelease、版本字符串分布和测试文件存在性。
2. 同步版本元数据。
3. 运行静态检查、focused tests和full tests。
4. commit。
5. push工作分支。
6. push内部tag。
7. fast-forward master。
8. push master。
9. push公开Release tag。
10. 创建GitHubRelease并上传`bootstrap.sh`和`install.sh`。
11. 复核资产、tag、旧tag和错误普通tag。
12. 刷新本机运行时并验证`dsproxy --version`和`codex --profile deepseek-thinking app-server --help`。

push默认走HTTPS，不走SSH。所有网络步骤必须设置timeout。Release notes正文不得重复Release标题行。

## 6. Release错题本

这些经验必须保留在手册里：

1. 不能硬编码运行时版本文件路径，实际路径是`deepseek_responses_proxy/app.py`。
2. 不能假设只有一个Python文件含版本元数据。
3. 版本文件职责不同：运行时版本、包版本、版本一致性测试、CLI输出测试要分开处理。
4. 修改`pyproject.toml`后必须同步测试断言。
5. focused tests必须过滤不存在的测试文件。
6. Release脚本必须幂等且可续跑。
7. push必须走HTTPS并设置timeout，避免SSH 22端口长时间卡住。
8. 公开Release tag应靠后推送，避免半发布状态。
9. `gh release view`不得依赖当前gh版本不支持的字段，例如`isLatest`。
10. Release notes正文不得重复标题。
11. 文档重构必须同步测试契约，不要为了旧测试保留幽灵文档。
12. 开发者手册是新对话启动包，不是历史档案馆，详尽流水写入`docs/development-log.md`。

## 7. 安装器和本地文件覆盖规则

安装器覆盖本地文件前必须备份：

- `~/.config/deepseek-responses-proxy/env`
- `~/.local/bin/dsproxy`
- `~/.local/bin/codex`
- `~/.codex/config.toml`
- installed checkout中的dirty patch和untracked files

未知用户自有`codex`或`dsproxy`不能静默覆盖。已知CoDeepSeedeX wrapper可以备份后刷新。

## 8. Provider和自定义API维护入口

Provider相关维护内容集中在这里。关键路径：

- `deepseek_responses_proxy/app.py`
- `deepseek_responses_proxy/cli.py`
- `scripts/install.sh`
- `README.md`
- `README.zh-CN.md`
- `TROUBLESHOOTING.md`

Web search验证可能消耗少量quota。image默认验证通常是非生成式验证，不能证明真实出图。真实出图必须显式执行：

```bash
dsproxy doctor providers --live --allow-spend
```

不要新增用户未要求的`dsproxy config test-provider --kind web-search|image --provider <name>`命令。

智谱和Z.AI图像端点必须区分，不能混淆国内智谱、国际Z.AI、GLM和CogView。

Provider诊断不能把通用文生图密钥误判为所有文生图provider均已配置。`DEEPSEEK_PROXY_IMAGE_API_KEY`只是当前`DEEPSEEK_PROXY_IMAGE_PROVIDER`所选provider的兼容密钥；未选中的provider仍应以`ZAI_API_KEY`、`DASHSCOPE_API_KEY`、`STABILITY_API_KEY`、`FAL_KEY`等专用变量为准。

Qwen/DashScope provider诊断必须尊重区域图像endpoint。`DEEPSEEK_PROXY_IMAGE_BASE_URL`和`DASHSCOPE_IMAGE_ENDPOINT`必须在非生成式验证和live图像probe payload构造中覆盖北京默认endpoint。

## 9. VM GitHub代理经验

VMware NAT中，已验证的路径是：

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> 极连云
```

不要把端口能TCP连接误判为代理可用。若GitHubRelease资产和`git ls-remote`稳定，jsDelivr失败不应作为阻断项。

## 10. 文档维护原则

- 英文开发者手册是主手册。
- 中文手册是给你看的镜像。
- 手册只保留当前状态、关键规则、文件地图、Release规范、高频错题和近期一个大版本摘要。
- 详尽日志进入`docs/development-log.md`。
- 新经验先判断是“长期规则”还是“流水记录”。长期规则进手册，流水记录进development log。
- 文档结构变化必须同步测试契约。

## 11. 当前大版本摘要：p2.9 / v0.3.7-alpha

p2.9阶段包括：

- provider endpoint和validation语义修正。
- Zhipu/Z.AI图像provider区分。
- `dsproxy doctor providers` live probe矩阵。
- 安装器修复受影响机器和同版本rerun。
- installed checkout同步到目标Release ref。
- local bin ownership guard。
- VM GitHub代理经验沉淀。
- `v0.3.7-alpha`发布闭环。
- SerpAPI真实web search probe已通过，命令为`dsproxy doctor providers --kind web-search --provider serpapi --live --allow-spend`。
- Zhipu真实图像生成probe已通过，命令为`dsproxy doctor providers --kind image --provider zhipu --live --allow-spend`。
- p2.9a19写入Release错题。
- p2.9a20文档收敛。
- p2.9a21恢复英文主开发者手册和中文镜像。

更细流水见`docs/development-log.md`。

## 12. 新对话启动检查

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.7-alpha^{}
git rev-parse --short p2.9a20-docs-consolidation^{}
```

新对话优先读取`docs/developer-handbook.md`，需要回溯时再读`docs/development-log.md`。

## 13. 安装和回退入口

LatestRelease bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

tag fallback：

```bash
tag="v0.3.7-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

## 模型配置命令契约

文档和测试必须保留当前模型配置命令示例：

```bash
dsproxy config set-model deepseek-v4-pro
```

不要恢复旧式带连字符的配置命令。

## p2.9a22运行时版本元数据规则

`gh release view --json`本身不支持`isLatest`字段。这是命令schema限制，不是当前安装的GitHub CLI版本问题。Release检查必须使用`tagName`、`name`、`url`、`publishedAt`、`isDraft`、`isPrerelease`、`targetCommitish`和`assets`等兼容字段。如果必须确认Latest状态，应使用单独的兼容方法，不要调用`gh release view --json isLatest`。

运行时版本元数据采用双轨规则。用户从公开Release tag安装时，看到的是发布该Release时的公开`v~` tag和当时绑定的内部`p~` tag。开发机从`master`运行时，在下一次公开Release发布前，public版本仍保持当前最新公开`v~`，但internal版本必须随着`master`最新内部`p~` tag前进。因此，公开Release发布后的文档或维护提交会让开发机显示比用户公开Release更新的内部`p~`版本，这是正常状态。

## p2.9a23脚本作用域安全补充

生成包含Python heredoc的shell命令时，`ts`、`out`等shell变量不会自动进入Python作用域。必须通过环境变量显式传入，例如`UPDATE_TS="$ts" python3 - <<'PY...'`，或者在Python内部重新生成，例如`datetime.datetime.now().strftime(...)`。不得在Python heredoc中直接引用只存在于shell作用域的变量。本次开发入口wrapper修复脚本曾因此触发`NameError: name 'ts' is not defined`，并在真正写入wrapper之前失败。

凡是会修改真实HOME路径的脚本，都必须保持“先失败、后写入”的结构：先在实际执行语言内部完成变量初始化，确认前置条件，创建备份，然后才允许写目标文件。

## p2.9a24辅助函数签名安全补充

shell驱动命令中的Python辅助函数，其函数签名必须覆盖后续所有调用参数。如果后面会调用`run(..., env=sanitized)`，则辅助函数必须定义为带`env=None`，并把该参数传递给`subprocess.run`。`timeout`、`check`、`allow_fail`等关键字参数同理。本次只读主线恢复审计曾因此触发`TypeError: run() got an unexpected keyword argument 'env'`。

向用户给出生成命令前，必须静态检查辅助函数定义和调用点，确认后续使用的每个关键字参数都被函数签名接收。长命令优先使用覆盖全脚本需求的superset签名。

### Qwen/DashScope区域文生图live矩阵

p2.9a30-qwen-region-live-matrix-doc-sync记录当前Qwen Image区域live probe结论：

- 北京：`qwen-image-2.0-pro`通过，HTTP 200，返回图像证据。
- 新加坡：`qwen-image-2.0-pro`通过，HTTP 200，返回图像证据。
- 美国弗吉尼亚：区域endpoint覆盖已生效，但`qwen-image-2.0-pro`和`qwen-image-2.0-pro-2026-03-03`均返回`Model not exist`。
- 德国法兰克福：区域workspace endpoint覆盖已生效，但`qwen-image-2.0-pro`返回`Model not exist`。

不要把美国和德国结果理解为DashScope整体不可用。当前结论仅表示被测试的Qwen Image模型在这些endpoint上不可用。如果后续需要覆盖美国和德国文生图，应把Wan image/text-to-image作为单独provider模式测试，不要混入`qwen_image`。

### p2.9a34 Brave provider公开配置面移除

Brave Search不再作为web search provider展示或引导配置，因为API key创建需要付费订阅，无法提供免费live probe路径。README示例、配置引导、`doctor providers`默认矩阵和新用户配置文档均应删除Brave。底层runtime兼容与公开provider catalog分开处理，除非维护者明确要求删除底层兼容。

### p2.9a37 web search live矩阵

p2.9a37-web-search-live-matrix-doc-sync记录当前web search provider live probe状态：

- SerpAPI：已作为现有主web search路径配置。
- Tavily：live probe通过，endpoint为`https://api.tavily.com/search`，HTTP 200，`functional_validation=performed`。
- Exa：live probe通过，endpoint为`https://api.exa.ai/search`，HTTP 200，`functional_validation=performed`。
- Firecrawl：live probe通过，endpoint为`https://api.firecrawl.dev/v2/search`，HTTP 200，`functional_validation=performed`。
- Brave Search：从公开配置面放弃，因为API key创建需要付费订阅，且没有免费live probe路径。

当前公开和引导配置的web search provider为SerpAPI、Tavily、Exa和Firecrawl。除非维护者明确反转该决策，否则不要把Brave重新加入README、配置向导choices或`doctor providers`默认矩阵。

### p2.9a38 image provider live矩阵

p2.9a38-image-provider-live-matrix-doc-sync记录当前图像provider live probe状态：

- Qwen Image / 北京：`qwen-image-2.0-pro` live probe通过，HTTP 200，返回图像证据。
- Qwen Image / 新加坡：`qwen-image-2.0-pro` live probe通过，HTTP 200，返回图像证据。
- Qwen Image / 美国弗吉尼亚：区域endpoint覆盖已生效，但`qwen-image-2.0-pro`和`qwen-image-2.0-pro-2026-03-03`均返回`Model not exist`。
- Qwen Image / 德国法兰克福：区域workspace endpoint覆盖已生效，但`qwen-image-2.0-pro`返回`Model not exist`。
- Stability AI：原则上允许使用官方API，但当前WSL/CLI live probe在Cloudflare层被Error 1010 `browser_signature_banned`拦截。不要绕过或密集重试。应走官方支持、allowlist或其他被认可的接入路径。
- fal.ai：provider endpoint和账户均已被识别，但live generation因账户余额耗尽失败。充值后可重测。

解释：Qwen Image已在北京和新加坡验证通过。美国弗吉尼亚和德国属于被测Qwen Image模型不可用，不是endpoint覆盖失败。Stability属于访问层/WAF拦截，不是已确认的API或认证失败。fal.ai属于账户余额失败，不是代码或认证路径失败。

### p2.9a39 model API live矩阵

p2.9a39-model-api-live-matrix-doc-sync记录当前model API验证矩阵。

当前model API状态：

- DeepSeek：现有主路径和Release基线。
- Kimi / Moonshot：endpoint已打到`https://api.moonshot.ai/v1/models`，但提供的key返回HTTP 401 `Invalid Authentication`。这不是已确认的代码路径失败。应标记为endpoint reachable but not verified，等待有效Moonshot key后重测。
- GLM / Zhipu / Z.AI：`/models`级验证通过。
  - 国内BigModel通用endpoint通过：`https://open.bigmodel.cn/api/paas/v4`。
  - 国内BigModel Coding Plan endpoint通过：`https://open.bigmodel.cn/api/coding/paas/v4`。
  - Z.AI通用endpoint通过：`https://api.z.ai/api/paas/v4`。
  - Z.AI Coding Plan endpoint通过：`https://api.z.ai/api/coding/paas/v4`。
  - 当前矩阵中，国内BigModel key和Z.AI key均对四类endpoint验证通过。
- Qwen / DashScope按量计费API：`/models`级验证通过。
  - 北京通过：`https://dashscope.aliyuncs.com/compatible-mode/v1`，模型`qwen-plus`。
  - 新加坡通过：`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`，模型`qwen-plus`。
  - 美国弗吉尼亚通过：`https://dashscope-us.aliyuncs.com/compatible-mode/v1`，模型`qwen-plus-us`。
- Qwen Coding Plan和Token Plan：未做脚本live probe，因为官方用途约束将其与普通自动化API probe区分开。应作为单独配置引导路径处理，并通过对应工具路径验证，而不是用通用脚本probe替代。
- Custom provider：已通过GLM/Zhipu/Z.AI矩阵和Qwen按量计费矩阵验证其机制可用。

后续provider文档和配置引导必须使用这些状态，而不是简单写supported或unsupported：

- `verified`：live `/models`验证通过。
- `endpoint reachable but auth failed`：endpoint和代码路径已到达，但凭据认证失败。
- `implemented but not yet verified`：实现存在，但尚未成功live验证。
- `not script-tested`：由于官方用途约束或工作流约束，不适合普通脚本probe。
- `abandoned`：明确从公开和引导配置面放弃。

不要把未测试或认证失败的model provider写成unsupported。model API矩阵完成后，应进入专项架构分支，评估CoDeepSeedeX哪些层可复用，哪些层与DeepSeek强绑定。建议分支为`work/p2.10-anycodex-provider-architecture-audit`。该评估至少覆盖provider adapter、`reasoning_content`等reasoning/thinking字段、stream事件归一化、model catalog元数据、Codex `/model`展示，以及将CoDeepSeedeX升级为更通用AnyCodex式provider架构的整体方案。

### p2.9a40配置引导provider表面修复

p2.9a40-config-guide-provider-surface-repair根据web search、图像provider和model API矩阵结果更新公开配置面：

- README和README.zh-CN不能再把Brave Search列为公开和引导配置的web search provider。
- 安装器和配置引导必须按明确站点和plan展示model provider，不能继续用含混的`glm`或`qwen`快捷入口作为推荐命令。
- Zhipu / BigModel国内通用、Zhipu / BigModel国内Coding Plan、Z.AI国际通用、Z.AI国际Coding Plan必须分开展示。
- Qwen / DashScope按量计费地域必须分开展示为北京、新加坡和美国弗吉尼亚。
- Qwen Coding Plan和Token Plan仍是单独配置引导路径，不能按普通脚本probe的按量计费endpoint处理。
- 旧`glm`和`qwen`别名仅保留为内部归一化和旧配置兼容辅助能力；公开CLI choices和推荐文档命令必须使用明确站点和plan的provider名称。

### p2.9a41 p2.9a40后移交同步

p2.9a41-post-p2.9a40-handoff-sync记录provider配置面修复线收口后的状态。

p2.9a40后的当前仓库状态：

- `master`、`origin/master`、`work/p2.9a40-config-guide-provider-surface-repair`和内部tag`p2.9a40-config-guide-provider-surface-repair`均指向`cd8e4d9`。
- 公开Release tag`v0.3.7-alpha`仍指向`466706f`，除非维护者明确开始新的公开Release，否则不得移动。
- 错误普通公开tag`v0.3.5`仍不存在。
- p2.9a40已通过`git diff --check`、`bash -n bootstrap.sh`、`bash -n scripts/install.sh`、focused provider/config tests、broader provider/config tests和full tests，full tests结果为`363 passed`。

p2.9a40后的provider配置面状态：

- Brave Search已从README、README.zh-CN、安装器引导配置和安装器验证choices中移除。
- 公开model API配置使用明确站点和plan的provider名称：
  - `zhipu`
  - `zhipu-coding`
  - `zai`
  - `zai-coding`
  - `qwen-beijing`
  - `qwen-singapore`
  - `qwen-us`
- 含混的`glm`和`qwen`快捷入口不再作为公开推荐命令。它们最多只能作为内部归一化或旧配置兼容辅助能力存在。
- p2.10a6已修复`scripts/install.sh`，使安装器交互式model API配置使用同一套显式provider surface，并新增`tests/test_installer_model_provider_surface.py`防止回归。
- `p2.10a7-doc-sync`同步README、开发手册和development-log中关于p2.10a6安装器provider surface修复的记录。
- p2.10a7同步README、开发手册和development-log中关于p2.10a6安装器provider surface修复的记录。
- README和测试应继续区分verified、endpoint reachable but auth failed、implemented but not yet verified、not script-tested和abandoned等状态，不要退回supported/unsupported二分法。

下一阶段开发方向：

- 下一条主设计线建议从`work/p2.10-anycodex-provider-architecture-audit`开始。
- 审计必须先只读抓证据，不得凭记忆猜源码。第一步应审计`app.py`、`cli.py`、运行时配置加载、stream转换、model catalog、provider config、tool bridge、测试和文档。
- 目标是评估CoDeepSeedeX是否应重构为AnyCodex式通用provider架构。
- 重点检查DeepSeek强绑定区域，包括`reasoning_content`、reasoning/thinking事件处理、thinking profile行为、Responses到chat转换、stream事件归一化、tool-call repair、model catalog假设、`/model` UI预期和Codex profile wrapper行为。
- 工具替换应作为更广义的一层处理：web search、image generation和未来第三方工具应能透明替换Codex原生不可达或不可用工具，而不是只做SerpAPI特例桥。

### p2.10a2配置刷新与effort体验规则

凡是会改变API key、model选择或reasoning effort的本地配置写入，成功后都应执行CoDeepSeedeX自身的post-config hook。该hook可以刷新已经运行的本地stable/thinking `dsproxy`进程，并报告`all updates applied`。它不能启动原本未运行的proxy。WeClaw resume自动化明确不属于CoDeepSeedeX本线，应交给WeClaw开发线处理。

DeepSeek侧effort体验不应继续推荐`medium`。`low`和`medium`可以作为Codex或旧命令的兼容输入继续接受，但CoDeepSeedeX应把它们保存并转发为`high`。用户文档示例应优先使用`high`、`xhigh`或`max`。

### p2.10a3 provider验证和地区状态规则

非生成式provider probe可以有意发送空payload或metadata-only payload。如果这类probe收到HTTP 200，但响应体中仍包含结构化provider error body，并且没有检测到认证错误，CoDeepSeedeX应把它作为非生成式探测证据接受，而不是泛化为validation failed。这个分类只代表非生成式验证通过，不能写成真实文生图已成功。

Qwen Image地区支持必须显式展示。北京和新加坡是可选Qwen Image provider。美国弗吉尼亚和德国法兰克福仍应列出，让用户看见地区决策，但必须报告qwen-image-2.0-pro模型暂不可用，而不是表现得像CoDeepSeedeX故障。

### p2.10a4 config菜单model-provider体验

`dsproxy config set-model`现在是model API配置主入口。它可以在一条命令中设置model provider、上游模型和可选API key。`dsproxy config set-api-key`保留为既有脚本的兼容别名，但新文档和安装器提示应引导用户使用`set-model`。

规则：
- 在后续明确做兼容性破坏决策前，不删除`set-api-key`。
- 保持`set-model <model>`旧式DeepSeek单纯改模型流程可用。
- custom OpenAI-compatible provider使用`set-model <model> --provider custom --base-url <url>`。
- provider配置命令变化时，README、README.zh-CN、安装器提示、CLI帮助和测试必须同步。

### p2.10a5配置后体验一致性

将model API配置主入口切换为`dsproxy config set-model`后，公开配置界面必须保持一致：
- `configuration_status.commands.model_api`应与supported model provider列表保持同一公开范围，包括coding-plan和Qwen分区入口。
- README和README.zh-CN不得继续推荐`dsproxy config set-api-key --provider custom`作为新的custom model API配置写法。
- custom OpenAI-compatible model API示例必须使用`dsproxy config set-model <model> --provider custom --base-url <url>`。
- `set-api-key`只应在明确说明legacy alias兼容性时保留。

## p2.10a8 alpha升级和Codex选项卡标题规则

普通`dsproxy upgrade`必须继续解析GitHub Latest Release。`dsproxy upgrade --alpha`解析GitHub releases列表中最新的非draft pre-release。该通道用于维护者VM验证：先发布pre-release，在VM中用`dsproxy upgrade --alpha`测试，完全通过后再把同一个GitHub Release提升为Latest。

`scripts/install.sh`安装的Codex wrapper会在`codex --profile deepseek`和`codex --profile deepseek-thinking`启动时随机设置终端选项卡标题。标题格式为`[emoji]CoDeepSeedeX`，emoji来自维护者给定候选列表。该逻辑应保留在wrapper中，而不是放到proxy startup中，因为wrapper在执行真实Codex二进制之前拥有用户终端。

## p2.10a10安装器provider选择交互

引导式安装器provider菜单应优先使用方向键导航和回车确认，同时为非TTY或不兼容终端保留数字和文本输入fallback。公开provider名称必须按provider家族和地区显式区分。尤其是Qwen / DashScope的model和image provider，在endpoint或可用性不同的情况下，不能退回单一泛化`qwen`入口。

## p2.10a11模型provider支持级别标记

安装器和配置交互中，只有DeepSeek原生model provider可以标为`Supported`。Kimi、Zhipu / BigModel、Z.AI和Qwen / DashScope等其他model provider，在完整Codex工作流验证通过前必须标为`Experimental`。API key验证、endpoint可达或单次模型响应不足以声明Supported，因为Codex兼容性还依赖流式行为、工具调用、reasoning语义、上下文窗口、错误恢复和费用行为。

规则声明：API连通性不等于完整Codex工作流支持。

## p2.10a12 bootstrap install-ref来源显示

全新VM上的pre-release安装不能依赖GitHub Latest。当设置`bootstrap.sh --install-ref <tag>`或`DEEPSEEK_PROXY_INSTALL_REF=<tag>`时，bootstrap必须优先下载`https://github.com/Awenforever/CoDeepSeedeX/releases/download/<tag>/install.sh`，只有失败后才进入raw/tag clone fallback。Bootstrap和install界面必须在banner下显示来源信息，便于操作者确认当前运行的是Latest、指定Release tag还是本地checkout。

## p2.10a13安装器UI压缩

交互式安装界面不要在Logo下打印完整Release资产URL。可见UI应保持紧凑：banner附近只显示产品名和公开版本，bootstrap/installer来源详情写入日志。方向键菜单必须通过`/dev/tty`渲染和读取，不能依赖stdout，因为VM验证时stdout经常会被tee或日志包装捕获。

## p2.10a13公开commit解析

运行时public commit元数据在存在Git信息时应解析配置的公开Release tag，而不是在源码中维护自指向的静态commit hash。这样可以避免pre-release tag重建到新commit后反复修改测试。非Git安装场景仍保留源码fallback。

## p2.10a14安装器来源日志变量

将安装器来源详情从交互界面移入日志时，必须写入既有`INSTALL_LOG`变量。不要引入`LOG_FILE`；安装器启用了`set -u`，未定义变量会直接中断全新VM安装。

## p2.10a15安装器provider流程

引导式安装菜单应先选择provider族，只有在该族需要区分endpoint、地区、Token API或Coding Plan API时才进入二级菜单。Yes/No菜单必须使用plain渲染，不得继承Supported等provider状态标记。安装器Logo旁应显示当前install ref。VM安装期间如果Git clone或`git fetch --tags origin`失败，安装器可fallback到请求install ref对应的GitHub/codeload源码归档。

## p2.10a16安装器Logo heredoc

Shell脚本中的ASCII art如果包含反引号、反斜线或美元符号，必须使用引用heredoc。`bash -n`不会发现未引用heredoc在运行时触发的命令替换，因此安装器banner改动应增加实际调用渲染函数的运行时烟测。
