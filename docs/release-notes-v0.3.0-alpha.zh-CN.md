# CoDeepSeedeX v0.3.0-alpha

## 概要

内部里程碑：`v2.7a32-real-session-validation-hardening`。

本版本聚焦Codex + DeepSeek thinking模式下的长会话可靠性，完成了从tool-output trimming、运行态观测、behavioral ready检查到真实Codex smoke验证的闭环。

## 重点功能

- 新增`dsproxy debug behavioral`，用于输出长会话运行态ready摘要。
- 将long-session debug trace聚合为behavioral status、blockers、context budget、prompt tokens和tool-output trim指标。
- 强化thinking模式下针对shell和interactive shell重输出会话的tool-output trimming rollout。
- 保留结构化tool-output trimming能力，image payload的真实大负载验证仍按后续rollout推进。
- 新增`docs/real-long-session-validation.md`，记录真实长会话验证流程。
- 新增受保护脚本`scripts/real-long-session-behavioral-smoke.sh`。
- 记录Codex `workspace-write`沙箱访问宿主WSL本地proxy端口`127.0.0.1:8001`的边界。

## 验证

受保护smoke脚本支持：

```bash
scripts/real-long-session-behavioral-smoke.sh --dry-run
scripts/real-long-session-behavioral-smoke.sh --allow-bypass
```

真实smoke使用`codex exec --dangerously-bypass-approvals-and-sandbox`，因为Codex的`workspace-write`沙箱不能稳定访问宿主WSL上的`127.0.0.1:8001`监听端口。

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

- 本版本验证的是tool-output trimming和long-session observability路径，不等同于完全复现原生Codex的semantic compaction。
- 大image payload真实会话验证仍是独立后续工作。
- 受保护真实smoke使用权限很高的Codex bypass模式，只建议在受控本地验证中使用。
