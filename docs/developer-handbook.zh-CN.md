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
