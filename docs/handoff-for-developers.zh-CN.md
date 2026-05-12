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

## p2.9a4 developer handoff sync

This section supersedes older p2.8-era handoff state when describing the current local developer checkout.

Current repository state:

- Project path: `~/projects/deepseek-responses-proxy`
- Main branch: `master`
- Remote main branch: `origin/master`
- Current `master` and `origin/master`: `b3700a3`
- Current internal development tag: `p2.9a3-version-metadata-dev-handbook`
- Current internal development tag target: `b3700a3`
- Current public Release tag: `v0.3.5-alpha`
- Current public Release tag target: `53897ad`
- Plain public tag `v0.3.5` must not exist and must not be created.
- `dsproxy --version` must print both public and internal version lines.
- Current public version line: `public version: v0.3.5-alpha | 53897ad`
- Current internal version line: `internal version: p2.9a3-version-metadata-dev-handbook | b3700a3`

### Local developer runtime rule

The developer machine must run `dsproxy` from the current checkout on `master`, not from an older installed GitHub Latest Release runtime.

The expected developer entrypoint is:

```bash
~/.local/bin/dsproxy
```

It should enter:

```bash
~/projects/deepseek-responses-proxy
```

and execute:

```bash
.venv/bin/python -m deepseek_responses_proxy.cli
```

After switching, pulling, or fast-forwarding `master`, restart both proxy services if they are running:

```bash
dsproxy stop thinking
dsproxy stop
dsproxy start
dsproxy start thinking
```

Validation commands:

```bash
dsproxy --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```

The `/healthz` version must match the current public version. If `dsproxy --version` reports the current p2.9a3 metadata but `/healthz` still reports an old version such as `v0.3.2`, the running uvicorn proxy is stale and must be restarted.

### Debug trace recording note

When recording Codex-visible behavior, summarize the debug directory inherited by the running proxy process. A new empty debug directory can produce a misleading `debug_file_count=0` if the existing proxy process is still writing to an older `DEEPSEEK_PROXY_DEBUG_DIR`.

Always confirm:

- the uvicorn proxy process environment
- `DEEPSEEK_PROXY_DEBUG_TRACE`
- `DEEPSEEK_PROXY_DEBUG_DIR`
- `trace-*.jsonl` files
- `latest.json`

### Release and tag boundary

Internal `p*` tags may be created for development milestones, but they must not create GitHub Releases. Public Release tags continue to use the `v0.3.x-alpha` form and may only be created, deleted, rebuilt, or moved when the user explicitly requests a public Release operation.

<!-- CODEEPSEEDEX_HANDOFF_P2_9A4_SYNC_END -->
