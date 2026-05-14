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
