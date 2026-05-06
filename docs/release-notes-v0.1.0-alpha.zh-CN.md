# 发布说明：v0.1.0-alpha

这是deepseek-responses-proxy计划中的第一个公开技术预览版。

## 重点功能

- 面向Codex的本地Responses兼容proxy
- DeepSeek上游桥接
- Codex工具调用归一化与协议强化
- 上下文裁剪与持久本地压缩
- 自适应压缩预算策略
- agent loop活性守卫
- 基于LLM的活性判定
- 支持内部调用归因的usage ledger
- dsproxy统一CLI
- Codex profile bootstrap
- 预览版安装脚本
- 中英文文档

## 已知限制

- 不是生产稳定版，也不是原生Codex的完全替代品
- Windows原生安装仍处于实验阶段
- scripts/install.sh在公开一行安装前仍需替换真实仓库URL
- DeepSeek行为不等同于原生Codex模型
- 当前压缩基于文本摘要，无法复现Codex内部encrypted compaction机制

## 推荐用户

适合理解Codex、本地proxy、环境变量和工具调用agent风险的技术用户。

## 安全说明

仅建议在本地运行，不要暴露到公网。
