# CoDeepSeedeX开发手册

本文档是给维护者和新对话AI看的“启动包”。它只保留高频规则、当前状态、关键路径、近期一个大版本的开发摘要和最高优先级经验。长期详细流水账不要塞进本文件，应写入`docs/development-log.md`。

## 1. 文档维护原则

- README面向用户，不能写维护者流水账。
- `TROUBLESHOOTING.md`面向用户排障，不能写Release内部流程。
- 本开发手册面向你和AI，用于新对话快速对齐。
- 本开发手册只保留近期一个大版本的详细摘要。更早、更细的过程记录进入`docs/development-log.md`。
- `docs/development-log.md`是详尽开发日志，用统一模板追加。只有需要回溯时再读取。
- 不再维护分散的handoff、operations、install、usage、upgrade、security、custom_api_handoff和release-notes文档。
- 如果调整文档结构，必须同步测试契约。不得为了旧测试保留幽灵文档。

## 2. 活跃文档契约

当前活跃文档只有：

- `README.md`：英文用户入口。
- `README.zh-CN.md`：中文用户入口。
- `TROUBLESHOOTING.md`：用户排障入口。
- `docs/developer-handbook.zh-CN.md`：维护者和AI启动包。
- `docs/development-log.md`：长期详尽开发日志，按需查阅，不默认喂给AI。

旧文档路径已退役。测试不得固定读取退役路径。

## 3. 当前项目状态

- 项目路径：`~/projects/deepseek-responses-proxy`
- GitHub仓库：`Awenforever/CoDeepSeedeX`
- 主分支：`master`
- 当前公开Release：`v0.3.7-alpha`
- 当前公开Release commit：`466706f`
- 当前Release内部tag：`p2.9a18-release-v0.3.7-alpha`
- 当前文档维护基线：`p2.9a19-release-lessons-handoff = 5013413`
- 旧公开tag不得移动：`v0.3.6-alpha = 7fd8fb6`，`v0.3.5-alpha = 53897ad`
- 普通错误tag`v0.3.5`必须不存在。

p2.9a20文档重构完成后，应以新的p2.9a20 commit作为master和origin/master。

## 4. 关键文件地图

- `deepseek_responses_proxy/app.py`：运行时核心、Responses兼容接口、provider桥接、版本元数据。
- `deepseek_responses_proxy/cli.py`：`dsproxy`命令入口、config、doctor、upgrade。
- `scripts/install.sh`：安装器，负责installed checkout、venv、wrapper、Codex profile、配置初始化。
- `bootstrap.sh`：一键安装入口，负责依赖和安装器获取。
- `tests/`：回归测试和文档契约测试。
- `README.md`、`README.zh-CN.md`：用户说明。
- `TROUBLESHOOTING.md`：用户排障。
- `docs/development-log.md`：详尽开发日志。

## 5. 版本和tag规则

`dsproxy --version`必须输出两行：

```text
public version: v0.3.x-alpha | <public_release_commit>
internal version: p2.9aN-topic | <internal_commit>
```

公开Release tag使用`v0.3.x-alpha`。alpha阶段不得创建不带`-alpha`的`v0.3.x`公开tag。内部开发tag使用`p`开头，例如`p2.9a20-docs-consolidation`。内部tag不得创建GitHubRelease。

## 6. Release发布规则

发布前必须先只读审计：

- branch、HEAD、origin/master
- 工作区是否干净
- 旧public tag是否未移动
- 目标public tag和GitHubRelease是否已存在
- 版本字符串分布
- 测试文件是否存在

发布顺序：

1. 同步版本文件。
2. 静态检查和测试。
3. commit。
4. push work branch。
5. push internal tag。
6. fast-forward master。
7. push master。
8. push public tag。
9. 创建GitHubRelease并上传`bootstrap.sh`和`install.sh`。
10. 复核Release资产。
11. 刷新本机运行时。

push默认使用HTTPS，不走SSH。所有push、curl和gh步骤必须设置timeout。

Release notes正文不能重复标题行，正文首行应为`Highlights:`、`Changes:`、`Fixes:`、`Install:`或`Validation:`。

## 7. 安装和Release入口

用户安装入口统一使用Latest Release bootstrap：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/releases/latest/download/bootstrap.sh | bash
```

tag fallback示例必须保留，供Release asset回退策略和测试契约使用：

```bash
curl -fsSL https://github.com/Awenforever/CoDeepSeedeX/raw/refs/tags/${tag}/bootstrap.sh | bash
```

推荐升级：

```bash
dsproxy upgrade
```

模型设置示例：

```bash
dsproxy config set-model deepseek-v4-pro
```

当前运行命令形态：

```bash
dsproxy start
dsproxy start thinking
dsproxy status
dsproxy status thinking
dsproxy stop
dsproxy stop thinking
```

不要恢复旧式带连字符的dsproxy运行命令。

## 8. Provider和自定义API维护入口

Provider相关维护内容聚合在本节。

关键代码路径：

- `deepseek_responses_proxy/app.py`
- `deepseek_responses_proxy/cli.py`
- `scripts/install.sh`
- `README.md`
- `README.zh-CN.md`

Web search tool bridge和image generation tool bridge都必须保持CLI、安装器、README和运行时语义一致。非生成式image validation不能宣称真实出图可用。真实出图必须通过：

```bash
dsproxy doctor providers --live --allow-spend
```

显式触发，并提示可能消耗额度。

## 9. 安装器本地文件覆盖规则

安装器覆盖本地文件前必须备份。重点文件包括：

- `~/.config/deepseek-responses-proxy/env`
- `~/.local/bin/dsproxy`
- `~/.local/bin/codex`
- `~/.codex/config.toml`
- installed checkout中的dirty patch和untracked files

未知用户自有`codex`或`dsproxy`不得静默覆盖。对已知CoDeepSeedeX wrapper可备份后刷新。

## 10. VM GitHub访问经验

VMware NAT下，VM常见网关是`192.168.231.2`，Windows宿主VMnet8地址常见为`192.168.231.1`。

已验证路径：

```text
VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> 极连云
```

如果GitHub直连不稳定，优先配置GitHub相关域名走VM可达的宿主代理。不要把端口能TCP连接误判为代理可用。若jsDelivr失败但GitHubRelease资产和`git ls-remote`稳定，不要把jsDelivr作为阻断项。

## 11. Release错题本

近期最高优先级经验：

1. 先审计版本字符串分布，不硬编码路径。
2. `deepseek_responses_proxy/app.py`、`pyproject.toml`、`tests/test_version_metadata.py`、`tests/test_cli.py`各自版本规则不同。
3. focused tests必须过滤不存在的测试文件。
4. Release脚本必须是幂等状态机。
5. push默认走HTTPS并设置timeout。
6. public Release tag尽量靠后推送，避免半发布状态。
7. `gh release view`不得依赖当前gh版本不支持的字段。
8. 文档重构必须同步测试契约，不得保留幽灵文档。
9. 开发手册只保留启动上下文和近期摘要，详尽开发日志写入`docs/development-log.md`。

## 12. 近期一个大版本摘要：p2.9 / v0.3.7-alpha

p2.9阶段主要完成：

- provider endpoint和validation语义修正。
- Zhipu/Z.AI图像provider区分。
- `dsproxy doctor providers` live probe矩阵。
- 安装器修复受影响机器的installed checkout同步。
- local bin ownership guard，避免未知用户自有`codex`或`dsproxy`被静默覆盖。
- VM GitHub代理经验沉淀。
- `v0.3.7-alpha`发布闭环。
- p2.9a19记录Release错题。
- p2.9a20执行文档重构，将开发手册和详尽开发日志分离。

更细的流水记录见`docs/development-log.md`。

## 13. 新对话启动检查

新对话继续开发时，先只读审计：

```bash
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/master
git status --short
git rev-parse --short v0.3.7-alpha^{}
git rev-parse --short p2.9a19-release-lessons-handoff^{}
```

若继续p2.9a20，应确认是否已有`p2.9a20-docs-consolidation`tag。若没有，应从当前dirty状态继续完成文档重构，不要重新开始。
