# 开发交接文档

## 当前定位

deepseek-responses-proxy是面向Codex的本地Responses兼容代理。

当前目标不是实现通用模型网关，而是优先改善codex --profile deepseek-thinking体验。

## 版本线

- v2.3a1 output_text内容归一化
- v2.3a2 Codex工具默认开放
- v2.3a3 上下文裁剪
- v2.3a4 持久本地压缩
- v2.3a5 运行态观测
- v2.3a6 agent loop活性守卫
- v2.3a7 工具调用协议强化
- v2.3a8 Codex工具协议注入和liveness judge
- v2.3a9 内部usage归因
- v2.3a10 自适应压缩预算策略
- v2.4a1 dsproxy CLI和配置基础
- v2.4a1a1 CLI启动版本和端口守卫
- v2.4a2 安装脚本和Codex profile bootstrap
- v2.4a3 文档和发布指南

## 不变量

- 默认只监听127.0.0.1
- 不应破坏Responses envelope兼容
- 不应破坏function_call和tool_call配对
- 不应让旧服务被误判为新服务ready
- usage ledger应记录内部上游调用
- Codex profile写入应尽量保留用户原有配置

## 发布前待办

- 确认scripts/install.sh指向公开GitHub仓库地址
- 完成README链接检查
- 测试fresh clone安装
- 测试WSL
- 测试无API key错误提示
- 测试Codex profile安装和卸载
- 做敏感信息扫描

## v0.3.0-alpha长会话可靠性交接

- 公开运行态版本：`v0.3.0-alpha`。
- 内部里程碑：`v2.7a32-real-session-validation-hardening`。
- `dsproxy debug behavioral --thinking`是面向长Codex thinking会话的紧凑运行态ready检查。
- `docs/real-long-session-validation.md`记录真实会话验证边界和验收条件。
- `scripts/real-long-session-behavioral-smoke.sh --dry-run`只验证受保护smoke脚本，不调用Codex。
- `scripts/real-long-session-behavioral-smoke.sh --allow-bypass`执行受控真实smoke。它有意使用`codex exec --dangerously-bypass-approvals-and-sandbox`，因为Codex的`workspace-write`沙箱不能稳定访问宿主WSL上的`127.0.0.1:8001`监听端口。
- 不要把沙箱内的`blocked` behavioral结果直接判断为proxy故障，必须先确认该执行环境能否访问localhost端口。

<!-- CODEEPSEEDEX_CURRENT_HANDOFF_BEGIN -->
## 当前发布交接状态：v0.3.5-alpha

当前公开Release状态：

- 公开Release tag：`v0.3.5-alpha`
- Release标题：`CoDeepSeedeX v0.3.5-alpha`
- Release commit：`53897ad`
- Release资产：`bootstrap.sh`、`install.sh`
- 默认安装和升级目标：GitHub Latest Release，不是`master`
- `master`和`origin/master`均位于`53897ad`

当前内部开发状态：

- 当前已完成开发线：`p2.8`
- 已完成内部阶段：
  - `p2.8a1-api-validation`
  - `p2.8a2-doc-api-validation-sync`
  - `p2.8a3-api-validation-quality-hardening`
  - `p2.8a4-model-api-provider-catalog`
  - `p2.8a5-doc-release-readiness-sync`
- 当前文档同步：`p2.8a6-post-release-doc-handoff-sync`

Release和tag规则：

- alpha阶段的公开Release tag使用`v0.3.x-alpha`形式。
- 本次alpha发布不要创建普通`v0.3.5`tag。
- 内部开发tag使用`p*`形式。
- 内部`p*`tag不能创建GitHub Release。
- 除非维护者明确指定具体Release和tag操作，否则不要移动、删除或重建公开Release tag。

v0.3.5-alpha概要：

- API key验证已集成到手动配置命令和安装或引导配置流程。
- 没有新增`dsproxy config test-provider --kind web-search|image --provider <name>`命令。
- web search和文生图provider支持得到扩展和加固。
- 新增model provider catalog相关能力。
- README和运维文档已说明provider配置、免费额度提示和`Other`自定义server交接路径。
- `docs/custom_api_handoff.md`是自定义tool server配置的交接文档。

下一阶段开发建议：

- 新开发线开始前，先审计当前仓库状态、Release状态、tag和脏文件。
- 使用`work/<topic>`分支。
- 完成修改后提交commit。
- 只有需要远端发布时，才同步推送工作分支和对应内部tag。
- 公开Release tag操作必须和普通内部开发分开处理。
<!-- CODEEPSEEDEX_CURRENT_HANDOFF_END -->

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_START -->

## p2.9a4开发交接状态同步

本节以p2.9a4为准，覆盖较早p2.8交接信息中关于当前开发状态的描述。

当前仓库状态：

- 项目路径：`~/projects/deepseek-responses-proxy`
- 主分支：`master`
- 远端主分支：`origin/master`
- 当前`master`和`origin/master`：`b3700a3`
- 当前内部开发tag：`p2.9a3-version-metadata-dev-handbook`
- 当前内部开发tag目标：`b3700a3`
- 当前公开Release tag：`v0.3.5-alpha`
- 当前公开Release tag目标：`53897ad`
- 普通公开tag`v0.3.5`不得存在，也不得创建。
- `dsproxy --version`必须同时输出public version和internal version。
- 当前public version行：`public version: v0.3.5-alpha | 53897ad`
- 当前internal version行：`internal version: p2.9a3-version-metadata-dev-handbook | b3700a3`

### 开发机运行时规则

开发机必须从当前checkout的`master`运行`dsproxy`，而不是从较旧的GitHub Latest Release安装运行时启动。

预期开发入口为：

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

切换、拉取或fast-forward合并`master`后，如果proxy服务正在运行，必须重启stable和thinking实例：

```bash
dsproxy stop thinking
dsproxy stop
dsproxy start
dsproxy start thinking
```

验证命令：

```bash
dsproxy --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```

`/healthz`中的版本必须匹配当前public version。若`dsproxy --version`已经显示当前p2.9a3元数据，但`/healthz`仍显示旧版本，例如`v0.3.2`，说明正在运行的uvicorn proxy是旧进程，必须重启。

### debug trace录制注意事项

录制Codex可见行为时，summary必须读取正在运行的proxy进程继承的debug目录。如果新建空debug目录但现有proxy进程仍写入旧的`DEEPSEEK_PROXY_DEBUG_DIR`，就会出现误导性的`debug_file_count=0`。

每次都应确认：

- uvicorn proxy进程环境变量
- `DEEPSEEK_PROXY_DEBUG_TRACE`
- `DEEPSEEK_PROXY_DEBUG_DIR`
- `trace-*.jsonl`文件
- `latest.json`

### Release和tag边界

内部`p*`tag可以用于开发里程碑，但不得创建GitHub Release。公开Release tag继续使用`v0.3.x-alpha`格式，并且只有在用户明确要求公开Release操作时，才允许创建、删除、重建或移动。

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_END -->

<!-- CODEEPSEEDEX_RELEASE_NOTES_NO_DUP_TITLE_RULE_START -->

### Release notes标题行规范

GitHub Release页面本身已经有Release标题，因此Release notes正文不得再重复写标题行。例如不得在正文第一行再写：

```text
CoDeepSeedeX v0.3.5-alpha
```

Release notes正文应直接从Highlights、Changes、Fixes、Install或Validation等内容开始。发布前检查Release notes时，必须确认正文没有重复的产品名加版本号标题行，避免GitHub页面出现双标题。

<!-- CODEEPSEEDEX_RELEASE_NOTES_NO_DUP_TITLE_RULE_END -->
