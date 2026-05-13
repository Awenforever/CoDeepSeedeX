# CoDeepSeedeX开发手册

本文档用于维护CoDeepSeedeX / deepseek-responses-proxy的开发、测试、版本和Release发布流程。后续进入新的p~开发节点或公开v~Release前，应优先查阅本文件。

## 1. 项目入口和关键路径

- 项目根目录：`~/projects/deepseek-responses-proxy`
- 主分支：`master`
- GitHub仓库：`Awenforever/CoDeepSeedeX`
- Python包目录：`deepseek_responses_proxy/`
- CLI入口：`deepseek_responses_proxy/cli.py`
- Proxy核心服务：`deepseek_responses_proxy/app.py`
- 安装入口：`bootstrap.sh`
- 安装脚本：`scripts/install.sh`
- 主要测试目录：`tests/`
- 运维文档：`OPERATIONS.md`
- Release/handoff文档：`docs/handoff-for-developers.en.md`和`docs/handoff-for-developers.zh-CN.md`
- 自定义API交接文档：`docs/custom_api_handoff.md`
- 开发手册：`docs/developer-handbook.zh-CN.md`

## 2. 关键文件和函数索引

### `deepseek_responses_proxy/app.py`

- `PROXY_PUBLIC_VERSION`：当前运行proxy对应的公开Release tag，例如`v0.3.5-alpha`。
- `PROXY_PUBLIC_COMMIT`：公开Release tag解析到的commit，例如`53897ad`。
- `PROXY_INTERNAL_VERSION`：当前源码默认内部p~开发tag，例如`p2.9a3-version-metadata-dev-handbook`。
- `PROXY_INTERNAL_COMMIT`：内部commit兜底值。源码checkout优先由Git动态解析HEAD。
- `PROXY_VERSION`：兼容旧字段，等于`PROXY_PUBLIC_VERSION`。
- `create_app()`：构建FastAPI应用。
- `/healthz`相关返回：用于`dsproxy doctor`和启动健康检查。
- `/v1/proxy/status`相关返回：用于运行状态、上下文、工具桥、provider配置等观测。
- debug trace、context compaction、tool output trimming和persistent compaction实现也集中在本文件。

### `deepseek_responses_proxy/cli.py`

- `build_parser()`：构建`dsproxy`命令行参数。
- `main()`：CLI主入口。
- `_format_version_metadata()`：格式化`dsproxy --version`的双版本输出。
- `_version_metadata()`：生成public/internal版本元数据。
- `_start_proxy()`：启动stable或thinking proxy。
- `_stop_proxy()`：停止stable或thinking proxy。
- `_doctor()`：检查proxy健康状态和版本匹配。
- `_config()`：处理`dsproxy config`子命令。
- `_config_wizard()`：交互式API配置向导。
- `_upgrade()`：按GitHubLatestRelease或显式ref执行升级。
- `_resolve_latest_release_tag()`：解析GitHubLatestRelease tag。
- `_release_tag_matches_runtime()`：判断Release tag与运行时public version是否匹配。
- `_debug()`：处理`dsproxy debug`观测命令。

### `scripts/install.sh`

- 负责用户级安装、升级、profile写入、API配置引导、Release ref checkout。
- 默认安装和升级目标是GitHubLatestRelease，不是`master`。
- `--install-ref`用于显式指定Release tag或Git ref。
- 修改本文件前必须运行`bash -n scripts/install.sh`。

### `bootstrap.sh`

- 一行安装入口。
- 优先下载GitHubRelease asset中的`install.sh`。
- raw GitHub和git clone fallback仅作为备用路径。
- 修改本文件前必须运行`bash -n bootstrap.sh`。

### `tests/`

- `tests/test_cli.py`：CLI行为和配置命令主测试。
- `tests/test_version_metadata.py`：public/internal版本输出和版本元数据测试。
- `tests/test_readme_cli_command_consistency.py`：README命令与CLI parser一致性检查。
- `tests/test_bootstrap_installer.py`：bootstrap和安装入口测试。
- `tests/test_install_entrypoints_and_model_ui.py`：安装流程、model UI和provider配置测试。
- `tests/test_debug_trace.py`：debug trace和长会话观测测试。
- `tests/test_persistent_compaction.py`：persistent compaction测试。

## 3. 版本显示规则

`dsproxy --version`必须同时输出两个版本源：

```text
public version: v0.3.5-alpha | 53897ad
internal version: p2.9a3-version-metadata-dev-handbook | <current-head>
```

### public version

- public version使用`v~`tag。
- public version是用户可见Release版本。
- public version必须与GitHubRelease页面中的公开tag一致。
- public commit必须是该公开Release tag解析到的commit。
- 发布公开Release前，必须由维护者明确指定目标Release tag。
- 不允许助手自行决定、移动、删除或重建公开Release tag。

### internal version

- internal version使用`p~`tag。
- internal version用于开发节点、工作分支和内部审计。
- internal p~tag可随开发需要创建。
- internal p~tag不能创建GitHubRelease。
- internal p~tag不能替代public version。

## 4. Git开发规范

### 日常开发

1. 从干净`master`开始。
2. 创建工作分支：`work/<p-version-topic>`。
3. 修改前检查`git status --short`。
4. 关键文件修改前备份到`/tmp`。
5. 长输出写入`/tmp/*.txt`，终端只显示`run_ok`、`out`、行数、字节数和关键tail。
6. 完成功能后commit。
7. 推送工作分支。
8. 同步推送内部p~tag。
9. 需要合并时，只允许fast-forward合并`master`。

### 命名规则

- 工作分支：`work/p2.9a3-version-metadata-dev-handbook`
- 内部tag：`p2.9a3-version-metadata-dev-handbook`
- 公开Release tag：`v0.3.x-alpha`
- 禁止为alpha阶段创建普通`v0.3.x`tag，除非维护者明确决定发布稳定版。

## 5. 测试规范

每次功能改动至少运行：

```bash
git diff --check
bash -n bootstrap.sh
bash -n scripts/install.sh
.venv/bin/python -m py_compile deepseek_responses_proxy/app.py deepseek_responses_proxy/cli.py
```

还应按范围运行focused tests，例如：

```bash
.venv/bin/python -m pytest tests/test_cli.py tests/test_version_metadata.py -q
```

合并`master`前尽量运行full tests：

```bash
.venv/bin/python -m pytest -q
```

若full tests因外部环境失败，必须在日志中说明失败点和是否影响本次改动。

## 6. Release发布规范

公开Release只能在维护者明确指定目标tag后发布。

发布前必须确认：

1. 维护者明确指定目标Release tag，例如`v0.3.6-alpha`。
2. `deepseek_responses_proxy/app.py`中的`PROXY_PUBLIC_VERSION`已更新为该tag。
3. `PROXY_PUBLIC_COMMIT`应与即将发布的tag目标commit一致。
4. `pyproject.toml`使用对应PEP440版本，例如`0.3.6a0`。
5. `dsproxy --version`输出的public version与目标Release tag一致。
6. 自动Release workflow保持关闭。
7. 不存在错误普通tag，例如`v0.3.6`。
8. Release资产至少包含`bootstrap.sh`和`install.sh`。
9. GitHubRelease标题与公开tag一致。
10. 发布后复核Release tag、Release资产、LatestRelease状态和安装路径。

Release发布过程中不得静默移动、删除或重建已有公开tag。若确需更新已有Release，必须明确说明要删除并重建哪个Release和tag，并等待维护者确认。

## 7. 安装和升级目标

- 默认安装目标：GitHubLatestRelease。
- 默认升级目标：GitHubLatestRelease。
- `master`是开发分支，不是默认用户升级目标。
- `dsproxy upgrade`默认解析GitHubLatestRelease tag。
- 显式测试开发分支或内部节点时，必须明确说明使用的ref。

## 8. 本机开发入口

当前开发机允许将`~/.local/bin/dsproxy`替换为当前源码checkout wrapper。该操作会修改真实HOME，执行前必须醒目标注。

开发机验证当前源码CLI时，可使用：

```bash
.venv/bin/python -m deepseek_responses_proxy.cli --version
```

本机PATH入口验证：

```bash
command -v dsproxy
dsproxy --version
```

二者应在当前开发机上保持一致。

## 9. 禁止事项

- 禁止在命令中使用`exit`或`logout`。
- 禁止猜测源码、配置、日志或运行态。
- 禁止直接打印全量环境变量、源码全文或无关大范围grep。
- 禁止在dirty工作区盲目叠补丁。
- 禁止内部p~tag创建GitHubRelease。
- 禁止将公开Release tag与内部开发tag混用。
- 禁止未确认就移动、删除或重建公开Release tag。

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_START -->

## p2.9a4开发交接状态同步

本节以p2.9a4为准，覆盖较早p2.8交接信息中关于当前开发状态的描述。

- 当前项目路径：`~/projects/deepseek-responses-proxy`
- 当前主分支：`master`
- 当前远端主分支：`origin/master`
- 当前master和origin/master：`b3700a3`
- 当前内部开发tag：`p2.9a3-version-metadata-dev-handbook`
- 当前内部开发tag目标：`b3700a3`
- 当前公开Release tag：`v0.3.5-alpha`
- 当前公开Release tag目标：`53897ad`
- 不存在也不得创建普通公开tag：`v0.3.5`
- `dsproxy --version`必须同时输出public version和internal version。
- 当前public version为：`v0.3.5-alpha | 53897ad`
- 当前internal version为：`p2.9a3-version-metadata-dev-handbook | b3700a3`

### 开发机运行时要求

开发机必须始终使用当前checkout master作为`dsproxy`入口，而不是GitHub Latest Release安装目录中的旧运行时。推荐入口为：

```bash
~/.local/bin/dsproxy
```

该入口应进入：

```bash
~/projects/deepseek-responses-proxy
```

并执行：

```bash
.venv/bin/python -m deepseek_responses_proxy.cli
```

每次切换、拉取或合并master后，若正在运行proxy服务，必须重启stable和thinking实例：

```bash
dsproxy stop thinking
dsproxy stop
dsproxy start
dsproxy start thinking
```

验证标准：

```bash
dsproxy --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```

`/healthz`中的`version`必须与当前public version一致。若`dsproxy --version`显示p2.9a3，而`/healthz`仍显示旧版本，例如`v0.3.2`，说明运行中的uvicorn proxy仍是旧进程，必须重启。

### debug trace录制注意事项

Codex录制时，summary必须读取正在运行的proxy实际继承的`DEEPSEEK_PROXY_DEBUG_DIR`。如果summary读取的是新建空目录，而proxy进程仍写入旧目录，会出现`debug_file_count=0`的假象。判断trace是否落盘时，应同时检查：

- `ps`中uvicorn proxy进程的环境变量
- `DEEPSEEK_PROXY_DEBUG_TRACE`
- `DEEPSEEK_PROXY_DEBUG_DIR`
- 目标目录下的`trace-*.jsonl`
- `latest.json`

### Release和tag边界

内部p tag可以随开发节点创建和推送，但不得创建GitHub Release。公开Release tag仍使用`v0.3.x-alpha`格式，并且只能在用户明确指定发布时创建、删除、重建或移动。

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_END -->

<!-- CODEEPSEEDEX_RELEASE_NOTES_NO_DUP_TITLE_RULE_START -->

### Release notes标题行规范

GitHub Release页面本身已经有Release标题，因此Release notes正文不得再重复写标题行。例如不得在正文第一行再写：

```text
CoDeepSeedeX v0.3.5-alpha
```

Release notes正文应直接从Highlights、Changes、Fixes、Install或Validation等内容开始。发布前检查Release notes时，必须确认正文没有重复的产品名加版本号标题行，避免GitHub页面出现双标题。

<!-- CODEEPSEEDEX_RELEASE_NOTES_NO_DUP_TITLE_RULE_END -->

<!-- CODEEPSEEDEX_P29A6_V036_HANDOFF_SYNC_START -->
## v0.3.6-alpha发布后移交状态，p2.9a6同步

- 当前仓库状态：`master = origin/master = 7fd8fb6`。
- 公开Release tag：`v0.3.6-alpha -> 7fd8fb6`。
- 发布点对应内部开发tag：`p2.9a5-release-v0.3.6-alpha -> 7fd8fb6`。
- 旧公开Release tag `v0.3.5-alpha`仍保留在`53897ad`，不得移动。
- 普通公开tag `v0.3.5`必须保持不存在。
- GitHub Release `v0.3.6-alpha`已发布，标题为`CoDeepSeedeX v0.3.6-alpha`，`targetCommitish=master`，`isDraft=false`，`isPrerelease=false`。
- Release资产`bootstrap.sh`和`install.sh`均已上传，并已通过HTTP 200检查。
- 发布后运行时预期：`dsproxy --version`输出`public version: v0.3.6-alpha | 7fd8fb6`和`internal version: p2.9a5-release-v0.3.6-alpha | 7fd8fb6`。
- 发布后健康检查预期：`http://127.0.0.1:8000/healthz`和`http://127.0.0.1:8001/healthz`均返回版本`v0.3.6-alpha`。
- Release notes正文不得重复GitHub Release页面已有的标题行，例如不得再写`CoDeepSeedeX v0.3.6-alpha`；正文应直接从`Highlights`、`Changes`、`Fixes`、`Install`或`Validation`等部分开始。
- 后续Release body检查脚本必须先把`gh release view --json ...`输出保存为`/tmp/*.json`文件，再由Python读取该文件。不要在含heredoc的脚本中把Release JSON通过stdin管道传给Python。
- debug trace汇总必须读取正在运行的proxy进程实际继承的`DEEPSEEK_PROXY_DEBUG_DIR`，不得读取新建或猜测的trace目录。
<!-- CODEEPSEEDEX_P29A6_V036_HANDOFF_SYNC_END -->
## VM中GitHub访问不稳定时的最短处理路径

适用场景：在VM或全新测试机中执行一键安装、E2E验证或`git clone/fetch`时，`github.com`、GitHubRelease资产或`git ls-remote`间歇性失败。遇到这类问题时，先不要继续跑安装器，避免把网络问题误判为`install.sh`或wrapper逻辑问题。

最短判断链：

1. 先在VM里只测`curl -4 -fsSIL https://github.com`和`git -c http.version=HTTP/1.1 ls-remote https://github.com/Awenforever/CoDeepSeedeX.git HEAD`。
2. 只要这两项不稳定，就暂停安装器验证，先固定VM到GitHub的网络链路。
3. 在Windows宿主机确认真实可用的本地代理端口，不要仅凭配置文件或界面显示判断端口可用。
4. 如果VM直连宿主机代理端口出现`TLS connection was non-properly terminated`、`unexpected eof while reading`、`Connection reset by peer`或`gnutls_handshake()`失败，应判断为代理对LAN客户端不稳定。
5. 对极连云一类只对本机回环稳定的代理，可在Windows管理员PowerShell中使用`netsh interface portproxy`把VMnet8入口转发到本机回环代理端口。
6. 例如本次有效链路为`VM -> 192.168.231.1:7896 -> Windows portproxy -> 127.0.0.1:7892 -> 极连云`。
7. VM中固定GitHub专用Git代理：`http.https://github.com.proxy`、`http.https://raw.githubusercontent.com.proxy`和`http.https://codeload.github.com.proxy`，同时保留`http.version HTTP/1.1`。
8. 后续E2E验证只把GitHubRelease资产下载、`git ls-remote`、`git clone/fetch/checkout`作为核心链路，不把jsDelivr短commit URL作为硬性验收项。

推荐的Windows端转发策略：

```powershell
netsh interface portproxy add v4tov4 listenaddress=192.168.231.1 listenport=7896 connectaddress=127.0.0.1 connectport=7892
New-NetFirewallRule -DisplayName "CoDeepSeedeX VMnet8 jilianyun proxy 7896" -Direction Inbound -Action Allow -Protocol TCP -LocalAddress 192.168.231.1 -LocalPort 7896 -RemoteAddress 192.168.231.0/24
```

推荐的VM端Git代理配置：

```bash
git config --global http.version HTTP/1.1
git config --global http.https://github.com.proxy http://192.168.231.1:7896
git config --global http.https://raw.githubusercontent.com.proxy http://192.168.231.1:7896
git config --global http.https://codeload.github.com.proxy http://192.168.231.1:7896
```

撤销Windows端转发：

```powershell
netsh interface portproxy delete v4tov4 listenaddress=192.168.231.1 listenport=7896
Remove-NetFirewallRule -DisplayName "CoDeepSeedeX VMnet8 jilianyun proxy 7896" -ErrorAction SilentlyContinue
```

注意事项：

- 不要把端口“能TCP连接”误判为代理可用，必须验证GitHubRelease下载和`git ls-remote`。
- 不要在网络不稳定时继续跑安装器，否则会制造半安装状态和误导性日志。
- 不要使用已知不稳定的`192.168.231.1:7892`直连路径作为VM验证路径。
- 对Release验证而言，GitHubRelease资产和Git仓库链路比jsDelivr短commit URL更关键。

## Release错题本

本节用于累计发布过程中暴露出的流程错误，后续发布前必须逐项对照。该节不是Release notes，不面向普通用户。

### v0.3.7-alpha发布错题

1. 不得硬编码版本文件路径。本次曾错误假设根目录存在`app.py`，实际运行时文件是`deepseek_responses_proxy/app.py`。发布脚本必须先执行只读审计，使用`git grep -n "v0.3.6-alpha\|p2.9a" -- "*.py" "pyproject.toml"`确认版本字符串分布。

2. 不得假设版本元数据只出现在一个Python文件。本次版本字符串同时存在于运行时代码和测试断言中。后续必须按角色处理：`deepseek_responses_proxy/app.py`维护public/internal runtime version，`pyproject.toml`维护包版本，`tests/test_version_metadata.py`维护版本一致性断言，`tests/test_cli.py`只维护CLI输出相关public version断言。

3. 不得强制所有测试文件都包含internal tag。本次错误要求`tests/test_cli.py`必须含`p2.9a*`，但该文件只需要public tag。后续必须为每个文件定义独立检查规则。

4. 修改`pyproject.toml`时必须同步版本测试。本次将包版本改为`0.3.7a0`后，测试中仍断言`0.3.6a0`，导致版本元数据测试失败。后续必须在full tests之前运行版本一致性快速检查。

5. focused tests不得引用不存在的文件。本次引用了不存在的`tests/test_provider_live_probe.py`，pytest直接返回`rc=4`。后续focused test列表必须先过滤存在文件，缺失项只记录到日志，不能传给pytest。

6. release脚本必须是幂等状态机，不得依靠一串临时续跑脚本。状态机至少要识别：版本文件已同步、测试已通过、commit已存在、本地tag已存在、远端分支/tag已存在、master已合并、GitHubRelease已存在、资产已上传、本机运行时已刷新。

7. push必须默认走HTTPS并设置超时。本次`git push`走SSH 22端口导致用户等待约28分钟。后续发布脚本必须使用`https://github.com/Awenforever/CoDeepSeedeX.git`，并在push前运行`gh auth status`和`gh auth setup-git`，所有网络步骤必须有timeout。

8. 公开Release tag应尽量靠后推送，避免半发布状态。推荐顺序：测试通过，commit，push work branch，push internal tag，fast-forward master，push master，push public tag，创建GitHubRelease，复核资产，刷新本机运行时。如果公开tag已存在，恢复脚本只能复核，不得移动。

9. Release复核不得依赖当前`gh`版本不支持的字段。本次使用`isLatest`导致Release已创建后复核中止。后续只使用稳定字段：`tagName,name,isDraft,isPrerelease,targetCommitish,publishedAt,assets`，或先动态检测字段能力。

10. Release notes正文不得重复标题行。正文应从`Highlights:`、`Changes:`、`Fixes:`、`Install:`或`Validation:`开始，不能再写`CoDeepSeedeX v0.3.x-alpha`作为首行。

### 后续强制发布流程

1. 只读审计：确认branch、HEAD、origin/master、工作区、旧public tag、目标public tag、目标GitHubRelease、版本字符串分布、测试文件存在性。
2. 版本同步：按文件角色同步public tag、internal tag和PEP440包版本。
3. 测试：`git diff --check`，`bash -n bootstrap.sh`，`bash -n scripts/install.sh`，`python -m py_compile`，focused tests，full tests。
4. 提交与推送：commit后先推work branch和internal tag，再fast-forward master并推master，最后推public tag。
5. Release创建：创建GitHubRelease并上传`bootstrap.sh`和`install.sh`。
6. 复核：确认master、origin/master、public tag、internal tag、Release资产、旧tag未移动、普通错误tag不存在。
7. 本机运行时刷新：用`--install-ref master`刷新，并确认`dsproxy --version`输出public/internal两行，`codex --profile deepseek-thinking app-server --help`返回0。
