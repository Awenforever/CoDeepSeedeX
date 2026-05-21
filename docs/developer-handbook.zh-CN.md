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

不再维护`OPERATIONS.md`、`docs/install.*.md`、`docs/usage.*.md`、`docs/upgrade.*.md`、`docs/security.*.md`、`docs/troubleshooting.*.md`、`docs/handoff-for-developers.*.md`、`docs/custom_api_handoff.md`这类碎片文档。旧的分散release-note文档不得恢复；唯一例外是当前公开Release明确维护的累计Release-note源文件，目前为`docs/release-notes-v0.3.9-alpha.md`。若测试仍读取旧路径，应修改测试契约，而不是保留幽灵文档。

## 2. 项目身份与当前状态

- 本地项目路径：`~/projects/deepseek-responses-proxy`
- GitHub仓库：`Awenforever/CoDeepSeedeX`
- 主分支：`master`
- 当前公开Release：`v0.3.9-alpha`
- 当前公开Release提交：`80bb0ea`
- GitHub Latest Release：`v0.3.9-alpha`
- GitHub Release标题：`CoDeepSeedeX v0.3.9-alpha`
- GitHub Release状态：非draft，非prerelease，普通Latest Release
- GitHub Release标志：`isDraft=false`，`isPrerelease=false`
- Release资产：`bootstrap.sh`，`install.sh`
- 当前内部开发检查点：`p2.10a92-codex-native-compact-source-alignment`，准确提交用`git rev-parse --short p2.10a92-codex-native-compact-source-alignment^{}`解析
- 最新闭合文档同步检查点：`p2.10a92-codex-native-compact-source-alignment`
- 已完成P0基线检查点：`p2.10a48-weclaw-full-telemetry-contract = 2e0edd0`
- WeClaw状态：当前CoDeepSeedeX和WeClaw集成线已闭合。`v0.3.9-alpha`提升为Latest并完成验证后，WeClaw侧未回报阻塞问题。
- Release要求：如果使用WeClaw集成，`weclaw_dev`必须不低于`v0.1.9-alpha`。
- 没有明确Release更新任务时不得移动的公开tag：
  - `v0.3.9-alpha = 80bb0ea`
  - `v0.3.8-alpha = dfdc629`
  - `v0.3.7-alpha = 466706f`
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- 错误普通tag `v0.3.5`和`v0.3.9`必须不存在。

本手册是新开发对话的启动上下文。它应维护当前状态、稳定规则、任务总线、Release规则和高价值经验。详细时间线放入`docs/development-log.md`。
- 当前公开Release note同步检查点仍为`p2.10a83-deepseek-cache-accounting-contract`，直到明确更新`v0.3.9-alpha`。
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
13. **完整源码优先审计规则。** 涉及源码或文档修改时，优先要求维护者上传完整源码文件和源文档。如果直接上传不方便，只读审计命令应把相关源码和文档完整复制到`/tmp`文件，并列出这些文件让维护者上传。`grep`、`rg`和窄片段只能用于建立文件清单，不能作为补丁设计的主要依据。补丁设计必须基于真实已阅读的完整文件，或完整函数、模块、章节上下文。
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

### 8.1 工具桥接术语契约

Provider维护章节必须保留以下稳定术语，因为测试和后续维护会把它们作为锚点：

- Web search tool bridge
- Image generation tool bridge

Web search tool bridge可能执行live provider检查，并可能消耗quota。

Image generation tool bridge默认可以执行非生成式验证。真实图像生成必须显式执行：

```bash
dsproxy doctor providers --live --allow-spend
```

### 8.2 模型配置命令契约

文档和测试必须保留当前模型配置命令示例：

```bash
dsproxy config set-model deepseek-v4-pro
```

不要恢复旧式带连字符的配置命令。

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

## 11. 当前主线摘要：p2.10 / v0.3.9-alpha

p2.10覆盖从`v0.3.8-alpha`到已闭合的`v0.3.9-alpha` Latest Release，以及后续p2.10a81文档状态同步。

当前已验证公开Release基线：

- `v0.3.9-alpha = 80bb0ea`
- `p2.10a80-docs-release-latest = 80bb0ea`
- GitHub Release标题：`CoDeepSeedeX v0.3.9-alpha`
- GitHub Release状态：非draft，非prerelease，普通Latest Release
- Release资产：`bootstrap.sh`，`install.sh`
- 错误普通tag `v0.3.9`和`v0.3.5`不存在。
- p2.10a80公开Release安装下，`dsproxy --version`应显示`public version: v0.3.9-alpha | 80bb0ea`和`internal version: p2.10a80-docs-release-latest | 80bb0ea`。

当前开发检查点：

- `p2.10a81-handbook-current-state-sync`是本次手册同步后的内部文档/版本元数据检查点。
- 公开Release元数据仍锚定`v0.3.9-alpha = 80bb0ea`；本次文档节点不得移动公开tag或GitHub Release。
- 开发checkout运行时可显示`internal version: p2.10a81-handbook-current-state-sync | <checkpoint commit>`，但public版本行仍保持`v0.3.9-alpha | 80bb0ea`。

自`v0.3.8-alpha`以来的用户可见变化：

- WeClaw集成由dsproxy拥有的遥测契约支撑。WeClaw可以通过稳定CLI和HTTP接口消费profile、model、effort、context-window、usage聚合、pricing元数据、estimated cost、provider balance、auxiliary model-call accounting和compaction状态。
- `dsproxy status [thinking] --weclaw-json`在proxy可达时优先使用运行时`/v1/proxy/weclaw/status`端点，不可达时返回结构化unavailable字段。
- `dsproxy profile status <profile> --json`和`dsproxy profile set-effort <profile> <effort> --json`为集成客户端提供机器可读profile和effort状态。
- runtime payload guard字段以字符级dsproxy运行时行为暴露Compact和Trim进度。它们不能和token级context-window字段混合。
- DeepSeek profile-tokenizer accounting可作为本地显示和漂移分析数据。provider usage仍是计费权威。
- `dsproxy tokenizer sync deepseek --json`和`dsproxy tokenizer status deepseek --json`管理用户机tokenizer资源。
- prompt segmentation语义区分最新普通`user`、`user_history`、`tool_output`、`environment`、`system`、`developer`和compaction summary类别。
- prompt reconciliation现在暴露`details_origin_breakdown`，WeClaw Details可显示user、history、system、environment、tools schema和protocol overhead等token来源，而不是`classified~x/y`小计。
- Pricing和Cost契约对DeepSeek V4采用CNY优先。中文官方价格页是主价格源，英文USD价格保留为fallback和未来国际化支持。
- Session cost使用per-turn ledger，不得用当前活跃模型价格重算历史session。
- 当provider没有暴露可单独计价的reasoning output时，reasoning output cost必须显式标记为不可用。

`v0.3.9-alpha` Release要求：

- 如果使用WeClaw集成，要求`weclaw_dev >= v0.1.9-alpha`。

## 12. 新对话启动检查清单

任何修改前先进行只读审计：

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.9-alpha^{}
git rev-parse --short p2.10a80-docs-release-latest^{}
git rev-parse --short p2.10a84-token-first-compact-trim-contract^{} || true
git rev-parse --short refs/tags/v0.3.9^{} || true
git rev-parse --short refs/tags/v0.3.5^{} || true
gh release view v0.3.9-alpha --json tagName,name,isDraft,isPrerelease,targetCommitish,assets,publishedAt
gh api repos/Awenforever/CoDeepSeedeX/releases/latest --jq '{tag_name:.tag_name,name:.name,draft:.draft,prerelease:.prerelease,target_commitish:.target_commitish,assets:[.assets[].name]}'
dsproxy --version
```

预期当前公开Release基线：

```text
worktree clean
v0.3.9-alpha=80bb0ea
p2.10a80-docs-release-latest=80bb0ea
current_internal_checkpoint=p2.10a84-token-first-compact-trim-contract
GitHub Latest Release=v0.3.9-alpha
isDraft=false
isPrerelease=false
assets=[bootstrap.sh, install.sh]
public version: v0.3.9-alpha | 80bb0ea
internal version: p2.10a83-deepseek-cache-accounting-contract | <current checkpoint commit>
```

然后阅读`docs/developer-handbook.md`。只有需要历史回溯时再阅读`docs/development-log.md`。

## 13. 安装和fallback入口

Latest Release bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

指定tag fallback：

```bash
tag="v0.3.9-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

固定Release资产bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.3.9-alpha/bootstrap.sh | bash -s -- --install-ref v0.3.9-alpha
```

## 14. 长期主线任务清单

该清单是防止任务漂移的长期任务账本。每次规划决策、重要实现节点、Release准备或上下文移交后都必须更新。

| ID | 主线任务 | 预期指标 | 当前版本 / 锚点 | 当前状态 | 最近更新 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | WeClaw完整遥测基线 | WeClaw可通过dsproxy拥有的CLI/HTTP契约消费profile、model、effort、context、usage聚合、pricing、cost、balance、Details、tokenizer状态和compaction。 | `v0.3.9-alpha = 80bb0ea` | 已闭合 | 2026-05-19 | WeClaw侧未回报阻塞问题。v0.3.9-alpha提升为Latest后，VM安装和运行验证通过。 |
| P0.4 | Token shadow accounting和token-vs-char drift观测 | token级状态、本地tokenizer估算、provider usage和字符级payload guard保持明确分离。 | `p2.10a65`到`p2.10a68` | 已为DeepSeek profile-tokenizer accounting和prompt segmentation实现 | 2026-05-18 | provider usage仍是计费权威。本地tokenizer accounting用于显示和漂移分析。 |
| P0.5 | Semantic payload compaction加固 | 在改写用户意图或patch关键payload前，存在dry-run、canary、telemetry、rollback和禁止内容规则。 | `p2.10a52-semantic-payload-compaction-tui-plan` | 已规划，未激活 | 2026-05-18 | 没有具体需求重新打开前，不要实施。 |
| P0.6 | Codex TUI第三方profile命令兼容性 | 除非未来auto-compact证据证明不同，manual compact路径仍按普通Responses流量兼容。 | `p2.10a53-tui-compact-path-evidence-sync` | 部分闭合 | 2026-05-18 | 没有新证据前不要添加`/responses/compact`。 |
| P1 | AnyCodeX级通用provider架构 | 在保持CoDeepSeedeX现有公开接口不破坏的前提下，形成基于证据的adapter和capability方案。 | `p2.10a40-generalized-provider-architecture-audit-report` | 已规划，未激活 | 2026-05-18 | AnyCodeX仍只是未来方向。 |
| P2 | `v0.3.9-alpha`公开Latest Release | GitHub Latest Release存在，`prerelease=false`，资产为`bootstrap.sh`和`install.sh`，Release notes不重复标题且包含WeClaw最低版本要求。 | `v0.3.9-alpha = 80bb0ea` | 已完成 | 2026-05-19 | Release notes包含`Requires weclaw_dev >= v0.1.9-alpha if WeClaw integration is used.` |
| Process | 全源码优先补丁纪律 | 补丁设计基于上传的完整文件或完整复制的源码/文档文件，而不是grep/rg片段。 | 手册规则6.1.13 | 生效中 | 2026-05-18 | `grep`和`rg`只能用于识别候选文件。 |

清单维护规则：

1. 每当新计划被接受、任务闭合或Release/移交改变活跃优先级时，都要更新该表。
2. 插入任务不得静默替代主线。插入任务闭合后必须回到该清单。
3. 移交内容必须包含该表或对活跃行的精确摘要。
4. 任务未取得日志、测试、tag、Release状态或下游接受反馈等证据前，不能声称完成。

## p2.10a64 pre-release升级与卸载文档收口

p2.10a64关闭P0后的审计缺口：pre-release升级已经由`dsproxy upgrade --alpha`、`--tag`和`--dry-run`覆盖，但完整产品卸载路径只存在于`scripts/install.sh --uninstall`，README中不够清晰。

当前决策：
- 保持产品级卸载入口在安装器中。
- 本节点不新增单独的`dsproxy uninstall`命令。
- 普通卸载文档化为`bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall`。
- 彻底移除文档化为`bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall --remove-files`。
- 明确卸载会移除受管Codex profiles、CoDeepSeedeX codex wrapper、dsproxy wrapper，并可选删除安装目录、env文件和安装manifest。
- 明确不得删除无关用户文件和非CoDeepSeedeX配置。

p2.10a64测试通过后，下一步进入VM验证以下组合用户路径：
- 通过`dsproxy upgrade --alpha`进行pre-release升级
- 通过`dsproxy upgrade --tag v0.3.9-alpha`进行显式pre-release升级
- 普通卸载
- 带`--remove-files`的完整卸载

## p2.10a63 P0发布状态文档同步

p2.10a63是`v0.3.9-alpha`发布到`p2.10a62`之后的docs/version-metadata-only收口节点。

公开pre-release更新后的当前可信状态：
- `master = origin/master = ac63043`
- `p2.10a62-weclaw-runtime-payload-guard = ac63043`
- `v0.3.9-alpha = ac63043`，这是公开annotated pre-release tag，peeled commit为`ac63043`
- `v0.3.8-alpha = dfdc629`，未移动
- 禁止出现的普通tag `v0.3.9`和`v0.3.5`仍不存在
- GitHub Release `CoDeepSeedeX v0.3.9-alpha`为非draft、pre-release，并包含`bootstrap.sh`和`install.sh`资产

P0闭环判断：
- CoDeepSeedeX侧P0实现已闭环。
- CoDeepSeedeX侧P0公开pre-release交付已闭环。
- 面向WeClaw的CoDeepSeedeX交付已闭环，现在等待WeClaw侧验证。
- WeClaw侧验证若发现新问题，应进入下一轮明确需求，默认不重新打开本轮P0范围。

## p2.10a62 WeClaw运行时payload guard

p2.10a62新增面向WeClaw的char级运行时payload guard契约。`runtime_payload_guard`提供可直接展示的Compact和Trim进度，来源是运行时内存快照，不依赖debug文件，也不使用token totals。

Compact numerator来自`_compact_chat_history_for_codex_like_persistence()`生成的最新进程内context compaction report，使用`after_chars`作为精确`runtime_context_builder`字符数。Trim numerator来自`DeepSeekClient.chat_completions()`中`_compact_deepseek_payload_context()`生成的最新进程内trimming report，使用`after_chars`作为精确`live_request_payload`字符数。如果当前运行route还没有观察到模型请求，契约会返回机器可读的unavailable原因和action。

不得从provider token totals、session totals、debug文件、SQLite或Codex私有profile数据推导Compact/Trim进度。

## p2.10a61 README结构清理

p2.10a61清理用户面向README，把用户工作流和开发历史分离。README只保留安装、验证、配置、provider、pricing、升级、WeClaw兼容性和文档入口。长Release历史、内部契约讨论和开发经验应进入`docs/development-log.md`或开发手册，不继续堆在README里。

本次清理还移除了shell注释被Markdown误解析成标题造成的结构污染，移除Brave作为用户面向provider设置入口，并保持公开pre-release `v0.3.9-alpha`仍指向`4a96283`，不移动公开tag。

## p2.10a60 WeClaw status上下文和价格契约

p2.10a60处理WeClaw第四轮status需求，修改位置在CoDeepSeedeX侧。运行时WeClaw status现在会提供可用的context numerator，但不伪造Codex内部context-window占用：当usage ledger存在最新primary上游调用时，`context_window.used_tokens`取该调用的provider `prompt_tokens`，并明确标注为`estimated_current_context_from_latest_upstream_prompt_tokens`。不得用`session_total` prompt tokens替代，因为那是累计消耗，不是当前上下文占用。

pricing status现在区分当前价格值、价格来源可信度、官方参考URL和官方cache刷新状态。内置兜底价格标注为`bundled_official_docs_snapshot`；只有通过`dsproxy pricing refresh --write-cache --json`持久化的cache才视为新抓取的`official_docs_html`来源。cost估算会暴露pricing source kind、source URL、source trust和official pricing availability，避免WeClaw把默认估算展示为实时官方价格。

context limit现在增加`context_window.limit_explanation`，覆盖`display_limit_tokens`、`model_context_window_tokens`、`auto_compact_token_limit`和model catalog context值。这是dsproxy维护的750k与1M等差异解释：WeClaw应使用`display_limit_tokens`作为展示分母，把`model_context_window_tokens`作为完整profile窗口。如果出现950k这类其他分母，必须映射到这些显式字段之一，否则应视为当前dsproxy契约外部来源。

## p2.10a59 WeClaw token归因边界契约

p2.10a59记录WeClaw第三轮status展示所需的token归因边界。审计结论是，dsproxy可以报告provider返回的聚合usage总量，也可以报告dsproxy模型调用purpose的精确归因。但当前没有经过审计的tokenizer，也没有per-prompt-segment ledger，因此不能拆分user、tool、environment、history等prompt子类token。

契约变更：

1. `tokens.taxonomy.version`更新为`3`。
2. `tokens.attribution.provider_usage_totals`标记聚合provider字段为精确。
3. `tokens.attribution.purpose_attribution`标记dsproxy的`purpose`、`call_index`、`request_id`和model归因为精确。
4. `tokens.attribution.prompt_subcategory_split`明确返回`available=false`、`precision=unavailable`和`reason=provider_usage_is_aggregate_without_prompt_subcategory_breakdown`。
5. `tokens.prompt_subcategory_split`镜像同一不可用契约，方便WeClaw消费。
6. `tokens.attribution.context_window_used_tokens`明确保持不可用，并指向`context_window.used_tokens`。
7. 本节点不引入tokenizer，不估算user/tool/env/history tokens，也不从session totals推导context-window used tokens。

边界：WeClaw可以展示精确聚合provider totals和精确purpose级totals。不得展示伪造的prompt子类token拆分。

## p2.10a58受保护官方价格刷新

p2.10a58为WeClaw第三轮实现受保护的价格刷新路径。当前V4价格来源是DeepSeek官方文档的人类HTML页面`https://api-docs.deepseek.com/quick_start/pricing`，不是稳定价格API。旧的`pricing-details-usd`和`pricing-details-cny`页面仍描述`deepseek-chat`和`deepseek-reasoner`旧价格，不能作为V4价格来源。

契约新增内容：

1. `dsproxy pricing refresh --json`现在会抓取并校验DeepSeek官方价格HTML，但默认不写缓存。
2. `dsproxy pricing refresh --json --write-cache`会把校验通过的价格原子写入用户价格缓存，或写入显式`--cache-path`。
3. refresh失败时保留旧缓存，并返回结构化`reason`、`error_type`、`source_url`、`source_kind`、`writes_cache=false`和`old_cache_preserved=true`。
4. 当价格源包含metadata时，`pricing show --json`可报告`source_url`、`source_kind`、`fetched_at`、`expires_at`、`ttl_seconds`和`is_stale`。
5. 实现明确标注来源为`official_docs_html`，不把它伪装成稳定API。
6. 默认refresh行为不修改项目内`config/pricing.json`。

本节点不实现vendor-stable pricing API，因为p2.10a58审计没有发现可用于V4价格的稳定官方价格API。

## p2.10a57 WeClaw第三轮契约基础补强

p2.10a57是WeClaw第三轮需求的低风险契约基础节点。它保持p2.10a55兼容性，优先补机器可读诊断，而不是直接实现高风险token估算、live pricing refresh或启用semantic payload compaction。

契约新增内容：

1. WeClaw-facing profile和runtime status新增`diagnostics`，包含`degraded_fields`、`warnings`和`actions`。
2. `context_window.used_tokens`仍不可用，但新增稳定的`used_tokens_action`和`used_tokens_precision=unavailable`。
3. `context_window.model_catalog`在managed Codex profile存在可读`model_catalog_json`时，可按effective model绑定模型上下文窗口。不可用时返回`reason`和`action`。
4. pricing契约新增`source_url`、`ttl_seconds`，并稳定`refresh`对象，包含`action`、`source_kind`、`requires_live_network`和`writes_cache=false`。
5. `dsproxy pricing show --json`返回当前静态价格缓存。`dsproxy pricing refresh --json`已存在，但只返回结构化`not_implemented`，不联网、不写缓存。
6. runtime WeClaw status将`compaction.semantic_compaction`镜像到顶层`semantic_compaction`，并为rollout状态补充`action`和`missing_events`。
7. 本节点不从session usage推断context used tokens，不在没有tokenizer时拆分prompt子类，不实现official live pricing refresh，也不启用semantic payload compaction。

Release状态：不移动公开Release tag，不创建GitHub Release，不重建Release资产。

## p2.10a55 WeClaw运行时status契约闭环

p2.10a55修复WeClaw真实接入后的第二轮full telemetry缺口。核心运行时错误是`GET /v1/proxy/weclaw/status`使用`create_app()`闭包参数里的`store`和`deepseek_client`，但真实运行对象位于`app.state.store`和`app.state.deepseek_client`。

本次契约变化：

1. 运行时WeClaw status改为从`app.state.store`聚合usage，因此Codex/ACP请求写入运行中SQLite usage ledger后，可以通过`tokens.last_turn`、`tokens.session_total`和`tokens.auxiliary_model_calls`展示。
2. 运行时WeClaw status改为通过`app.state.deepseek_client`查询balance。没有API key时返回可操作的`not_configured`，而不是泛化的client unavailable。
3. balance不可用响应新增`status`、`provider`、`reason`、`action`、`updated_at`、`currency`、`amount`和`display`。
4. cost响应通过`usage_available`、`pricing_available`、`pricing_stale`、`reason`、`missing`和pricing时间字段区分usage、pricing和stale pricing问题。
5. context-window响应新增`used_tokens=null`、`used_tokens_available=false`和`used_tokens_source=not_reported`，避免WeClaw从session totals推断context usage。
6. model-conflict响应新增`display_hint`、`diagnostic_hint`和`user_visible=false`，普通WeClaw status可以隐藏内部模型差异诊断，verbose status后续可展示。
7. runtime WeClaw端点不可达时，CLI fallback status也同步返回新的context和balance不可用字段。

本补丁不移动公开`v0.3.9-alpha` Release tag，也不重建Release资产。

## p2.10a54 token shadow accounting计划

p2.10a54是文档和版本元数据同步节点，用于记录一个关键决策：dsproxy不应直接把现有char级运行时compaction替换为token级触发。更稳妥的做法是在semantic payload compaction实现前，先增加token shadow accounting和token-vs-char漂移观测层。

### 决策

保留当前dsproxy运行时payload保护的char口径：

1. persistent compaction继续作为proxy侧payload安全阀。
2. trimming继续作为proxy侧硬保护。
3. `runtime_compaction`和`runtime_trimming`继续报告`unit=chars`。
4. 现有char保护继续覆盖序列化payload、tool output、JSON、reasoning content和function arguments，即使token估算不可用也不能失效。

在semantic payload compaction之前新增token shadow accounting：

1. 从Codex profile和Codex status暴露token级context window值。
2. provider返回的usage仍作为token和cost事实来源。
3. 本地token估算只能作为estimate，必须明确confidence和source。
4. 报告token-vs-char漂移，判断char保护是过早、过晚还是基本对齐。
5. WeClaw展示必须拆分为token级context window和char级proxy payload guard，不得混成一个进度条。

### 契约边界

未来status和WeClaw契约必须区分：

```json
{
  "context_window": {
    "unit": "tokens",
    "limit_tokens": 750000,
    "used_tokens_reported": null,
    "source": "codex_profile|codex_status|provider_usage"
  },
  "runtime_payload_guard": {
    "unit": "chars",
    "effective_trigger_chars": null,
    "max_context_chars": null,
    "source": "dsproxy_runtime"
  },
  "token_shadow": {
    "available": false,
    "estimated": true,
    "input_tokens_estimated": null,
    "confidence": "low|medium|high",
    "source": "local_estimator|provider_usage|codex_status"
  },
  "drift": {
    "token_to_char_ratio": null,
    "risk": "unknown|early_char_compaction|late_char_compaction|aligned"
  }
}
```

具体字段可在实现时调整，但单位边界不能弱化。token级context window、char级payload guard、provider usage和cost attribution必须保持分离。

### 实现前置审计

实现semantic payload compaction之前，必须先审计并定义：

1. 每条route可获得哪些token来源：Codex status、provider usage、本地估算或无。
2. 本地估算是模型相关还是通用近似。
3. 如何标注估算值，避免被误认为provider usage。
4. compact turn如何归入usage和cost。
5. WeClaw如何展示token context、char payload guard、compact events和cost。
6. token估算和char保护分歧时，漂移预警如何显示。

### 后续触发策略

不要一步切换到token触发。安全顺序应为：

1. 只观测。
2. 报告token shadow值和drift。
3. 当token风险和char风险分歧时增加warning。
4. 基于真实trace评估。
5. 最后才考虑chars或token-risk任一触发的双阈值策略。

这样既保留现有安全保护，又修正Codex token窗口和dsproxy char保护之间的语义漂移。

## p2.10a53 TUI compact路径证据同步

p2.10a53是文档和版本元数据同步节点，用于记录p2.10a52之后的CodexTUI人工验证证据。不实现新的运行时代码，不移动公开Release tag，也不重建Release资产。

### 已捕获证据

在隔离`CODEX_HOME`和临时工作目录下，`codex --profile deepseek`人工TUI验证确认：

1. TUI可以用`deepseek`profile启动，并进入dsproxy-backed provider。
2. 短请求`reply ok exactly`可以正常通过profile返回。
3. 手动`/compact`可以成功，并显示`Context compacted`。
4. 先前人工矩阵已观察到`/fork`可以fork当前chat。
5. `/status`可以显示Codex侧token级上下文信息。
6. compact路径抓取没有在TUI transcript中发现`responses/compact`或`/responses/compact`标记。
7. Codex侧日志显示`codex.op="compact"`、`session_task.compact`、`model_client.stream_responses_api`、`wire_api=responses`、`http.method="POST"`和`api.path="responses"`。
8. 8000端口监听进程是本项目`deepseek_responses_proxy.app:app`的uvicorn进程，proxy access log显示普通`POST /v1/responses HTTP/1.1`请求。

### 更新解释

当前证据表明，在Codex CLI `0.130.0`和`codex --profile deepseek`下，手动`/compact`走普通Responses路径，不走专用`/responses/compact`路径。因此，当前没有证据要求dsproxy实现`/responses/compact`兼容面。

该结论只覆盖短会话中的手动`/compact`。它不能证明接近`model_auto_compact_token_limit`时的Codex auto-compact也走同一路径。auto-compact仍未验证，因为本次没有把会话推到token阈值附近。

### P0.6剩余工作

P0.6仍保留以下未闭环项：

1. 接近token阈值时的auto-compact路径抓取。
2. 多次compact和长会话稳定性。
3. 启用payload级debug trace后审计compact prompt和摘要质量。
4. compact turn的usage和cost归因。
5. WeClaw是否需要把compact turn与普通turn分开展示。

除非后续证据表明auto-compact或新版CodexCLI调用`/responses/compact`并失败，否则不应优先实现`/responses/compact`兼容端点。

## p2.10a52 semantic payload compaction和TUI兼容性计划

p2.10a52是计划和文档同步节点，不实现semantic payload compaction，不等同于TUI矩阵验证完成，不移动公开Release tag，也不重建Release资产。

### 范围

本节点记录两个插入任务，避免它们覆盖当前WeClaw任务总线：

1. `P0.5 semantic payload compaction hardening`：默认排在WeClaw第二轮需求之后、AnyCodeX级架构工作之前。若TUI compact验证发现高风险，可提升优先级。
2. `P0.6 Codex TUI third-party profile command compatibility`：对`codex --profile deepseek`执行隔离TUI命令矩阵，验证原生`/compact`、auto-compact、`/fork`、`/resume`、`/model`、`/status`、`/diff`、`/review`、approval、sandbox等命令。

### 当前单位边界

Codex profile中的context字段是token级声明。`model_context_window`和`model_auto_compact_token_limit`必须按tokens理解。dsproxy运行时compaction、trimming和semantic payload compaction是char级payload保护。WeClaw和CLI展示时不得把token窗口和char预算合并成一个进度条，除非明确标注单位和来源。

### semantic payload compaction需求

实现前必须确认：

1. 可压缩对象：初始只允许低风险flattened tool transcript、重复长终端输出、长pytest输出和重复shell日志。
2. 禁止压缩对象：用户需求、任务计划、补丁脚本、git状态、commit/tag/Release状态、根因结论、测试断言、关键错误栈、API key语义和近期高价值上下文。
3. 可审计性：每个dry-run和applied事件必须记录message index、semantic type、risk level、retention markers、压缩前chars、压缩后chars、移除chars和原始payload是否保留。
4. usage和cost影响：provider返回的token usage仍是事实来源。cost估算仍来自usage ledger和pricing cache。除非引入经审计的tokenizer或provider前后对照，否则不得声称精确节省tokens。
5. WeClaw影响：可新增独立semantic payload compaction字段，必须标注`unit=chars`、mode、安全状态、候选数、应用数、移除chars和rollout blockers。该字段不得混入token级context window。
6. debug和观测：`debug budget`、long-session observability、runtime status和WeClaw status必须暴露semantic dry-run和applied事件，同时不遮蔽现有persistent compaction和trimming字段。
7. 回退：默认保持dry-run。启用必须有显式环境变量、canary检查和本地不变量检查。异常或无收益压缩必须返回原始messages。

### CodexTUI兼容性需求

TUI矩阵至少验证`/help`、`/status`、`/model`、`/compact`、auto-compact、`/fork`、`/resume`、`/diff`、`/review`、`/approval`、`/sandbox`和`/clear`。

矩阵必须记录每个命令是本地命令、普通Responses请求、`/responses/compact`请求、OpenAI或ChatGPT私有能力、session store依赖、provider filtering依赖，还是需要dsproxy兼容接管。

如果第三方profile下原生`/compact`或auto-compact失败，不能假设dsproxy的char级persistent compaction会自动接管。只有请求真实经过dsproxy兼容路径时，dsproxy才有机会接管。后续设计必须基于证据选择inline compact、实现`/responses/compact`兼容面，或增加wrapper/integration级保护和恢复路径。

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

p2.10a49后的当前优先级：

1. P0当前状态：WeClaw full telemetry contract第一版基线已在p2.10a48完成，并已被WeClaw侧认可用于初步集成。
2. P0下一步：等待WeClaw第二轮审计需求。后续在新对话继续，任何补丁前必须先做只读状态审计。
3. P1默认后续方向：如果没有激活的WeClaw第二轮任务，则进入AnyCodeX级通用provider架构审计或重构规划。
4. P2后续方向：只有维护者明确要求Release时才进入公开Release准备。

防偏移规则：

1. 文档同步、版本元数据更新、命名边界清理和Release状态修复等插入任务可以打断主线，但这些任务收口后必须回到任务总线优先级。
2. 未来架构审计或重构不得破坏已经验收的WeClaw契约表面。
3. 每次handoff必须包含本任务总线、当前P0状态、已认可字段、精确性边界和待提出的WeClaw第二轮需求。
4. 完成声明必须有证据：精确CLI或HTTP命令、JSON输出形态、字段来源、精确性状态、测试记录和剩余缺口。

p2.10a48后的WeClaw已认可基线：

1. `config set-effort`和`profile set-effort`不会向Codex profile写入`model_reasoning_effort = "max"`。
2. `profile status --json`向WeClaw提供权威profile、model、effort、thinking、context-window和health字段。
3. `status --weclaw-json`和运行时HTTP WeClaw status提供profile、model、context、token taxonomy、usage聚合、pricing、cost、balance和compaction状态。
4. HTTP WeClaw端点已验收：
   - `GET /v1/proxy/weclaw/profile-status?profile=deepseek-thinking`
   - `GET /v1/proxy/weclaw/status?profile=deepseek-thinking`
5. 已可直接消费字段包括`model.effective_model`、`model.codex_model`、`model.model_conflict`、`model.force_model_enabled`、`effort.user_facing`、`effort.deepseek_reasoning_effort`、`effort.codex_model_reasoning_effort`、`context_window.effective_safe_window_tokens`、`tokens.last_turn`、`tokens.session_total`、`tokens.auxiliary_model_calls`、`pricing`、`cost`、`balance`和`compaction`。
6. 精确性边界：provider返回的token总量和dsproxy purpose归因可以报告。cost来自dsproxy pricing cache估算。user/tool/environment/history等prompt子类拆分仍保持not-reported或unavailable，除非后续新增经过审计的tokenizer层。
7. 检查model attribution时必须使用隔离或sanitized测试环境，因为导出的`DEEPSEEK_PROXY_MODEL`和`DEEPSEEK_PROXY_FORCE_MODEL`会按设计改变effective model行为。

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

6. 稳定手册规则必须放入编号章节，或放入带明确版本号的历史小节。不要在编号章节和历史小节之间留下无编号孤岛。

## p2.10a45 手册章节结构清理

本补丁基于英文和中文手册全文清理章节层级。

结构决策：

1. `Provider bridge terminology contract`不是独立顶级章节，应归入第8章，因为它定义provider和工具桥接术语。
2. `模型配置命令契约`不是独立顶级章节，也应归入第8章，因为它定义provider和model配置命令契约示例。
3. 稳定手册规则必须归入编号章节，按版本记录的实现说明继续保留在`p*`历史小节中。
4. 后续若讨论文档结构，应优先读取全文。正则或grep片段不足以支撑章节层级判断。

## p2.10a46 WeClaw契约最终验收

p2.10a46完成P0 WeClaw契约验收检查点。

最终状态：

- `master = origin/master = 3e6b922`。
- `p2.10a46-weclaw-usage-test-env-isolation = 3e6b922`。
- `v0.3.8-alpha = dfdc629`，未移动。
- 合并后工作区干净。
- 未移动公开Release tag，未创建GitHub Release，未重建Release资产。
- WeClaw focused acceptance全部通过。
- sanitized full tests通过，结果为`435 passed`。

已验收的WeClaw契约表面：

```text
CLI:
dsproxy profile status <profile> --json
dsproxy profile set-effort <profile> <effort> --json
dsproxy status [thinking] --weclaw-json

HTTP:
GET /v1/proxy/weclaw/profile-status?profile=deepseek-thinking
GET /v1/proxy/weclaw/status?profile=deepseek-thinking
```

已可直接消费字段：

- `model.effective_model`
- `model.codex_model`
- `model.model_conflict`
- `model.force_model_enabled`
- `effort.user_facing`
- `effort.deepseek_reasoning_effort`
- `effort.codex_model_reasoning_effort`
- `context_window.effective_safe_window_tokens`
- 明确标注`unit=chars`的runtime compaction和trimming字段

结构化降级字段：

- `tokens.last_turn`
- `tokens.session_total`
- `tokens.auxiliary_model_calls`
- `pricing`
- `cost`
- balance-in-status

测试隔离经验：

- 当usage ledger测试断言request-model attribution时，必须清理`DEEPSEEK_PROXY_MODEL`、`DEEPSEEK_PROXY_FORCE_MODEL`和`DEEPSEEK_MODEL`。
- 开发shell中的full-suite结果必须先清理model、provider、image、web-search和API key环境变量后再判断。
- 不能通过修改生产model选择语义来修复这类测试环境污染问题。

## p2.10a48 WeClaw完整遥测契约

p2.10a48在p2.10a46基础契约检查点之后重新打开P0，并实现面向WeClaw的第一版完整遥测契约表面。

已实现的契约变化：

- 运行时HTTP `GET /v1/proxy/weclaw/status?profile=deepseek-thinking`现在会把usage ledger聚合为`tokens.last_turn`、`tokens.session_total`和`tokens.auxiliary_model_calls`。
- 运行时HTTP WeClaw status现在提供pricing cache元数据、estimated cost字段和provider balance数据。
- CLI `dsproxy status thinking --weclaw-json`在proxy可达时优先透传运行时WeClaw status端点，不可达时才返回结构化不可用字段。
- token数量来自provider返回并写入dsproxy usage ledger，属于精确总量。
- cost字段来自dsproxy pricing cache估算，不等同于provider账单。
- user/tool/environment/history等prompt子类拆分在没有经过审计的tokenizer层之前，仍标记为provider不直接报告。

## p2.10a49最终移交同步

p2.10a49是p2.10a48 WeClaw full telemetry contract开发线完成后的最终移交同步节点。

最终移交状态：

- p2.10a49文档同步前，`master = origin/master = 2e0edd0`。
- `p2.10a48-weclaw-full-telemetry-contract = 2e0edd0`。
- `v0.3.8-alpha = dfdc629`，未移动。
- WeClaw侧已认可p2.10a48回报基线，并进入初步集成。
- WeClaw第二轮需求会在其审计后提出，并应在新对话继续。
- 本节点同步当前状态块、任务总线、development log和运行时internal version元数据，保证新对话移交连续。
- 本节点不是公开Release，不得移动`v0.3.8-alpha`，不得创建GitHub Release，也不得重建Release资产。

新对话启动要求：

- 先只读审计branch、HEAD、origin/master、工作区、`p2.10a49-final-handoff-sync`、`p2.10a48-weclaw-full-telemetry-contract`和`v0.3.8-alpha`。
- 优先读取`docs/developer-handbook.md`。
- 把p2.10a48视为WeClaw full telemetry第一版已认可基线。
- 只有拿到WeClaw第二轮明确审计需求后，才继续开发。


## p2.10a65 Profile tokenizer accounting

p2.10a65启动profile感知的tokenizer统计主线。该节点为DeepSeek profile增加dsproxy自有的本地tokenizer层，使用官方DeepSeek V3 tokenizer JSON资源和Python `tokenizers`包。

契约边界：

- Provider返回的`usage`仍然是计费和聚合prompt、completion、cache、reasoning token总量的权威来源。
- `tokens.profile_tokenizer`和`tokens.prompt_subcategory_split`是本地profile tokenizer估算，适合WeClaw展示和drift分析，但不能当作账单数据。
- prompt子类统计基于dsproxy组装payload后的message边界，统计message text、reasoning content和tool-call名称或参数。chat-template开销不分摊到子类。
- 不声称替换Codex TUI内部token统计。当前`codex --profile deepseek debug models`证据没有显示DeepSeek model catalog条目，因此dsproxy先为集成客户端提供并行的正确统计。
- char级`runtime_payload_guard`、Compact和Trim继续与token级profile统计保持分离。


## p2.10a66 Tokenizer resource installer sync

p2.10a66 changes tokenizer resource delivery from repository-bundled large JSON files to installer/user-machine synchronization. The runtime now looks for managed tokenizer resources under `DEEPSEEK_PROXY_TOKENIZER_RESOURCE_DIR` or `DEEPSEEK_PROXY_INSTALL_DIR/resources/tokenizers`, and the CLI exposes `dsproxy tokenizer status` and `dsproxy tokenizer sync deepseek --json`.

The official archive is still the DeepSeek token-usage documentation archive whose internal directory is named `deepseek_v3_tokenizer`. CoDeepSeedeX labels the local binding as `deepseek_official_current` to avoid claiming that it is a V4-specific tokenizer. Provider `usage` remains billing-authoritative; profile tokenizer accounting remains a local estimate for WeClaw display and drift analysis.


## p2.10a67 Status tokenizer contract consistency

p2.10a67 fixes the WeClaw status tokenizer contract boundary. `tokens.profile_tokenizer.available` now reports tokenizer resource and runtime binding availability, independently from whether the route has observed an assembled prompt. `tokens.profile_tokenizer.summary.available` reports whether an assembled prompt has been observed and summarized.

When the tokenizer resource is available but the route has not yet observed an assembled prompt, `tokens.prompt_subcategory_split.available` remains false with `reason=profile_tokenizer_available_but_no_observed_prompt` and `categories={}`. When the tokenizer resource is unavailable, the reason comes from the tokenizer contract, for example `profile_tokenizer_json_not_found`.

This prevents WeClaw from seeing a contradictory status where `dsproxy tokenizer status deepseek --json` is available but `tokens.profile_tokenizer.available` is false without a specific explanation.


## p2.10a68 Prompt Segment Ledger Audit

p2.10a68 fixes the prompt subcategory semantics for WeClaw Details. Codex can encode memory, environment, AGENTS instructions, tool-call transcripts, tool-output transcripts, and historical context as `role=user` messages. Therefore dsproxy must not classify every `role=user` message as the latest user input.

The tokenizer split now treats `user` as the latest ordinary user segment after excluding known Codex-injected environment and tool transcript markers. Earlier ordinary user segments go into `user_history`. `[tool call transcript]` and `[tool output transcript]` go into `tool_output`. AGENTS, memory, and environment-context user-role blocks go into `environment`.

The WeClaw contract also exposes `tokens.latest_prompt_segmentation` and `tokens.prompt_subcategory_split.latest_prompt_segmentation`, containing sanitized segment records with role, source, category, token_count, char_count, preview, and sha256. Full content must not be exposed in normal status.


## p2.10a69 Pricing Currency and Turn Ledger

p2.10a69 fixes the WeClaw Pricing/Cost contract. Pricing remains sourced from DeepSeek official USD prices, but dsproxy now exposes source currency, display currency, FX metadata, converted display amounts, and structured per-million-token price objects. When the account balance is CNY, status display contracts expose CNY amounts so WeClaw does not perform USD/CNY conversion.

Cost remains estimated, but it is explicitly sourced from the per-turn usage ledger (`usage_events.estimated_cost_usd`). Session cost is the sum of historical turn-level estimated costs and must not be recomputed from the currently active model price. The usage ledger now records route, effort, pricing model, pricing currency, pricing source kind, pricing updated timestamp, and per-turn price fields for new events.

Reasoning output cost is not split unless the provider exposes separate reasoning pricing. The contract reports `reasoning_cost_available=false` with a reason instead of asking WeClaw to infer it.


## p2.10a70 Pricing CNY Primary Source

p2.10a70 changes the DeepSeek pricing source priority. The Chinese official pricing page is the primary source for V4 Flash/Pro prices and uses CNY per million tokens. The English pricing page is retained as a USD fallback/i18n source.

Default bundled prices are now:
- deepseek-v4-flash: cache hit 0.02 CNY/M, cache miss 1 CNY/M, output 2 CNY/M.
- deepseek-v4-pro: cache hit 0.025 CNY/M, cache miss 3 CNY/M, output 6 CNY/M.

The p2.10a69 FX fields remain in the contract, but they are not the default DeepSeek CNY path. FX conversion is used only when the active pricing source is USD and the display currency is CNY. WeClaw must continue to consume dsproxy structured pricing/cost fields and must not perform its own currency conversion.

Primary pricing URL: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
Fallback/i18n pricing URL: https://api-docs.deepseek.com/quick_start/pricing/

## p2.10a71 Pre-release Release Notes Closeout

当前收口目标：在p2.10a71验证完成后，将当前master更新到`v0.3.9-alpha`。Release note必须累计覆盖自`v0.3.8-alpha`以来到当前预发布状态的功能变化，但保持面向用户，不写开发流水账。

应写入功能性变化：
- WeClaw上下文、runtime payload guard、Compact/Trim进度和context-window估算字段。
- DeepSeekprofile tokenizer统计，以及用户机tokenizer同步/状态命令。
- WeClaw Details的prompt分段语义，包括最新`user`、`user_history`、`tool_output`和`environment`。
- CNY优先的Pricing/Cost契约、DeepSeek中文官方价格源、cash估算和逐turn账本费用语义。
- provider未提供独立reasoning费用拆分时的显式不可用语义。

不写入开发过程细节：
- 内部p-tag列表，
- 测试数量，
- 文档维护本身，
- 命令脚本恢复过程，
- 实现过程中的中间错误，
- release note编辑过程。

`v0.3.9-alpha`Release note应在现有正文上累计更新，不能用一个短delta覆盖已有功能项。已有的`runtime_payload_guard`、Compact/Trim、context-window limit explanation、pricing refresh和WeClaw status contract等内容必须保留。

## p2.10a72 Handbook Latest-state sync

p2.10a72在`v0.3.9-alpha`收口和VM验证后同步英文与中文开发手册。这是仅文档状态修正节点。

该节点后的可信当前状态：

- `master = origin/master = 6ea67b2`
- `v0.3.9-alpha = 6ea67b2`
- `p2.10a71-docs-prerelease-notes = 6ea67b2`
- GitHub Release `CoDeepSeedeX v0.3.9-alpha`为非draft、非prerelease，并且是GitHub Latest Release。
- Release资产只有`bootstrap.sh`和`install.sh`。
- 错误普通tag `v0.3.9`和`v0.3.5`不存在。
- `dsproxy --version`的public和internal版本均指向`6ea67b2`。
- VM安装和运行验证通过。

该节点不移动公开Release tag，不重建Release资产，不创建GitHub Release。


## p2.10a73 WeClaw status primary-scope contract

p2.10a73为WeClaw状态消费分离latest primary模型调用、latest-any模型调用和auxiliary模型调用。该节点新增usage ledger `session_id`、`tokens.latest_primary_turn`、`tokens.latest_any_model_call`、`tokens.latest_auxiliary_call`、通过`--session-id`进行current-session过滤，并为Compact/Trim提供明确的`progress_*`字段。Pricing和折扣解析推迟到后续节点。


## p2.10a74 DeepSeek pricing discount contract

p2.10a74使DeepSeek pricing采用CNY优先并支持折扣元数据。

契约变化：

1. `dsproxy pricing refresh --json`默认使用中文官方价格页。
2. parser识别当前实际生效价、删除线原价、折扣标签、折扣率和官方折扣有效期。
3. `config/pricing.json`保存官方CNY内置快照，并使用当前实际生效价。
4. `pricing.effective_prices`、`pricing.original_prices`、`pricing.discount`和`pricing.prices_display`暴露给WeClaw。
5. WeClaw应展示当前实际生效价，不自行推断折扣窗口，也不使用当前价格重算历史turn成本。


## p2.10a75 upgrade, current-session cost, prompt segmentation, and retention progress

p2.10a75关闭WeClaw p89反馈的契约缺口：

1. `dsproxy upgrade`采用与WeClaw一致的同版本语义：检查远端release tag commit后，若目标public version和commit与当前运行时一致则跳过；若同public version但release commit不同则覆盖重装。`--force` / `--force-reinstall`可强制重装。
2. `cost.session`成为明确的current-session cost对象。route/profile累计不再被静默标记为session cost。
3. 传入`--session-id`时，prompt segmentation按session隔离，不会把route-latest旧session segmentation复用到新session。
4. Compact/Trim主进度字段表示信息保有率：压缩/裁剪后的chars除以原始未压缩chars。触发/容量进度另用`capacity_progress_*`字段表示。


## p2.10a76 Tokens aux and Details coverage contract

p2.10a76关闭WeClaw p92/p93反馈的契约缺口：

1. 当前session没有辅助模型调用时，`tokens.auxiliary_model_calls`仍返回明确的零对象：`available=true`、`scope=current_session`、`total_tokens=0`、`model_call_count=0`、`reason=no_auxiliary_model_call_in_current_session`。
2. `tokens.prompt_subcategory_split`新增相对`latest_primary_turn.summary.prompt_tokens`的覆盖率字段：`categories_sum_tokens`、`provider_reference_tokens`、`provider_reference_field`、`delta_tokens`、`coverage_complete`、`coverage_scope`、`coverage_basis`、`delta_reason`。
3. Details仍是本地profile tokenizer对dsproxy组装后message content和tool-call arguments的估算。除非`coverage_complete=true`，否则不能理解为provider prompt tokens的完整守恒分解。


## p2.10a77 Prompt reconciliation contract

p2.10a77将WeClaw Details从简单partial覆盖率扩展为prompt reconciliation：

1. `tokens.prompt_reconciliation`同时比较三种总量：`prompt_subcategory_split.categories_sum_tokens`、`local_full_observed_prompt_tokens`和provider返回的`latest_primary_turn.summary.prompt_tokens`。
2. 新增`delta_breakdown`、`delta_status`、`is_accounting_suspect`、`recommended_action`和脱敏后的`prompt_segment_audit`。
3. dsproxy不会把provider/local差额直接归入`other_prompt`，除非这些token对应可观测的prompt segment。
4. 如果本地可观测prompt token与分类合计一致，但provider prompt tokens显著更大，则dsproxy把差值标记为未解释的provider/template/tokenizer层差异，并建议`run_prompt_reconciliation_trace`。
5. 内置最小实验矩阵是live trace计划，不伪造实验结果。provider prompt usage必须通过真实provider调用获得。


## p2.10a78 Prompt delta root-cause accounting

p2.10a78将prompt reconciliation从`unknown`报警推进为本地根因账本：

1. dsproxy现在把完整DeepSeek chat payload传入profile-tokenizer accounting，不再只传`messages`。
2. `observable_payload.components`分别统计message content、serialized messages、tool schema、tool choice、response format、request options和完整serialized payload。
3. `local_full_observed_prompt_tokens`现在包含本地可观测的prompt-bearing API字段，例如`tools_schema`，而不只是message content。
4. `delta_breakdown.tools_schema_tokens`可以解释常见差值：provider `prompt_tokens`包含工具/函数schema，但Details分类只显示message content。
5. observable payload accounting之后仍剩余的provider差值会继续标记为provider/template/tokenizer overhead，不会归入`other_prompt`。


## p2.10a79 Details origin breakdown

p2.10a79将WeClaw侧Details契约从“分类小计”改为“来源拆分”：

1. `prompt_reconciliation.details_origin_breakdown`直接提供可显示的token来源：user、history、tool output、system、developer、compaction summary、environment、runtime injected、other prompt、tools schema、message/protocol overhead和provider residual。
2. `should_display_classified_total=false`；WeClaw默认不应显示`classified~x/y`小计。
3. 实测约8.1k差值的主因是`tools_schema_tokens`，剩余可见差值由message JSON/protocol/request-option overhead和少量provider/tokenizer residual解释。
4. `provider_residual`不能归入`other_prompt`；当`abs_tokens`在容差内时可隐藏。


## p2.10a80 Docs and latest release handoff

p2.10a80在p2.10a79之后更新公开/用户侧文档，并将现有`v0.3.9-alpha` Latest Release移动到当前master。累计Release notes同步维护在`docs/release-notes-v0.3.9-alpha.md`和GitHub Release页面。公开tag `v0.3.9-alpha`只在本release步骤中有意移动。

p2.10a80最终验证状态：

- `master = origin/master = 80bb0ea`
- `p2.10a80-docs-release-latest = 80bb0ea`
- `v0.3.9-alpha = 80bb0ea`
- GitHub Release `CoDeepSeedeX v0.3.9-alpha`为非draft、非prerelease，并且是GitHub Latest Release。
- Release资产严格为`bootstrap.sh`和`install.sh`。
- 错误普通tag `v0.3.9`和`v0.3.5`不存在。
- 更新Release前full tests已通过。

## p2.10a81 Handbook current-state sync

p2.10a81是p2.10a80之后的文档和运行时内部版本同步节点。它将手册启动状态从过期的`6ea67b2` / `p2.10a71-docs-prerelease-notes`修正为p2.10a80公开Release基线`80bb0ea`，明确当前累计Release-note源文件是`docs/`下唯一仍活跃的release-note文件，并将开发侧内部检查点推进到`p2.10a81-handbook-current-state-sync`。

本节点不得移动`v0.3.9-alpha`，不得重建GitHub Release，也不得重新上传Release资产。


## p2.10a82 Append-only upstream payload trace

p2.10a82新增可选的append-only上游payload trace，用于诊断Codex通过当前profile route实际发送给上游模型的内容。设置`DEEPSEEK_PROXY_PAYLOAD_TRACE_DIR`为`/tmp`下的绝对目录即可启用。

该trace仅限本地，默认关闭。每次`DeepSeekClient.chat_completions()`调用会写入一个JSON事件，包含脱敏后的原始payload、payload摘要、request purpose元数据、重复content hash、各role字符数、tools schema大小和context trimming report。该trace不改变prompt组装、模型选择、compaction、trimming、provider调用、pricing或Release元数据。

本节点只提供观测能力。它不是payload减冗余、prompt cache或semantic compaction实现。公开`v0.3.9-alpha`仍停留在`80bb0ea`。


## p2.10a83 DeepSeek cache accounting contract

Adds provider-authoritative DeepSeek prompt cache hit/miss accounting to the usage ledger, WeClaw status, and cost contract. Session, last-turn, and auxiliary cache sections expose request-level `prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, and cache hit ratio. Cost remains per-turn ledger based and uses hit/miss input prices rather than treating all prompt tokens as cache miss or cache hit. DeepSeek ChatCompletions payloads now set a stable hashed `user_id` by default and canonicalize tools schema ordering to protect DeepSeek context-cache reuse. Segment-level origin splits remain local estimates; provider cache hit/miss is request-level authoritative.

## p2.10a84 Token-first Compact/Trim context contract

p2.10a84将当前context-window契约从“展示auto-compact阈值”修正为“token-first展示真实模型窗口”。

规则：

1. 受管Codex profile在DeepSeek V4线保持`model_context_window = 1000000`。
2. 受管Codex profile只使用一个受管比例`auto_compact_ratio = 0.90`派生`model_auto_compact_token_limit`，默认阈值为`900000`。
3. WeClaw和CLI状态中的`context_window.display_limit_tokens`必须来自`model_context_window_tokens`，不能来自`model_auto_compact_token_limit`。
4. `model_auto_compact_token_limit`作为`auto_compact_threshold_tokens`暴露，只表示触发阈值，不表示context-window分母。
5. char级`runtime_payload_guard`、Compact和Trim字段继续作为`unit=chars`的fallback/debug payload guard存在，不能混入token级context window。
6. 旧的显式`--auto-compact-token-limit`输入只作为兼容参数接受，受管profile生成时会忽略该值并按比例派生阈值。

Release边界：本节点不移动公开`v0.3.9-alpha`，不重建Release资产，也不更新GitHub Release notes。

## p2.10a85 Compact prompt fingerprint and material classifier dry-run

p2.10a85为Codex-like persistent compaction增加只审计metadata。

规则：

1. `_compaction_prompt_messages()`新增脱敏`compaction_prompt_fingerprint`，用SHA-256标识准确compact prompt和material边界。
2. fingerprint只报告digest、计数和边界metadata，不能暴露原始compact material或retained recent message内容。
3. `compact_material_classifier_dry_run`只分类compaction material、retained recent verbatim messages和leading system/developer messages，不改payload。
4. `retained_recent_policy`显式暴露`_safe_recent_message_start()`边界，包括是否为了保留assistant tool_call/tool result对而回退边界。
5. runtime status可在compaction last-report metadata下暴露这些字段。它们仍是`unit=chars/messages`诊断字段，不能改变p2.10a84的token-first context分母。
6. 本节点不启用semantic payload compaction，不启用token-based runtime trimming，也不移动公开`v0.3.9-alpha`。

## p2.10a86 Compact runtime/status contract

p2.10a86稳定p2.10a85 Compact audit metadata的runtime/status契约面。

规则：

1. runtime WeClaw status暴露`runtime_payload_guard.compaction.compact_audit`，并在`compaction.compact_audit`下镜像。
2. `compact_audit`是可展示且脱敏的字段，只包含fingerprint、classifier dry-run和retained-recent-policy metadata。
3. 当`/v1/proxy/weclaw/status`不可用时，CLI legacy fallback会从`/v1/proxy/status.context.compaction.last_report`暴露`compaction.compact_audit`。
4. debug budget在compaction区暴露同一组audit metadata，便于本地运行时验证。
5. 该契约仍为`unit=chars/messages`，与p2.10a84 token-first context-window统计分离。
6. 本节点不启用semantic payload compaction，不启用token-based runtime trimming，也不移动公开`v0.3.9-alpha`。

## p2.10a87 Compact audit dry-run on skipped compaction

p2.10a87关闭p2.10a87运行态审计发现的可用性缺口。

规则：

1. 当policy未触发或消息过少导致compaction跳过时，`_compact_chat_history_for_codex_like_persistence()`也会附加脱敏Compact audit metadata。
2. 这不会调用模型，不会改变payload messages，也不会启用semantic payload compaction。
3. 生成的metadata保持`mode=dry_run`、`applied=false`、`raw_prompt_exposed=false`和`raw_material_exposed=false`。
4. 因此在普通未触发compaction的请求之后，runtime、CLI和WeClaw status也可以显示`compact_audit.available=true`，不再必须等待真正compaction事件。
5. compaction被禁用时仍报告disabled/unavailable，不伪造audit metadata。
6. 本节点不移动公开`v0.3.9-alpha`。

## p2.10a88 HTTP WeClaw Compact audit E2E regression

p2.10a88把p2.10a88运行态审计固化为HTTP端到端回归测试。

规则：

1. 测试必须用fake no-network DeepSeek client执行真实ASGI `POST /v1/responses`请求。
2. 同一个app实例随后查询`GET /v1/proxy/weclaw/status?profile=deepseek-thinking&include_balance=false`。
3. 断言必须覆盖`compaction.compact_audit`和`context_window.runtime.payload_guard.compaction.compact_audit`。
4. 普通未触发compaction的请求必须暴露`compact_audit.available=true`、`mode=dry_run`、`applied=false`和脱敏fingerprint metadata。
5. status payload不能暴露raw prompt或raw compact material。
6. 本节点不移动公开`v0.3.9-alpha`。

## p2.10a89 TRIM type enum, first-image protection, and token dry-run

p2.10a89回到原始TRIM清单主线。

规则：

1. `_compact_deepseek_payload_context()`现在输出脱敏`token_first_trim_dry_run`报告。
2. dry-run报告`unit=tokens`、显式类型枚举、item类型计数、类型token估算、候选裁剪目标和保护metadata。
3. 本节点中，生产context trimming仍保持现有char级硬保护；token-based trimming尚未实际启用。
4. message列表中观察到的第一个image payload会被保护，不参与context TRIM和最后兜底aggressive shrinking。
5. system、developer、AGENTS、environment和protocol类别的当前/最新静态块会被识别并保护；旧副本可在后续type-aware TRIM中处理。
6. status/report snapshot暴露`token_first_trim_dry_run`、`item_type_summary`、`protected_static_blocks`和`image_first_protection`。
7. dry-run metadata不得暴露raw message content、raw image payload或raw static block文本。
8. 本节点不启用semantic payload compaction，不启用token-based runtime trimming，也不移动公开`v0.3.9-alpha`。

## p2.10a90 Type-aware TRIM enablement

p2.10a90启用第一批生产类型感知context TRIM。

规则：

1. `token_first_trim_dry_run`继续可用且保持脱敏。
2. 生产TRIM现在对低风险文本payload应用类型级字符限制：`tool_result`、`log`、`pytest`、`traceback`、`diff`、`json`、旧文本、tool-call arguments和reasoning content。
3. 第一个image payload继续受保护，不参与普通TRIM、old-prefix compaction和aggressive shrinking。
4. 当前system/developer块，以及最新AGENTS/environment/protocol块继续受保护。
5. 状态面暴露`type_aware_trim`，包含applied计数、按类型汇总、limit和脱敏标记。
6. metadata不得暴露raw message content、image payload、static block文本或tool arguments。
7. `DEEPSEEK_PROXY_TYPE_AWARE_TRIM=0`可以关闭生产类型感知TRIM，但不关闭dry-run metadata。
8. 公开`v0.3.9-alpha`在完整清单完成前继续冻结。

## p2.10a91 Image semantic envelope

p2.10a91新增面向context TRIM的display-safe图像语义信封层。

规则：

1. 第一个被观察到的image payload继续受保护并保持原样。
2. 非保护image message可以被替换为semantic envelope文本，只记录message index、role、image count、media type提示、source shape、byte estimate和sha256。
3. `image_semantic_envelope`会暴露到context trim report、runtime payload guard snapshot和WeClaw status surface。
4. metadata不得暴露raw image payload、base64字符串、data URL或raw message content。
5. `DEEPSEEK_PROXY_IMAGE_SEMANTIC_ENVELOPE=0`关闭envelope report层；`DEEPSEEK_PROXY_IMAGE_SEMANTIC_ENVELOPE_TRANSFORM=0`保留report metadata但关闭payload替换。
6. 公开`v0.3.9-alpha`在完整清单完成前继续冻结。

## p2.10a92 Codex native Compact source alignment

p2.10a92将dsproxy本地Compact prompt对齐到Codex GitHub源码模板，并记录remote Compact边界。

源码证据：

1. 审计时观察到的`openai/codex` GitHub源码commit：`main`。
2. `codex-rs/core/src/compact.rs`引入`codex-rs/core/templates/compact/prompt.md`。
3. `codex-rs/core/src/compact.rs`引入`codex-rs/core/templates/compact/summary_prefix.md`。
4. `prompt.md` sha256：`ab0c334d4faca17e3afbb9b16967c1b2fdcc7242a9a0880af57949fa236d6d07`。
5. `summary_prefix.md` sha256：`e9b088e794a6bb9082ac053fcc760bd818d7e720ee4bcdc72c6e480de7b7cb0e`。
6. `run_inline_auto_compact_task()`从`turn_context.compact_prompt()`合成compact输入。
7. manual compact和mid-turn auto compact的`InitialContextInjection`行为不同。
8. remote compact端点存在，为`responses/compact`，但Codex通过provider能力门控。

运行时契约：

1. dsproxy在本地Compact user message中包含精确的Codex `prompt.md`文本。
2. dsproxy通过Compact metadata、compact audit、runtime payload guard和WeClaw status暴露`codex_native_source_evidence`、`compact_prompt_alignment`和`codex_summary_prefix`。
3. dsproxy可以声明本地prompt文本精确对齐。
4. dsproxy不得声称第三方DeepSeek route具备Codex原生remote compaction能力。
5. status metadata继续不暴露raw prompt和raw material。
6. 公开`v0.3.9-alpha`继续冻结。

## p2.10a94 Plan closure contract

p2.10a94是在公开更新`v0.3.9-alpha`之前的计划闭合契约节点。它只补齐低风险审计缺口，不改变高风险运行时触发模型。

规则：

1. Compact的retained recent元数据必须显式暴露latest incoming user、recent user/assistant消息和active tool-chain边界是否被保留。
2. semantic payload compaction除chars字段外，必须暴露token估算字段，并标明估算来源和精度。
3. semantic payload compaction必须暴露`pytest_success`、`pytest_failure`、`git_diff`、`api_response_json`等计划级类型别名；这些是契约标签，不代表高风险payload可以被改写。
4. image semantic envelope只是metadata-only封套。必须暴露`semantic_summary_unavailable=true`，不得声称已经完成OCR、caption或外部视觉摘要。
5. 本节点不改变生产Compact/TRIM触发语义：运行时硬保护仍是char级，token-first TRIM仍是dry-run/observability。
6. 本节点不得移动公开`v0.3.9-alpha`，不得更新GitHub Release，不得上传Release资产。
