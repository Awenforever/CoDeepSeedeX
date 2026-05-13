# CoDeepSeedeX详尽开发日志

本文件保存长期、可回溯的开发流水账。它不是新对话默认上下文。只有需要追溯具体版本、错误、测试或Release细节时才查阅。

## 记录格式规范

每条记录使用统一模板：

```text
## <date> <tag-or-branch> <short-title>

- 范围：
- 起点：
- 变更：
- 测试：
- 结果：
- 风险：
- 后续：
```

规则：

- 记录客观事实，不写泛泛总结。
- 必须写commit、tag、branch、测试结果和是否推送。
- 失败也记录，说明阻断点和恢复方式。
- 不记录API key值。
- 长日志路径写`/tmp/*.txt`，不要把完整日志粘进开发手册。
- 公开Release tag和内部tag必须分开记录。
- Release notes正文不得重复GitHub Release标题。

## 2026-05-13 p2.9a18 / v0.3.7-alpha 发布

- 范围：发布`v0.3.7-alpha`。
- 起点：`p2.9a17-vm-github-proxy-handbook = e5f79c2`。
- 变更：安装器受影响机器修复、installed checkout同步、local bin ownership guard、provider验证语义、VM代理经验、Release文档修正。
- 测试：focused tests通过，full tests为`359 passed in 18.98s`。
- 结果：`v0.3.7-alpha = 466706f`，`p2.9a18-release-v0.3.7-alpha = 466706f`，GitHubRelease已创建，资产`bootstrap.sh`和`install.sh`可访问。
- 风险：发布过程中曾出现半发布状态，公开tag先推送成功，但work分支、internal tag、master和GitHubRelease未全部完成。
- 恢复：改用HTTPS补齐push、master、Release和本机运行时刷新。
- 后续：必须将Release流程做成幂等状态机。

## 2026-05-13 p2.9a19 Release错题和handoff同步

- 范围：将`v0.3.7-alpha`发布经验写入开发手册和handoff。
- 起点：`master = origin/master = 466706f`。
- 变更：更新`OPERATIONS.md`、`docs/custom_api_handoff.md`、`docs/developer-handbook.zh-CN.md`、`docs/handoff-for-developers.en.md`、`docs/handoff-for-developers.zh-CN.md`。
- 测试：静态检查通过。
- 结果：`master = origin/master = 5013413`，`p2.9a19-release-lessons-handoff = 5013413`。
- 风险：文档继续分散，维护成本高。
- 后续：p2.9a20执行文档收敛。

## 2026-05-13 p2.9a20 文档重构

- 范围：重构文档体系。
- 起点：`master = origin/master = 5013413`。
- 目标：README面向用户，TROUBLESHOOTING面向用户排障，developer-handbook作为新对话启动包，development-log作为长期详尽日志。
- 关键决策：不再保留幽灵文档和幽灵测试。删除旧文档路径时必须同步测试契约。
- 当前过程：先尝试保留stub过测，后修正为测试契约跟随新文档结构。
- 风险：测试中仍可能存在旧文档路径硬编码，需要逐项替换。
- 后续：完成p2.9a20提交、内部tag、push和fast-forward master。

## 2026-05-13 p2.9a21 Bilingual developer handbook restoration

- Scope: restore the missing maintainer knowledge after p2.9a20 and introduce an English-primary developer handbook.
- Starting point: `master = origin/master = b160525`, `p2.9a20-docs-consolidation = b160525`.
- Change: add `docs/developer-handbook.md` as the primary AI startup context, keep `docs/developer-handbook.zh-CN.md` as the Chinese mirror, preserve detailed history in this log.
- Reason: p2.9a20 consolidated documentation correctly but compressed the developer handbook too aggressively and left only the Chinese handbook.
- Test contract: active documents now include both English and Chinese developer handbooks.
- Expected result: `master`, `origin/master`, and `p2.9a21-handbook-bilingual-restoration` point to the same new commit.

## p2.9a22-version-metadata-policy-audit

- Clarified runtime version metadata as a dual-track policy.
- User installations from a public Release tag report the public `v~` tag and the internal `p~` tag that existed when the Release tag was cut.
- Developer checkout runtime on `master` keeps the current public `v~` until the next Release, but its internal `p~` must advance with the latest `master` internal tag.
- Corrected the GitHub CLI rule: `gh release view --json` does not support `isLatest`; this is a command schema limitation, not an installed-version issue.
- Updated current developer runtime metadata to `p2.9a22-version-metadata-policy-audit` while keeping public Release `v0.3.7-alpha` and public commit `466706f`.
