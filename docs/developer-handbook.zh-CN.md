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

## 2. 项目身份和当前状态

- 本地项目路径：`~/projects/deepseek-responses-proxy`
- GitHub仓库：`Awenforever/CoDeepSeedeX`
- 主分支：`master`
- 当前公开alpha Release：`v0.3.8-alpha`
- 公开Release commit：`dfdc629`
- Release对应内部tag：`p2.10a26-wrapper-start-plan-mode-hardening`
- 当前内部开发线：`p2.10a44-doc-marker-discipline-cleanup`
- p2.10a43后的当前仓库基线：`master = origin/master = 9bf5fe9`
- 旧公开tag不能移动：
  - `v0.3.7-alpha = 466706f`
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- 错误普通tag `v0.3.5`必须不存在。
- `v0.3.8-alpha`是当前GitHub Release，当前没有标记为GitHub pre-release。它仍沿用alpha tag命名。
- `v0.3.8-alpha`公开Release资产为`bootstrap.sh`和`install.sh`。

本手册是新AI开发对话的启动上下文。它应记录当前状态、稳定规则和高价值经验。详细时间线进入`docs/development-log.md`。
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

## 6. 防错规则和Release经验

以下规则用于防止反复出现的开发失败，属于长期规则，必须保留在手册中。

### 6.1 可避免失败类型

1. **脚本变量作用域。** `ts`、`out`、`run_id`等shell变量不会自动进入Python heredoc。必须通过环境变量传入，或在Python内部生成。每个脚本只使用一个规范run id。
2. **源码锚点。** 锚点不确定、重复、被半补丁移动，或位于生成式shell模板中时，必须先审计真实源码。
3. **替换纪律。** 优先使用函数级、章节级、块级或AST级整体替换。Python测试和函数默认按AST定位整个`def`替换。Markdown默认按heading整节替换。shell模板默认替换整个生成函数或heredoc块。除稳定版本常量外，不要再依赖单行或局部字符串锚点。
4. **辅助函数语义。** 写测试或补丁前先读helper定义。不能把期待“函数名”的参数当作任意文本边界使用。
5. **正则边界。** 正则补丁只能用于稳定且已验证的边界。测试和函数通常应整块替换。
6. **pytest前marker检查。** 进入pytest前必须验证目标marker已出现、旧marker已消失，避免半补丁进入长测试。
7. **重改动两阶段。** 涉及installer、wrapper、profile或Release资产的改动，应先只补丁和测试。focused/full tests通过后，第二阶段再commit、tag、push、merge或重建Release资产。
8. **验收标准必须对应用户可见缺陷。** 不能把兼容fallback写成修复。Plan mode问题的验收是写入`plan_mode_reasoning_effort = "high"`并确认TUI不再显示`medium`，不只是proxy内部把`medium`映射成`high`。
9. **集成面属于每个任务。** 凡是可能影响用户路径的开发任务，都必须显式考虑install、upgrade、uninstall、rollback、生成wrapper、用户配置文件、Release资产和VM/user-path验证。
10. **运行期观察优先于猜测。** terminal、wrapper和Codex TUI行为必须先用隔离命令验证，再补丁。本轮通过普通命令验证了Windows Terminal标题OSC有效，也确认tab颜色不属于当前wrapper可控范围。
11. **测试环境污染。** 脏的开发shell可能让full tests因为补丁无关原因失败。p2.10a36中，`DEEPSEEK_PROXY_MODEL`、`DEEPSEEK_PROXY_FORCE_MODEL`、`DEEPSEEK_PROXY_IMAGE_PROVIDER`、`DEEPSEEK_PROXY_IMAGE_DOWNLOAD`以及真实provider API key等环境变量改变了默认模型和provider行为，导致与文档补丁无关的full tests失败。在把full tests失败当作补丁证据前，必须记录相关环境覆盖，用sanitized环境重跑失败子集和full tests，然后再判断责任在补丁还是本机环境。
12. **AnyCodeX未来命名边界。** CoDeepSeedeX仍是当前项目名和公开产品名。AnyCodeX是未来计划名和潜在未来品牌名，不是当前代码、命令、tag、branch、安装器、wrapper、公开路径或面向用户文档名称。在维护者明确批准重命名任务前，不要把AnyCodeX引入面向用户的表面。未来架构工作可以在仅面向开发者的规划文档中把目标描述为AnyCodeX级通用provider架构。
### 6.2 Release专项规则

- 不要猜运行时版本文件路径。运行时文件是`deepseek_responses_proxy/app.py`。
- 不要假设只有一个Python文件包含版本字符串。运行时代码和测试都可能包含版本字符串。
- 版本文件职责分离：运行时public/internal版本、PEP440包版本、版本一致性测试、CLI输出测试。
- 运行时版本元数据采用双轨规则。用户从公开Release tag安装时显示该公开`v~`tag和发布时绑定的内部`p~`tag。开发机从`master`运行时，public保持当前公开`v~`直到下一次Release，internal随最新内部tag前进。
- Release脚本必须幂等且可续跑。
- push默认走HTTPS并设置timeout，避免SSH 22端口卡死。
- 公开Release tag应靠后推送，避免半发布状态。
- `gh release view --json`不得依赖当前gh不支持的字段，例如`isLatest`。
- Release notes正文不得重复GitHub Release标题。
- 文档重构必须同步测试契约，不要为了旧测试保留幽灵文档。
- 开发者手册不是历史档案馆，长期规则留在这里，详细流水写入`docs/development-log.md`。

### 6.3 upgrade和uninstall范围规则

凡是可能影响用户安装态的开发任务，都必须在设计阶段同时检查install、upgrade和uninstall。至少要判断是否涉及一键bootstrap、`scripts/install.sh`、`dsproxy upgrade`、生成的`dsproxy`或`codex`wrapper、`~/.codex/config.toml`、本地env文件、manifest-backed rollback、source archive fallback和Release资产。

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

## 11. 当前大版本摘要：p2.10 / v0.3.8-alpha

p2.10对应当前`v0.3.8-alpha`公开alpha Release线，以及发布后的内部加固工作：

- 安装器provider表面清理，包括显式区分Zhipu / BigModel、Z.AI和Qwen / DashScope区域入口。
- 安装器体验加固，包括方向键菜单、紧凑来源日志、引用heredoc、source archive fallback、版本元数据保留和图像live验证。
- 配置和profile体验加固，包括`set-model`成为model API主入口、post-config proxy刷新、provider验证语义和DeepSeek兼容effort表面。
- Codex wrapper启动加固，包括fail-closed proxy route启动、`plan_mode_reasoning_effort = "high"`、manifest-backed uninstall rollback和用户路径验证。
- WeClaw-facing契约，包括`profile status --json`、`status --weclaw-json`、dsproxy统一维护profile effort、effective model字段、model conflict诊断和context窗口来源分离。
- Codex tab标题行为加固，最终有效设计为：wrapper准备对应route，在Codex启动后启动有限标题keeper，前台运行真实Codex，记录keeper PID，Codex返回后kill并wait keeper，同时保留真实Codex返回状态。
- 文档纪律，包括移除幽灵文档、同步当前状态，以及后续补丁强制优先采用函数级、块级、章节级或AST级整体替换。

p2.10a38后的已验证基线：

- `master = origin/master = e572677`。
- `p2.10a38-version-metadata-name-boundary = e572677`。
- `p2.10a34-title-keeper-cleanup = 280f14b`。
- `v0.3.8-alpha = dfdc629`，当前GitHub Release，非draft且非pre-release。
- 公开Release资产仍为`bootstrap.sh`和`install.sh`；p2.10a36及后续内部文档/元数据任务不重建资产。
- 真实HOME wrapper刷新已通过，包含keeper PID清理，且不再使用`exec "$REAL_CODEX" "$@"`。
- `deepseek-thinking` profile状态健康，`model=deepseek-v4-flash`，DeepSeek侧effort为`max`，Codex profile侧effort为`xhigh`。
## 12. 新对话启动检查

修改前先做只读审计：

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.8-alpha^{}
git rev-parse --short p2.10a26-wrapper-start-plan-mode-hardening^{}
git rev-parse --short refs/tags/v0.3.5^{} || true
gh release view v0.3.8-alpha --json tagName,name,isDraft,isPrerelease,targetCommitish,assets
```

新对话优先读取`docs/developer-handbook.md`。需要回溯时再读`docs/development-log.md`。

## 13. 安装和回退入口

LatestRelease bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

tag fallback：

```bash
tag="v0.3.8-alpha"
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

不要把未测试或认证失败的model provider写成unsupported。model API矩阵完成后，应进入专项架构分支，评估CoDeepSeedeX哪些层可复用，哪些层与DeepSeek强绑定。建议分支为`work/p2.10-generalized-provider-architecture-audit`。该评估至少覆盖provider adapter、`reasoning_content`等reasoning/thinking字段、stream事件归一化、model catalog元数据、Codex `/model`展示，以及将CoDeepSeedeX升级为更通用AnyCodeX式provider架构的整体方案。

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

- 下一条主设计线建议从`work/p2.10-generalized-provider-architecture-audit`开始。
- 审计必须先只读抓证据，不得凭记忆猜源码。第一步应审计`app.py`、`cli.py`、运行时配置加载、stream转换、model catalog、provider config、tool bridge、测试和文档。
- 目标是评估CoDeepSeedeX是否应重构为AnyCodeX式通用provider架构。
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

## p2.10a17安装器菜单渲染

方向键菜单不能依赖长原始文本在终端中正确换行。每个选项都应渲染为受终端宽度限制的一行，打印前先截断，并对选中项使用整行高亮。列表中存在的数字快捷键应立即返回，包括用于跳过或返回的`0`。全局菜单帮助提示每次安装只显示一次，引导配置块之间应有明显视觉分隔。

## p2.10a18极简方向键安装器UI

安装器菜单必须只有一个实际生效的`read_menu_choice_from_tty()`实现。不要留下重复shell函数定义，因为Bash会使用后定义版本并静默覆盖预期渲染器。引导式安装菜单只使用方向键：`↑/↓`或`j/k`移动，`Enter`确认，`Backspace`返回或跳过。TTY菜单不再宣传或实现数字/text fallback。辅助提示和默认值提示应使用淡色，bootstrap中与安装器重复的依赖检查结果应写入日志，不再在可见界面重复打印。

## p2.10a18 CLI版本元数据来源

CLI版本元数据必须直接使用从`deepseek_responses_proxy.app`导入的常量。声明的内部版本优先于HEAD上已有的p-tag。不要通过`from deepseek_responses_proxy import app`读取版本元数据，因为包级`app`名称可能指向FastAPI应用对象，而不是`deepseek_responses_proxy.app`模块。否则CLI可能静默回退到git tag推断，导致源码测试通过但CLI仍显示上一内部tag。

## p2.10a19安装器菜单列对齐

选中和未选中菜单行必须让选项编号保持在同一视觉列。由于选中标记使用`▶ `，未选中行的占位前缀应使用两个空格，而不是三个空格。该规则应由安装器文本级测试覆盖。

## p2.10a20安装器密钥输入语义

密钥输入必须区分“用户新输入的密钥”和“空输入并保留已有密钥”。当存在默认密钥时，空输入不能被报告为新收到的字符，也不能像用户刚粘贴密钥一样触发验证。optional、hidden、keep existing等辅助提示应使用淡色。Codex wrapper提示应说明安装后用户可运行`codex --profile deepseek`或`codex --profile deepseek-thinking`，并由wrapper处理本地dsproxy后台启动或刷新。

## p2.10a21安装器wrapper说明位置

特定问题的解释文本应由菜单渲染器打印在问题下方，并位于全局按键提示之前。不要在调用菜单前单独打印问题解释，否则解释会在视觉上和问题本身脱离。

## p2.10a22安装器端口标签和effort表面

安装器UI应把8000profile称为`Non-Thinking`，不要称为`Stable`，因为用户面对的是DeepSeek thinking模式差异，不是release稳定性差异。CoDeepSeedeX自身的profile安装和升级路径不应再为DeepSeek profile写入`medium`。`low`和`medium`只作为Codex或旧命令兼容输入保留，并归一化为DeepSeek侧`high`。

## p2.10a23安装器运行期调用覆盖

安装器测试不能只断言调用字符串存在，还必须断言被调用的shell函数已定义且先于调用位置。image API验证这类运行期分支可能通过`bash -n`，但在真实交互中仍因`command not found`失败。pre-release安装测试会反复重建并移动同一个公开alpha tag，因此受管理安装目录刷新时应使用强制tag获取，避免因`would clobber existing tag`中断。


## p2.10a24安装器输出与图像live验证

安装器TTY输出应采用类似Pixi的“人类可读进度”和“详细日志”分离原则：紧凑分区、淡色解释行、Logo附近不显示原始来源URL，并在`Install logs`区块统一展示bootstrap和install日志。Image API配置改为显式live验证路径：先提示会生成一张安全测试图且可能消耗provider额度，然后将生成结果保存到`/tmp`。不要再把非生成式image probe作为引导式安装器的验证门槛。

### p2.10a25安装器体验规则

source archive安装路径不能依赖`.git`提供版本元数据。安装器应尽量解析目标ref对应commit，并通过dsproxy wrapper加载的env文件传递给运行时。已有非git安装目录时，应直接进入source archive fallback，不要先打印git clone fatal。Codex Plan mode可能显示`medium`，proxy端会将该请求映射为DeepSeek侧`high`。

### p2.10a26 wrapper启动、Plan mode与uninstall规则

CoDeepSeedeX管理的Codex profile必须采用fail-closed启动语义。用户执行`codex --profile deepseek`或`codex --profile deepseek-thinking`时，wrapper必须先启动对应proxy路由，并验证对应`dsproxy status`成功。如果启动和状态检查均失败，wrapper必须输出清晰错误，不能继续进入连接空端口的Codex TUI。

DeepSeek Codex profile必须同时写入`model_reasoning_effort`和`plan_mode_reasoning_effort`。其中`plan_mode_reasoning_effort`固定为`high`，因为Codex原生Plan mode会读取这个独立配置键。不能再把Plan mode显示`medium`仅描述为由proxy侧别名修复。

uninstall必须在manifest存在`CODEX_WRAPPER_BACKUP`时恢复原Codex命令。任何wrapper重写都必须保留rollback语义：先删除CoDeepSeedeX wrapper，再把备份移动回原wrapper路径。


## p2.10a28 dsproxy统一维护WeClaw profile契约

CoDeepSeedeX / `dsproxy`是Codex profile文件和DeepSeek运行配置的权威维护者。WeClaw不得直接修改`~/.codex/config.toml`，也不得从私有文件推断model、effort、context窗口、token、cost、pricing、balance或compaction状态。

`dsproxy config set-effort max`在DeepSeek侧保存`DEEPSEEK_REASONING_EFFORT=max`，在Codex profile侧写入Codex兼容的`model_reasoning_effort = "xhigh"`。`xhigh`继续作为兼容输入，归一到DeepSeek `max`。`low`、`medium`、`minimal`和`none`作为兼容输入，在该proxy路径下归一为DeepSeek/Codex `high`。

机器可读契约入口：
- `dsproxy profile status [profile] --json`
- `dsproxy profile set-effort <profile> <effort> --json`
- `dsproxy status [thinking] --weclaw-json`

WeClaw status契约中，token、pricing、cost、balance、辅助token和compaction等尚未完成精确数据源审计的字段，必须以结构化`available=false`或`missing=[...]`返回，不能让WeClaw自行猜测。


## p2.10a29 WeClaw运行时契约统一

`dsproxy`必须向WeClaw暴露model和context的source-of-truth字段，而不是让WeClaw解析Codex私有文件。WeClaw-facing契约必须区分：
- `codex_model`：Codex profile中声明的model。
- `effective_model`：dsproxy实际选择并发送给上游的model。
- `force_model_enabled`：`DEEPSEEK_PROXY_FORCE_MODEL`是否覆盖Codex请求model。
- `model_conflict`：Codex profile model是否与实际上游model不一致。

当`model_conflict=true`时，WeClaw应展示`effective_model`，只把`codex_model`作为诊断细节显示。

Context字段必须区分Codex token级声明和dsproxy char级运行时控制。Codex profile中的`model_context_window`和`model_auto_compact_token_limit`是token级声明。`/v1/proxy/status.context`中的runtime compaction/trimming是char级行为。除非明确标注单位和来源，否则不得混合这些值。

源码更新后，已安装Codex wrapper可能仍停留在旧版本。`dsproxy profile refresh-wrapper --json`会根据install manifest刷新CoDeepSeedeX-managed wrapper，同时保留manifest-backed rollback元数据。未知用户自有wrapper不得静默覆盖，除非操作者显式传入`--force`。


## p2.10a30-p2.10a34 wrapper、profile和WeClaw契约收口

Managed Codex profile的`model`值必须与该profile自己的有效上游模型一致。`dsproxy profile repair --managed-only --json`会通过`profile status`使用的同一profile契约计算每个profile的effective model，并修复`deepseek`和`deepseek-thinking`。`codex_model`、`effective_model`和`model_conflict`继续作为诊断字段保留。正常managed状态下，`model_conflict`应为false。

WeClaw-facing model和context契约由dsproxy维护。WeClaw应使用`effective_model`，检查`model_conflict`，并按明确source和unit消费context字段。Codex profile中的`model_context_window`和`model_auto_compact_token_limit`是token级声明。runtime compaction和trimming是char级行为，不能不标注来源就混合展示。

源码更新后，已安装Codex wrapper可能仍停留在旧版本。`dsproxy profile refresh-wrapper --json`会根据install manifest刷新CoDeepSeedeX-managed wrapper，同时保留manifest-backed rollback元数据。未知用户自有wrapper不得静默覆盖，除非操作者显式传入`--force`。

当前tab标题设计以p2.10a34为准。不要恢复更早的启动前标题或三次延迟标题策略。wrapper必须：
- 不在Codex启动前设置标题
- 启动并验证匹配的dsproxy route
- 在route准备完成后启动有限运行期标题keeper
- 即使stdout被重定向，只要`/dev/tty`可写，就允许写标题OSC
- 以前台命令运行真实Codex，不使用`exec`
- 记录keeper PID
- Codex返回后停止并等待keeper结束
- 返回原始Codex状态

本轮经验：
- Windows Terminal tab标题可通过向当前TTY写OSC修改，但Codex启动期可能再次覆盖标题。
- 后台任务stdout重定向到`/dev/null`时，不能用`[ -t 1 ]`作为写`/dev/tty`的唯一门禁。
- 固定时长不是生命周期边界。keeper必须绑定真实Codex命令生命周期，并通过PID清理。
- 不要在没有当前tab运行期机制证据时把tab颜色加入wrapper。`wt --tabColor`是new-tab或split-pane启动参数，不是已验证的当前tab wrapper控制能力。
- 后续wrapper和installer补丁应整体替换shell函数或生成wrapper模板，不要替换狭窄转义片段。

## p2.10a35 文档和替换纪律同步

p2.10a35是p2.10a34之后的文档和移交同步节点。它更新当前状态，压缩已经被后续推翻的wrapper标题实验记录，保留p2.10a34当前有效设计，记录整体替换规则，并准备下一对话移交。

不要把它当作公开Release任务。除非维护者明确进入Release流程，否则不得移动`v0.3.8-alpha`，也不得重建Release资产。

## p2.10a36 Release状态文档同步

p2.10a36用于把文档同步到已验证的GitHub Release状态。`v0.3.8-alpha`仍是`dfdc629`上的公开alpha Release tag，但当前GitHub Release状态是非draft且非pre-release。本次只更新当前状态表述和README迁移提示。

不要把它当作Release重建任务。不得移动`v0.3.8-alpha`，不得重建GitHub Release，也不得上传新的Release资产。

## p2.10a38 版本元数据和命名边界

p2.10a38把开发运行时internal version元数据更新为`p2.10a38-version-metadata-name-boundary`，并记录AnyCodeX未来命名边界。公开版本元数据仍保持`v0.3.8-alpha`。

这不是Release重建任务。不得移动`v0.3.8-alpha`，不得重建GitHub Release，也不得上传新的Release资产。

## p2.10a40 通用provider架构审计报告

p2.10a40是内部规划检查点，不是大规模运行时重构。它把只读证据审计整理为后续实现顺序，用于未来AnyCodeX级通用provider架构，同时保持当前项目名仍为CoDeepSeedeX。

基于证据的结论：

DeepSeek强绑定运行时接缝：

1. 运行时核心仍集中在大型`deepseek_responses_proxy/app.py`中。上游模型调用仍经过`DeepSeekClient`。
2. 运行时配置仍使用DeepSeek命名：`DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_PROXY_MODEL`、`DEEPSEEK_PROXY_FORCE_MODEL`、`DEEPSEEK_THINKING`和`DEEPSEEK_REASONING_EFFORT`。
3. thinking行为仍与DeepSeek强绑定。关键接缝包括`_deepseek_thinking_config`、`_repair_thinking_history_messages`、`_prepare_messages_for_deepseek`、`reasoning_content`以及DeepSeek ChatCompletions角色和tool-call修复。
4. CLI和安装器provider catalog比运行时更通用。它们已经区分DeepSeek、Kimi、Zhipu / BigModel、Z.AI、Qwen / DashScope区域endpoint和custom OpenAI-compatible provider。
5. Web search和image generation已有provider分发层，但它们是工具provider桥接，不是通用model provider抽象。
6. WeClaw-facing契约在内部provider架构演进期间必须保持稳定。不得破坏`effective_model`、`codex_model`、`model_conflict`、context window单位和profile repair契约。

实现顺序：

1. 先增加provider能力元数据。它应描述请求形态、reasoning策略、stream事件映射、tool-call约束、usage字段和model catalog行为。
2. 有元数据后再增加上游adapter接口。不要在一个补丁里全局重命名`DeepSeekClient`。应先引入adapter边界，再逐步迁移调用点。
3. 将reasoning/thinking策略从model provider中分离。DeepSeek的`reasoning_content`修复应成为一种策略，而不是所有provider的默认假设。
4. 将stream归一化从provider transport中分离。Responses stream事件应来自provider-neutral event model。
5. 工具桥接替换是相关但独立的层。Web search、image generation和未来第三方工具替换不应混入model provider adapter。
6. 每一步都必须运行sanitized focused tests和full tests。在审计环境变量覆盖前，不得把测试失败归因于补丁。

## p2.10a41 长期任务总线和WeClaw验收审计

本任务总线用于跨新对话和插入任务持续追踪主线。

当前优先级：

1. P0当前主线：WeClaw契约验收和缺口闭环。
2. P1后续方向：AnyCodeX级通用provider架构。
3. P2后续方向：只有当P0缺口已实现，或维护者明确延期后，才进入公开Release准备。

防偏移规则：

1. `return_to_p0_after_inserted_tasks=true`。
2. 文档同步、版本元数据更新、命名边界清理和Release状态修复等插入任务可以打断主线，但这些任务收口后，下一步必须回到最高优先级未完成任务。
3. 未来架构审计或重构不得挤占WeClaw契约验收，除非维护者明确调整任务总线优先级。
4. 每次handoff必须包含本任务总线、当前P0状态和未解决验收缺口。
5. 完成声明必须有证据：精确CLI或HTTP命令、JSON输出形态、字段来源、精确性状态、测试记录和剩余缺口。

P0 WeClaw验收清单：

1. 验证`config set-effort`和`profile set-effort`绝不向Codex profile写入`model_reasoning_effort = "max"`。
2. 验证`profile status --json`向WeClaw提供权威profile、model、effort、thinking、context-window和health字段。
3. 验证`status --weclaw-json`提供稳定的profile、model、context、token、pricing、cost和compaction健康字段，即使部分字段显式不可用。
4. 验证HTTP WeClaw端点是否存在，并确认其与CLI JSON等价或记录差异。
5. 验证pricing、cost、balance、token taxonomy、auxiliary token统计和compaction字段是已实现、部分实现、不可用还是缺失。
6. 验证`max`、`high`和兼容effort输入的隔离HOME测试。
7. 为WeClaw集成对话输出交付报告，包含精确命令、端点名、JSON样例、字段来源、精确性标记、超时建议和失败fallback策略。

## p2.10a43 effort JSON和刷新控制


本补丁继续保持P0 WeClaw验收主线。

契约变化：

1. `dsproxy config set-effort <effort> --json`现在被parser接受，用于保持CLI/help一致性。该命令原本就输出JSON，因此这是parser契约修复，不是输出格式变化。
2. `dsproxy config set-effort <effort> --no-refresh`和`dsproxy profile set-effort <profile> <effort> --no-refresh`会保存env和profile变化，但不刷新运行中的proxy进程。
3. no-refresh路径复用既有post-config apply禁用模式，并返回`post_config_apply.status = "skipped"`。
4. effort核心映射不变：DeepSeek/env effort可以是`max`，Codex profile effort必须是`xhigh`，兼容输入归一到DeepSeek `high`，`plan_mode_reasoning_effort`保持`high`。

WeClaw调用建议：

- 集成测试或非交互流程中，如只修改一个profile，使用`profile set-effort <profile> <effort> --json --no-refresh`。
- 如需保留legacy config命令路径，使用`config set-effort <effort> --profile <profile> --json --no-refresh`。
- 只有用户明确希望配置变更后刷新运行中的proxy进程时，才省略`--no-refresh`。

## p2.10a44 文档marker纪律清理

本补丁清理p2.10a43遗留的文档债务。

文档和补丁纪律：

1. 不得为了满足marker而加入仅服务于验证字符串的兼容说明。
2. 验证marker必须来自真实源码、真实测试和真实文档正文。
3. 如果验证规则和真实内容不一致，应修正验证规则或修正目标内容，不得加入没有项目语义的文字来满足marker。
4. 每次补丁前必须同时审计将修改的精确源码或文档片段、替换规则和验证规则。
5. required markers应尽量使用真实命令契约。对p2.10a43而言，真实契约是`dsproxy config set-effort <effort> --json`、`dsproxy profile set-effort <profile> <effort> --no-refresh`和`post_config_apply.status = "skipped"`。
