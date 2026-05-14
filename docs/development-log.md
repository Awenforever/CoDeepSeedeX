# CoDeepSeedeX详尽开发日志

本文件保存长期、可回溯的开发流水账。它不是新对话默认上下文。只有需要追溯具体版本、错误、测试或Release细节时才查阅。


## p2.10a7-doc-sync

- Synchronized README, README.zh-CN, developer handbook, Chinese handbook, and this development log after the p2.10a6 installer model provider surface repair.
- Developer runtime internal version now advances to `p2.10a7-doc-sync`, while the public runtime version remains `v0.3.7-alpha | 466706f` until the next public Release.
- No public Release tag was moved or recreated.

## p2.10a6-installer-model-provider-surface

- Repaired `scripts/install.sh` so guided installer model API setup no longer presents ambiguous public choices such as `GLM / Z.AI`, generic `Qwen / DashScope`, Mimo, or Baichuan.
- The installer now mirrors the public model API provider surface:
  - `zhipu`
  - `zhipu-coding`
  - `zai`
  - `zai-coding`
  - `qwen-beijing`
  - `qwen-singapore`
  - `qwen-us`
  - `custom`
- Kept legacy `glm`, `qwen`, `dashscope`, and related aliases only as backward-compatible selection inputs, mapping them to explicit canonical providers.
- Added `tests/test_installer_model_provider_surface.py` and updated installer UI tests to prevent reverting to generic provider labels.
- Validation passed before merge: `git diff --check`, `bash -n bootstrap.sh`, `bash -n scripts/install.sh`, focused tests, broader tests, and full suite `379 passed`.

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

## p2.9a23-script-scope-safety-note

- Recorded a script-scope safety rule after the development-entrypoint wrapper repair script failed with `NameError: name 'ts' is not defined`.
- Shell variables are not available inside Python heredocs unless explicitly passed through environment variables.
- Future generated commands must either pass shell values into Python through environment variables or generate those values inside Python.
- For real-HOME modifications, scripts must validate variables and preconditions before writing target files.

## p2.9a24-script-helper-signature-safety

- Recorded a second generated-command safety rule after a read-only mainline resume audit failed with `TypeError: run() got an unexpected keyword argument 'env'`.
- Helper function signatures in generated Python scripts must cover all later keyword arguments such as `env`, `timeout`, `check`, and `allow_fail`.
- Future commands should be statically checked for helper definition/call-site consistency before being given to the user.

## p2.9a25-provider-key-scope-doc-sync

- Scoped image provider diagnostics so a generic `DEEPSEEK_PROXY_IMAGE_API_KEY` no longer marks every image provider as configured.
- Kept compatibility for the currently selected `DEEPSEEK_PROXY_IMAGE_PROVIDER` while preserving provider-specific key variables for unselected providers.
- Made `set-image-api-key` and the guided wizard write provider-specific image API key variables in addition to the legacy generic variable.
- Updated README image provider examples from the old `glm` shortcut to explicit `zhipu` and `zai` examples.

## p2.9a26-provider-live-web-search-doc-sync

- Confirmed the real SerpAPI web search live probe on the developer machine.
- Command class: `dsproxy doctor providers --kind web-search --provider serpapi --live --allow-spend`.
- Result: `doctor_status=ok`, `provider_ok=True`, HTTP status 200, `validation_method=fixed_query_search`, `validation_strength=live_query_probe`, `functional_probe=True`, and `functional_validation=performed`.
- The probe did not print API key values.
- Other web search providers remain untested because their API keys are not configured.
- This validates the CoDeepSeedeX provider bridge path for SerpAPI. It does not by itself prove the full Codex TUI end-to-end tool selection path, which should be validated separately before release readiness.

## p2.9a27-zhipu-live-image-doc-sync

- Confirmed the real Zhipu image generation live probe on the developer machine.
- Command class: `dsproxy doctor providers --kind image --provider zhipu --live --allow-spend`.
- Result: `doctor_status=ok`, `provider_ok=True`, HTTP status 200, `validation_method=live_image_generation`, `validation_strength=live_generation_probe`, `functional_probe=True`, and `functional_validation=performed`.
- The probe returned image evidence: `has_image=True` and `evidence=data_url_or_base64`.
- The probe did not print API key values.
- This validates the CoDeepSeedeX provider bridge path for Zhipu image generation. It does not by itself prove the full Codex TUI end-to-end tool selection path, which should be validated separately before release readiness.

## p2.9a29-qwen-region-endpoint-probe

- Fixed Qwen/DashScope provider diagnostics so `dsproxy doctor providers --kind image --provider qwen_image --live --allow-spend` respects `DEEPSEEK_PROXY_IMAGE_BASE_URL` and `DASHSCOPE_IMAGE_ENDPOINT`.
- Fixed the Qwen non-generation image API validation path to use the same regional endpoint override.
- Root cause: runtime image generation already respected `DEEPSEEK_PROXY_IMAGE_BASE_URL`, but the CLI provider diagnostic path had a separate hardcoded Beijing endpoint.
- This prevents Singapore, US Virginia, and Germany Frankfurt DashScope keys from being incorrectly tested against the Beijing endpoint.

## p2.9a30-qwen-region-live-matrix-doc-sync

- Recorded the Qwen/DashScope image regional live-probe matrix after p2.9a29 fixed regional endpoint overrides in CLI provider diagnostics.
- Beijing live probe passed: `qwen-image-2.0-pro`, endpoint `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`, HTTP 200, `has_image=True`, evidence `output_choice_image`.
- Singapore live probe passed: `qwen-image-2.0-pro`, endpoint `https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`, HTTP 200, `has_image=True`, evidence `output_choice_image`.
- US Virginia endpoint override worked: endpoint `https://dashscope-us.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`, but `qwen-image-2.0-pro` and `qwen-image-2.0-pro-2026-03-03` returned `Model not exist`.
- Germany Frankfurt workspace endpoint override worked: endpoint `{workspace}.eu-central-1.maas.aliyuncs.com`, but `qwen-image-2.0-pro` returned `Model not exist`.
- Conclusion: keep `qwen_image` validated for Beijing and Singapore. Treat US Virginia and Germany as model-availability failures for the tested Qwen Image models, not as endpoint override failures.
- Future work: if US/Germany Alibaba image generation is required, introduce or test a separate Wan image/text-to-image provider mode.

## p2.9a34-brave-provider-surface-removal

- Removed Brave Search from public/guided web search provider surfaces because Brave does not provide a free API key path before subscription.
- Updated README and README.zh-CN command examples to list SerpAPI, Tavily, Exa, and Firecrawl only.
- Removed Brave from CLI configuration choices, provider configuration status, and the `doctor providers` default web-search matrix.
- Kept low-level runtime compatibility separate from the public provider catalog to avoid unnecessarily breaking existing manual Brave configurations.

## p2.9a37-web-search-live-matrix-doc-sync

- Recorded current web search provider live-probe status after the Brave provider surface removal.
- Tavily live probe passed: endpoint `https://api.tavily.com/search`, HTTP 200, `validation_strength=live_query_probe`, `functional_validation=performed`.
- Exa live probe passed: endpoint `https://api.exa.ai/search`, HTTP 200, `validation_strength=live_query_probe`, `functional_validation=performed`.
- Firecrawl live probe passed: endpoint `https://api.firecrawl.dev/v2/search`, HTTP 200, `validation_strength=live_query_probe`, `functional_validation=performed`.
- SerpAPI remains the configured existing primary web search path.
- Brave Search remains removed from public/guided configuration because API key creation requires a paid subscription before testing.
- Current public/guided web search provider list: SerpAPI, Tavily, Exa, Firecrawl.

## p2.9a38-image-provider-live-matrix-doc-sync

- Recorded current image provider live-probe status after the Qwen regional matrix, Stability AI probe, and fal.ai probe.
- Qwen Image Beijing passed: `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Qwen Image Singapore passed: `qwen-image-2.0-pro`, HTTP 200, image evidence present.
- Qwen Image US Virginia endpoint override worked, but `qwen-image-2.0-pro` and `qwen-image-2.0-pro-2026-03-03` returned `Model not exist`.
- Qwen Image Germany Frankfurt workspace endpoint override worked, but `qwen-image-2.0-pro` returned `Model not exist`.
- Stability AI reached the official endpoint but was blocked at the Cloudflare layer with Error 1010 `browser_signature_banned`; do not bypass or retry aggressively.
- fal.ai reached the provider/account layer but live generation failed because the account balance was exhausted.
- Current interpretation: Qwen Image is validated for Beijing and Singapore; US/Germany are model-availability failures for the tested Qwen Image models; Stability is a sanctioned-access/WAF issue; fal.ai needs balance top-up before retesting.

## p2.9a39-model-api-live-matrix-doc-sync

- Recorded current model API live verification matrix.
- DeepSeek remains the existing primary path and release baseline.
- Kimi / Moonshot endpoint was reachable at `https://api.moonshot.ai/v1/models`, but the provided key returned HTTP 401 `Invalid Authentication`; mark as endpoint reachable but not verified, not as unsupported.
- GLM / Zhipu / Z.AI `/models` validation passed across the tested key-source by endpoint matrix:
  - Domestic BigModel general: `https://open.bigmodel.cn/api/paas/v4`.
  - Domestic BigModel Coding Plan: `https://open.bigmodel.cn/api/coding/paas/v4`.
  - Z.AI general: `https://api.z.ai/api/paas/v4`.
  - Z.AI Coding Plan: `https://api.z.ai/api/coding/paas/v4`.
  - Both the domestic BigModel key and the Z.AI key passed against all four endpoints.
- Qwen / DashScope pay-as-you-go `/models` validation passed:
  - Beijing: `https://dashscope.aliyuncs.com/compatible-mode/v1`, `qwen-plus`.
  - Singapore: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, `qwen-plus`.
  - US Virginia: `https://dashscope-us.aliyuncs.com/compatible-mode/v1`, `qwen-plus-us`.
- Qwen Coding Plan and Token Plan were not script-tested because official usage constraints distinguish them from ordinary automation-style probes; they require guided config and tool-path validation.
- Custom provider is validated as a mechanism because the GLM/Zhipu/Z.AI and Qwen matrices used `--provider custom` with explicit base URLs and models.
- Future README, wizard, and config guidance must distinguish verified, endpoint reachable but auth failed, implemented but not yet verified, not script-tested, and abandoned states. Do not mark untested providers as unsupported.
- After matrix testing, prepare a separate architecture audit branch for a potential AnyCodex-style refactor. The audit should identify DeepSeek-specific logic such as `reasoning_content`, reasoning/thinking event handling, model catalog assumptions, and which proxy layers can be generalized across providers.

## p2.9a40-config-guide-provider-surface-repair

- Repaired the public configuration surface after p2.9a40 audit.
- Removed the remaining Brave Search README quick-reference row and removed Brave from the installer validation surface.
- Replaced ambiguous model API guide commands with explicit site and plan provider names:
  - `zhipu`, `zhipu-coding`, `zai`, `zai-coding`.
  - `qwen-beijing`, `qwen-singapore`, `qwen-us`.
- Kept legacy `glm` and `qwen` only as internal canonicalization/backward-config helpers, while tests prevent these shortcuts from being used as public CLI choices or recommended README commands.
- Added test coverage so README examples parse through the CLI and continue to distinguish provider states rather than reverting to a binary supported/unsupported label.

## p2.9a41-post-p2.9a40-handoff-sync

- Synced developer handbooks and the development log after the p2.9a40 provider-surface repair.
- Current post-p2.9a40 state:
  - `master=origin/master=cd8e4d9`.
  - Internal tag `p2.9a40-config-guide-provider-surface-repair=cd8e4d9`.
  - Public release tag `v0.3.7-alpha=466706f`, unchanged.
  - Plain public tag `v0.3.5` remains absent.
  - p2.9a40 passed full tests with `363 passed`.
- Provider-surface result:
  - Brave Search removed from public and guided web search configuration.
  - Model API public guidance now uses explicit Zhipu/Z.AI/Qwen site and plan providers rather than ambiguous `glm` and `qwen` shortcuts.
- Next planned line:
  - `work/p2.10-anycodex-provider-architecture-audit`.
  - Start with read-only architecture evidence collection.
  - Assess DeepSeek-specific logic and the feasibility of an AnyCodex-style provider abstraction.
  - Keep the broader third-party tool replacement objective separate from a single SerpAPI-style bridge.

## p2.10a2-config-refresh-and-effort-ux

- Added a CoDeepSeedeX-only post-config apply hook for successful config writes.
- API key, model, and effort config updates refresh already-running local stable/thinking proxy processes instead of requiring users to infer whether a restart is needed.
- The hook reports `all updates applied` when the local apply path completes.
- WeClaw stop/start/resume automation remains out of scope for this repository line.
- User-facing effort guidance no longer recommends `medium`; compatibility inputs `low` and `medium` are stored as `high` for the DeepSeek proxy path.
- README and README.zh-CN now include a compact behavior-change table for milestone CLI/workflow changes.

## p2.10a3-provider-validation-region-status

- Updated non-generation image validation so HTTP 200 provider error bodies are accepted as probe evidence when no authentication error is detected.
- Added explicit Qwen Image region choices for Beijing, Singapore, US Virginia, and Germany Frankfurt.
- Beijing and Singapore remain selectable for Qwen Image. US Virginia and Germany Frankfurt are listed but return a model-unavailable status for qwen-image-2.0-pro.
- Updated README behavior-change tables and developer handbook rules for provider validation classification and Qwen Image regional status.

## p2.10a4-config-menu-model-provider-ux

- Made `dsproxy config set-model` the primary model API setup entrypoint for provider, upstream model, and optional API key configuration.
- Kept `dsproxy config set-api-key` as a compatibility alias and added a compatibility/deprecation note in JSON output.
- Preserved the old model-only flow: `dsproxy config set-model deepseek-v4-flash`.
- Updated the guided wizard model provider catalog so supported model API providers are selectable from the wizard instead of only DeepSeek being handled as supported.
- Updated installer guidance, README, README.zh-CN, developer handbooks, and tests to prefer `set-model` for model API setup.

## p2.10a5-post-config-ux-consistency

- Synchronized the model API command summary shown by `dsproxy config wizard --non-interactive` with the full explicit provider surface.
- Replaced the remaining README and README.zh-CN Qwen Coding Plan custom-provider examples from the old `set-api-key --provider custom --model ...` form to the new `set-model <model> --provider custom --base-url ...` form.
- Added tests to prevent README custom model API examples from regressing to the old `set-api-key --provider custom` command shape.
