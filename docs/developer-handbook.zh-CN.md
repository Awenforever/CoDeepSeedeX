# CoDeepSeedeX开发者手册

本文件是英文主手册`docs/developer-handbook.md`的中文镜像，给维护者阅读和核对使用。以后给AI的新对话启动上下文，应优先使用英文主手册。详尽历史流水账放在`docs/development-log.md`，只有需要回溯时再读取。

本手册不是历史档案馆，只保留当前运行模型、项目地图、Release规则、高价值经验和当前Hand-off状态。

## 1. 文档架构

用户文档：

- `README.md`：英文用户入口。
- `README.zh-CN.md`：中文用户入口。
- `TROUBLESHOOTING.md`：用户排障入口。

维护文档：

- `docs/developer-handbook.md`：英文主开发者手册，也是AI新对话主入口。
- `docs/developer-handbook.zh-CN.md`：中文镜像，给维护者看。
- `docs/development-log.md`：完整长期开发日志，需要历史回溯时读取。

不再维护`OPERATIONS.md`、`docs/install.*.md`、`docs/usage.*.md`、`docs/upgrade.*.md`、`docs/security.*.md`、`docs/troubleshooting.*.md`、`docs/handoff-for-developers.*.md`、`docs/custom_api_handoff.md`这类碎片文档。旧的分散Release note文档不得恢复。公开GitHub Release正文维护在GitHub Release页面；Release自动化可以使用`/tmp`临时notes文件，但仓库不得保留长期per-release note源文件。若测试仍读取旧路径，应修改测试契约，而不是保留幽灵文档。

## 2. 当前可信状态

- 本地项目路径：`~/projects/deepseek-responses-proxy`
- GitHub仓库：`Awenforever/CoDeepSeedeX`
- 主分支：`master`
- 当前公开Release：`v0.4.3-alpha`
- 当前公开Release类型：GitHub Latest普通alpha Release，`isPrerelease=false`
- 当前公开Release提交：`6a96593`
- GitHub Latest普通Release：`v0.4.3-alpha`
- GitHub Release标题：`CoDeepSeedeX v0.4.3-alpha`
- GitHub Release状态：`isDraft=false`，`isPrerelease=false`
- Release资产：`bootstrap.sh`，`install.sh`
- Release资产digest：
  - `bootstrap.sh` sha256：`257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4`
  - `install.sh` sha256：`81b509239c10c6a911350cda51b744daedb8f0077274d09a1c94519bc4450294`
- 当前内部开发检查点：`p2.19a25-docs-release-state-sync`
- 当前公开Release包含的最新运行时检查点：`p2.19a23-profile-drift-failclosed-guard`
- 最新闭合文档同步检查点：`p2.19a25-docs-release-state-sync`
- 最新闭合幽灵审计工具检查点：`p2.19a23-profile-drift-failclosed-guard`
- 最新闭合测试契约清理检查点：`p2.19a14-test-contract-pruning`
- 最新闭合provider alias边界检查点：`p2.19a15-provider-alias-boundary`
- 最新闭合legacy threshold边界检查点：`p2.19a16-legacy-threshold-boundary`
- 最新闭合wrapper path hygiene检查点：`p2.19a17-wrapper-path-hygiene`
- 最新闭合real-HOME profile model consistency检查点：`p2.19a19-real-home-profile-model-consistency`
- 最新闭合status JSON与upstream model leakage检查点：`p2.19a21-status-json-and-upstream-model-leakage`
- 最新闭合profile drift fail-closed guard检查点：`p2.19a23-profile-drift-failclosed-guard`
- 当前公开Release note同步检查点：`p2.19a23-profile-drift-failclosed-guard`
- WeClaw要求：如果使用WeClaw集成，要求`weclaw_dev >= v0.1.9-alpha`。
- 未经明确Release更新任务不得移动的公开tag：
  - `v0.4.3-alpha = 6a96593`
  - `v0.3.9-alpha = 82a4428`
  - `v0.3.8-alpha = dfdc629`
  - `v0.3.7-alpha = 466706f`
  - `v0.3.6-alpha = 7fd8fb6`
  - `v0.3.5-alpha = 53897ad`
- 错误普通tag `v0.4.0`、`v0.3.5`和`v0.3.9`必须不存在。

当前收口证据：

- 公开tag `v0.4.3-alpha = 6a96593`。
- 当前公开Release包含的内部检查点：`p2.19a23-profile-drift-failclosed-guard = 6a96593`。
- GitHub Release非draft、非prerelease。
- GitHub Latest API返回`v0.4.3-alpha`。
- Release资产只有`bootstrap.sh`和`install.sh`。
- 刷新后的Release线运行`dsproxy --version`应报告`public version: v0.4.3-alpha | 6a96593`。
- `p2.19a24`真实Codex入口复测已通过：故意把两个managed splitprofile漂移到`glm-5.1`后，入口路径会自动修复并使用`deepseek-v4-flash-ascend`，无403/access-denied、无默认模型泄漏、无`/tmp`wrapper链。
- 本次文档同步可能让`master`领先公开Release提交；公开`v0.4.3-alpha`tag必须保持在`6a96593`，直到后续明确Release更新任务。

## 3. 关键文件地图

- `deepseek_responses_proxy/app.py`：运行时核心、Responses兼容接口、DeepSeek/custom provider桥接、工具桥接、provider分发、版本元数据、debug trace。
- `deepseek_responses_proxy/cli.py`：`dsproxy`命令入口、配置、custom provider registry、provider设置、post-config刷新、doctor命令、升级逻辑。
- `scripts/install.sh`：安装器，负责installed checkout同步、venv、wrapper、Codex profile、guided UI、配置初始化和本地文件备份。
- `bootstrap.sh`：一键安装入口，负责依赖、install.sh获取和fallback。
- `scripts/codex-wrapper.bash`：适用时维护wrapper模板表面。
- `scripts/audit-ghost-contracts.py`：只读幽灵契约审计工具。
- `config/pricing.json`：内置价格快照。
- `experiments/model-catalog/deepseek-proxy-models.json`：托管模型目录。
- `tests/`：回归测试、文档契约测试、provider测试、安装器测试、升级测试和运行时契约测试。
- `README.md` / `README.zh-CN.md`：用户说明。
- `TROUBLESHOOTING.md`：用户排障。
- `docs/development-log.md`：完整时间线记录。

## 4. 当前用户可见Release面

`v0.4.3-alpha`当前覆盖以下用户可见内容：

1. 安装器和`dsproxy config wizard`
   - 语言选择属于guided flow。
   - Model API、Web search API、Image generation API和Codex wrapper使用同一套箭头键UI契约。
   - Web search和Image generation步骤使用各自的step-local hint，不再泄漏custom model provider摘要。
   - 完成页总结结果，正常安装保持一条命令完成。

2. Custom OpenAI-compatible provider
   - 用户可以设置仅用于显示和切换的provider name。
   - 支持多个custom providers和每个provider多个models。
   - active provider/model镜像到legacy env契约以保持运行时兼容。
   - 粘贴带`/chat/completions`的Base URL会归一化为OpenAI-compatible `/v1` base URL。
   - Model API验证使用已配置的provider/base URL/model，不再对custom provider回退到DeepSeek官方balance检查。
   - Model/API-key输入保护会拒绝URL、路径、控制字符和API-key-like字符串作为model id。

3. Codex兼容和wrapper可靠性
   - Codex CLI `< 0.134.0`使用`~/.codex/config.toml`里的legacy `[profiles.*]`表。
   - Codex CLI `>= 0.134.0`使用split profile files。
   - Managed profile repair必须保持当前Codex CLI要求的布局。
   - 生成的Codex wrapper必须解析真实Codex二进制，不能把`REAL_CODEX`指向另一个CoDeepSeedeX wrapper或`/tmp/codeepseedex-*`测试wrapper。
   - wrapper启动可以修复managed profiles，但若profile conflict仍存在，必须fail closed。

4. Status和诊断
   - `dsproxy profile status`一致报告profile source和profile layout。
   - legacy Codex profile table下，`context_window.codex_profile.source`必须是`codex_profile.legacy_profile_table`。
   - managed profile context保持`model_context_window=1000000`和`model_auto_compact_token_limit=900000`。
   - `dsproxy config show`和`dsproxy config test-api-key`显示validation method和URL，但不得记录API key材料。

5. Provider bridges
   - Web search tool bridge
   - Image generation tool bridge
   - Web search验证可能消耗quota。
   - Image generation默认验证不一定是真实生成；真实出图必须显式执行`dsproxy doctor providers --live --allow-spend`。

6. 安全和日志
   - API key在日志和status中必须保持redacted。
   - 真实provider E2E脚本不得记录签名图片URL、临时provider URL或query-string token。

## 5. 版本和tag规则

`dsproxy --version`必须输出两类版本来源：

```text
public version: v0.x.y-alpha | <public_release_commit>
internal version: p2.9aN-topic | <internal_commit>
```

从公开Release tag安装时，internal版本行报告切该Release时绑定的`p~`tag。开发机从`master`运行时，public版本保持最新公开Release，internal版本随最新内部`p~`tag前进。

公开Release tag在alpha阶段使用`v0.x.y-alpha`，不得创建不带`-alpha`的`v0.3.x`或`v0.4.x`公开tag。内部开发tag使用`p`前缀，不创建GitHub Release。

`pyproject.toml`中的包版本使用PEP440，例如`0.4.3a0`。

Release或文档同步常涉及：

- `deepseek_responses_proxy/app.py`
- `pyproject.toml`
- `tests/test_version_metadata.py`
- `tests/test_cli.py`
- `tests/test_docs_release_readiness.py`
- `tests/test_release_metadata_env_sanitization.py`

各文件职责不同，不能强制每个版本相关文件都包含public和internal tag。

### 版本语义健康规则

内部`p~`版本是语义检查点，不只是递增标签。必须主动管理：

1. 只有工作仍属于同一个连贯开发阶段时，才继续使用当前`pX.YaN`线。
2. 当既定计划已经闭合、新的主要技术阶段开始，或旧编号语义不健康时，应推进到新的`pX.(Y+1)a1`线。
3. 不要因为下一个整数可用，就一直在不健康的阶段名上继续堆叠补丁。
4. 阶段边界原因必须写入本手册和`docs/development-log.md`。
5. 公开`v*`Release tag与内部`p~`检查点分离，只有用户明确要求Release更新时才移动。

## 6. Release状态机

Release必须按状态机执行：

1. 只读审计branch、HEAD、origin/master、工作区、旧public tags、目标public tag、GitHub Release、版本字符串分布和测试文件存在性。
2. 同步版本元数据。
3. 运行静态检查和focused tests。
4. 运行full tests。
5. commit。
6. push工作分支。
7. push内部tag。
8. fast-forward master。
9. push master。
10. push公开Release tag。
11. 创建或更新GitHub Release并上传`bootstrap.sh`和`install.sh`。
12. 复核资产、tag、旧tag、Latest状态和错误普通tag。
13. 若改动影响安装态用户路径，必须进行VM或真实HOME验证。

push默认走HTTPS，不走SSH。所有网络步骤必须设置timeout。

GitHub Release notes正文不得重复Release标题。公开Release note必须面向用户、聚焦功能，并通过`/tmp`临时notes文件或GitHub API正文写入，不能在仓库中维护tracked Release note文件。

## 7. 防错规则和Release经验

### 7.1 可避免失败类型

1. **脚本变量作用域。** `ts`、`out`、`run_id`等shell变量不会自动进入Python heredoc。必须通过环境变量或参数传入。
2. **源码锚点。** 不从记忆补丁。锚点不确定、重复、被半补丁移动或位于生成式shell模板中时，必须先审计真实源码。
3. **替换纪律。** 优先使用函数级、章节级、块级或AST级整体替换。Python测试和函数按整个`def`替换。Markdown按整节或整文件替换。shell模板按整个生成函数或heredoc块替换。
4. **辅助函数语义。** 写测试或补丁前先读helper定义，不能误用参数语义。
5. **正则边界。** 正则补丁只用于稳定且已验证的边界。
6. **pytest前marker检查。** 进入pytest前确认目标marker已出现、旧marker已消失。
7. **重改动两阶段。** installer、wrapper、profile或Release变更，应先patch和test，通过后再commit、tag、push、merge或重建资产。
8. **验收标准必须对应用户可见缺陷。** 不能把兼容fallback写成用户可见缺陷修复。
9. **集成面属于每个任务。** 涉及用户路径的任务都必须检查install、upgrade、uninstall、rollback、wrapper、配置文件、Release资产和VM/user-path验证。
10. **运行期观察优先于猜测。** terminal、wrapper、Codex TUI和provider行为先用隔离命令验证。
11. **测试环境污染。** full tests失败前必须排除开发shell环境变量污染。
12. **AnyCodeX未来命名边界。** CoDeepSeedeX仍是当前项目名和公开产品名。AnyCodeX只是未来方向，不得进入当前用户表面。
13. **完整源码优先审计规则。** 补丁设计必须基于完整文件、完整函数、完整模块或完整章节上下文，不能只靠grep/rg片段。
14. **不要迎合旧测试。** 如果测试断言过时行为或幽灵文档，应修改测试契约，而不是保留死代码或死文档。

### 7.2 Release专项规则

- 不要猜运行时版本文件路径。运行时文件是`deepseek_responses_proxy/app.py`。
- 不要假设只有一个Python文件包含版本元数据。
- 运行时版本元数据是双轨：公开`v~`代表发布版本，内部`p~`代表开发检查点。
- Release脚本必须幂等且可续跑。
- push默认使用HTTPS并设置timeout。
- 公开Release tag应靠后推送，避免半发布状态。
- `gh release view --json`不得依赖当前gh不支持的字段，例如`isLatest`。
- Release notes不得重复GitHub Release标题。
- 文档重构必须同步测试契约。
- 开发者手册不是历史档案馆，长期规则留在这里，详细流水写入`docs/development-log.md`。

### 7.3 upgrade和uninstall范围规则

凡是可能影响用户安装态的开发任务，都必须在设计阶段同时检查install、upgrade和uninstall。至少判断是否涉及一键bootstrap、`scripts/install.sh`、`dsproxy upgrade`、生成的`dsproxy`或`codex`wrapper、`~/.codex/config.toml`、本地env文件、manifest-backed rollback、source archive fallback和Release资产。

## 8. 安装器、wizard和本地文件覆盖规则

安装器覆盖本地文件前必须备份：

- `~/.config/deepseek-responses-proxy/env`
- `~/.local/bin/dsproxy`
- `~/.local/bin/codex`
- `~/.codex/config.toml`
- installed checkout中的dirty patch和untracked files

未知用户自有`codex`或`dsproxy`不能静默覆盖。已知CoDeepSeedeX wrapper可以备份后刷新。

Installer TTY菜单使用箭头键guided UI：`↑/↓`或`j/k`移动，Enter选择，Backspace返回。不要恢复旧式数字TTY提示。非TTY fallback必须明确且machine-readable。

Guided UI hint必须属于当前步骤。Model API详情不得泄漏到Web search或Image generation提示中。

## 9. Provider和custom API handoff

Provider相关行为必须在runtime、CLI、installer、README和tests中保持一致。

关键路径：

- `deepseek_responses_proxy/app.py`
- `deepseek_responses_proxy/cli.py`
- `scripts/install.sh`
- `README.md`
- `README.zh-CN.md`
- `TROUBLESHOOTING.md`

Custom OpenAI-compatible provider规则：

- Provider name只用于显示和切换。
- Model name必须是准确的上游model id。
- Base URL必须是上游OpenAI-compatible `/v1` endpoint。
- 一个provider可以有多个models。
- 用户必须能够新增provider、给已有provider新增model、切换active model。
- 运行时兼容通过legacy env mirror保持：`DEEPSEEK_PROXY_MODEL_PROVIDER=custom`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_PROXY_MODEL`和`DEEPSEEK_API_KEY`。

Provider bridge稳定术语：

- Web search tool bridge
- Image generation tool bridge

Web search验证可能执行live检查并消耗quota。Image generation默认验证不一定是真实出图。真实出图必须显式执行：

```bash
dsproxy doctor providers --live --allow-spend
```

不要新增用户未要求的`dsproxy config test-provider --kind web-search|image --provider <name>`命令。

智谱和Z.AI图像端点必须区分。Provider诊断不能把通用图像API key误判为所有图像provider均已配置。Qwen/DashScope provider诊断必须尊重区域图像endpoint。

文档和测试必须保留当前模型配置命令示例：

```bash
dsproxy config set-model deepseek-v4-pro
```

不要恢复旧式带连字符的配置命令。

## 10. Codex profile和wrapper契约

Codex兼容取决于版本：

- Codex CLI `< 0.134.0`：使用`~/.codex/config.toml`里的legacy `[profiles.deepseek]`和`[profiles.deepseek-thinking]`表。
- Codex CLI `>= 0.134.0`：使用split profile files：`~/.codex/deepseek.config.toml`和`~/.codex/deepseek-thinking.config.toml`。

Wrapper契约：

- `REAL_CODEX`必须解析到真实Codex binary或Node入口，不能指向另一个CoDeepSeedeX wrapper。
- `/tmp/codeepseedex-*`路径不得被选为真实Codex。
- 找不到有效真实Codex时必须fail closed，而不是生成递归wrapper。
- Managed profile repair必须保持当前Codex版本需要的profile布局。
- Legacy profile status必须报告：
  - `profile_source=legacy_profile_table`
  - `codex_profile_layout=legacy_profile_tables`
  - `context_window.codex_profile.source=codex_profile.legacy_profile_table`

## 11. VM GitHub代理经验

VMware NAT中GitHub不可达时，不要猜测。应审计route、DNS、curl、git、proxy listener和Windows host listener。

已验证路径：

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> Jilianyun
```

VM中可以使用GitHub-specific proxy设置。若GitHub Release资产和`git ls-remote`稳定，jsDelivr失败不应作为阻断项。

## 12. 新对话启动检查清单

任何修改前先进行只读审计：

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.4.3-alpha^{}
git rev-parse --short p2.19a15-provider-alias-boundary^{} || true
git rev-parse --short p2.19a10-guided-installer-contextual-hints^{}
git rev-parse --short refs/tags/v0.4.0^{} || true
git rev-parse --short refs/tags/v0.3.9^{} || true
git rev-parse --short refs/tags/v0.3.5^{} || true
gh release view v0.4.3-alpha --repo Awenforever/CoDeepSeedeX --json tagName,name,isDraft,isPrerelease,targetCommitish,assets,publishedAt
gh api repos/Awenforever/CoDeepSeedeX/releases/latest --jq '{tag_name:.tag_name,name:.name,draft:.draft,prerelease:.prerelease,target_commitish:.target_commitish,assets:[.assets[].name]}'
dsproxy --version
```

预期当前公开Release基线：

```text
worktree clean
master=origin/master=<current p2.19a25 documentation sync commit>
v0.4.3-alpha=6a96593
p2.19a23-profile-drift-failclosed-guard=6a96593
GitHub Latest Release=v0.4.3-alpha
isDraft=false
isPrerelease=false
assets=[bootstrap.sh, install.sh]
bootstrap.sh sha256=257456d2724519bf94ad09f4dce038ac23e8fd5ab9da4b117f1ae637164590a4
install.sh sha256=81b509239c10c6a911350cda51b744daedb8f0077274d09a1c94519bc4450294
public version: v0.4.3-alpha | 6a96593
internal version: p2.19a25-docs-release-state-sync | <current internal tag commit>
```

然后阅读`docs/developer-handbook.md`。只有需要历史回溯时再阅读`docs/development-log.md`。

## 13. 安装和fallback入口

Latest Release bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

指定tag fallback：

```bash
tag="v0.4.3-alpha"
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

固定Release资产bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/download/v0.4.3-alpha/bootstrap.sh | bash -s -- --install-ref v0.4.3-alpha
```

产品级卸载仍由安装器负责：

```bash
bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall
bash ~/.local/share/deepseek-responses-proxy/scripts/install.sh --uninstall --remove-files
```

卸载不得删除无关用户文件和非CoDeepSeedeX配置。

## 14. 长期主线任务清单

| ID | 主线任务 | 预期指标 | 当前版本 / 锚点 | 当前状态 | 最近更新 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| Release | `v0.4.3-alpha`当前Latest | GitHub Latest Release存在，`isPrerelease=false`，资产只有`bootstrap.sh`和`install.sh`，Release正文不重复标题。 | `v0.4.3-alpha = 6a96593` | 已闭合 | 2026-06-08 | 包含p2.19 custom provider registry、guided UI、Codex兼容/wrapper加固、status JSON、辅助模型泄漏修复、profile漂移fail-closed guard和真实Codex入口验证。 |
| Installer UX | 安装器和wizard一致性 | step-local hints、箭头键菜单、Backspace导航、简洁验证摘要、无跨步骤model摘要泄漏。 | `p2.19a10-guided-installer-contextual-hints` | 已闭合 | 2026-06-07 | VM真实HOME验证通过。 |
| Custom providers | 多custom OpenAI-compatible providers和models | 用户可新增provider、新增model、切换active provider/model，并按配置的`/models`验证。 | `p2.19a1`到`p2.19a6` | 已闭合 | 2026-06-06 | active provider/model镜像到legacy env以保持运行时兼容。 |
| Codex compatibility | 版本感知profile布局和安全wrapper | Codex `<0.134`使用legacy tables；Codex `>=0.134`使用split files；`REAL_CODEX`不指向wrapper。 | `p2.19a7`到`p2.19a9` | 已闭合 | 2026-06-07 | 真实HOME wrapper执行通过。 |
| WeClaw | 完整遥测基线 | WeClaw可消费dsproxy拥有的profile、model、effort、context、usage、pricing、cost、balance、Details、tokenizer和compaction契约。 | `v0.3.9-alpha = 82a4428` | 已闭合 | 2026-05-24 | 使用WeClaw时要求`weclaw_dev >= v0.1.9-alpha`。 |
| Managed tool routing | Web/image provider bridge | 可暴露Web search tool bridge和Image generation tool bridge状态与诊断。 | `p2.14a2`到`p2.14a8` | 已闭合 | 2026-05-26 | 真实SerpAPI web E2E和Zhipu provider bridge验证已完成；未观察到Codex native image_generation。 |
| Token/context | token-first Compact/TRIM和tokenizer accounting | provider usage仍是计费权威；本地tokenizer accounting用于展示/漂移分析；token和char单位保持分离。 | `p2.10a65`到`p2.13a5` | 已闭合 | 2026-05-24 | 不得混淆token context window与char payload guard。 |
| Process | 全源码优先补丁纪律 | 补丁设计基于完整文件或完整源码/文档上下文，而不是grep片段。 | 手册规则7.1.13 | 生效中 | 2026-06-07 | 过时测试应更新契约，不保留幽灵行为。 |

清单维护规则：

1. 每当新计划被接受、任务闭合或Release/移交改变活跃优先级时，都要更新该表。
2. 插入任务闭合后必须回到该清单。
3. 移交内容必须包含该表或对活跃行的精确摘要。
4. 任务未取得日志、测试、tag、Release状态或下游接受反馈等证据前，不能声称完成。


### Provider alias边界

- `qwen-us`是当前显式地域模型provider，应继续保留在README/CLI模型provider指引中。
- `glm`、`qwen_us`、`qwen_us_virginia`、`dashscope_us`和Brave WebSearch只作为隐藏/向后兼容alias保留，除非后续验证线明确重新提升为公开入口。
- `dsproxy config set-api-key`保留为deprecated兼容命令；用户可见指引应优先使用`dsproxy config set-model`。


### Legacy threshold边界

- managed auto-compact threshold配置保持ratio-first：`model_auto_compact_token_limit`由`model_context_window * 0.90`生成。
- `model_auto_compact_token_limit`、`auto_compact_token_limit`和`auto_compact_ratio`是当前生成/状态字段，不是legacy输入。
- 历史`750000`和`0.75`只能保留在历史记录或负向守卫中。
- legacy absolute-threshold环境变量输入只作为兼容证据，managed profile必须报告为ignored。
- 维护版ghost audit规则不得把当前90%字段归类为旧阈值债务。


### Wrapper path hygiene

- 生成的CoDeepSeedeX Codex wrapper不得把另一个CoDeepSeedeX wrapper作为`REAL_CODEX`。
- `dsproxy profile refresh-wrapper`只有在能从`CODEEPSEEDEX_REAL_CODEX`、`PATH`或常见npm/nvm位置解析出非CoDeepSeedeX真实Codex可执行文件时，才允许从污染的manifest `REAL_CODEX`中恢复。
- 如果没有安全真实Codex可执行文件，wrapper refresh必须fail closed。
- `/tmp/codeepseedex-*`测试HOME wrapper不得作为真实用户wrapper manifest的真实Codex目标。


### Real-HOME profile model consistency

- `DEEPSEEK_PROXY_MODEL`中的active upstream model对两个managed Codex profile均为权威来源，除非显式配置`DEEPSEEK_PROXY_THINKING_MODEL`覆盖`deepseek-thinking`。
- `config set-model`、`set-api-key`、custom-provider激活和guided wizard不得让`deepseek`与`deepseek-thinking` split profile残留不同upstream model。
- managed Codex profile的provider name仍保持本地dsproxy provider（`deepseek-proxy`和`deepseek-thinking-proxy`）；上游provider/base URL/model由dsproxy env契约承载。
- real-HOME repair必须保持Codex 0.134+ split profile布局，不得重新引入legacy `[profiles.deepseek*]`表。


### Status JSON与辅助模型泄漏

- `dsproxy status --json`是普通proxy status JSON的显式机器可读别名。
- `dsproxy status thinking --json`和`dsproxy status --json thinking`都必须可用。
- `--weclaw-json`仍是独立的WeClaw-facing契约，不得与普通proxy status JSON混淆。
- 在`DEEPSEEK_PROXY_FORCE_MODEL=1`下，agent-liveness judge等辅助调用必须跟随`DEEPSEEK_PROXY_MODEL`，不得静默选择另一个provider model。
- status表面应暴露辅助调用实际选择的upstream model，使用户路径验证能在真实模型调用前捕获泄漏。


### Profile drift fail-closed guard

- 当`DEEPSEEK_PROXY_FORCE_MODEL=1`时，`DEEPSEEK_PROXY_MODEL`仍是CoDeepSeedeX-managed Codex profiles的权威model来源。
- `dsproxy start`和`dsproxy status`在继续前会基于默认env执行静默managed-profile预修复。
- 预修复内部禁用post-config apply，避免递归重启/修复循环。
- 若修复失败，CLI入口必须fail closed，而不是继续允许`glm-5.1`等过时split profile残留。
- Codex wrapper launch repair仍然保留；status/start preflight用于保护Codex调用前的用户路径和验证路径。
