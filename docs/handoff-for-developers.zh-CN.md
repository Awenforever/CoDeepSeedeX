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
