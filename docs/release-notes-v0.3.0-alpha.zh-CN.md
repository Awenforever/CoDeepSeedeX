# CoDeepSeedeX v0.3.0-alpha

## 概要

内部里程碑：`v2.7a32-real-session-validation-hardening`。

本版本聚焦Codex + DeepSeek thinking模式下的上下文效率和长会话可靠性。核心改进是：超大的工具输出会在反复进入模型上下文之前被裁剪，从而降低长时间、工具密集型开发会话中的上下文压力。

## 长会话相关变化

- thinking模式启动时默认启用受限rollout的tool-outputtrimming。
- 超大的shell和interactive shell输出会在进入模型上下文前被压缩。
- 大型结构化工具输出会尽量先规范化，再进入裁剪路径。
- imagepayload类工具输出在通用tool-outputtrimming之外，还有12000字符的专门上限。
- long-session debug trace会被聚合为behavioral ready摘要，包括blockers、context budget、prompt tokens和tool-output trim指标。
- `dsproxy debug behavioral --thinking`可以快速查看当前长会话状态是ready、blocked，还是需要更多trace数据。

## 对用户的实际影响

对于长Codex会话，尤其是反复运行测试、shell诊断和日志密集型命令的会话，CoDeepSeedeX现在会把更少上下文浪费在超大工具输出上。这会提高会话在不耗尽prompt预算的情况下继续运行的概率。

代价是有意引入的：超大工具输出的中间部分可能被省略。保留的头部和尾部通常能覆盖命令结果、摘要和最近的错误上下文。如果必须保留完整输出，应将日志保存为文件，再显式检查或上传该文件。

## 验证与诊断

本版本新增：

- `docs/real-long-session-validation.md`
- `scripts/real-long-session-behavioral-smoke.sh`
- `dsproxy debug behavioral --thinking --limit 200 --timeout 5`

smoke脚本主要面向维护者和受控本地验证。普通用户诊断长会话行为时，通常只需要使用behavioral debug命令。

## 升级

升级到最新版：

```bash
dsproxy upgrade
```

预览：

```bash
dsproxy upgrade --dry-run
```

旧版本没有`dsproxy upgrade`时，可重新运行one-line installer：

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

## 已知限制

- 本版本改进的是tool-outputtrimming和long-sessionobservability，不等同于完全复现原生Codex的semanticcompaction。
- 超大工具输出的完整中间内容可能被移除。如果需要精确复现，请把完整日志保存为文件。
- 大imagepayload真实会话验证仍是独立后续工作。
- 受保护真实smoke使用权限很高的Codex bypass模式，只建议在受控本地验证中使用。
