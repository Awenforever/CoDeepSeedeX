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
