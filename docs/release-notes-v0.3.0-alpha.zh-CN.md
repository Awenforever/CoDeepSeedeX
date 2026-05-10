# CoDeepSeedeX v0.3.0-alpha

CoDeepSeedeX第三个公开alpha版本。

**强烈推荐所有用户升级**，尤其是通过`deepseek-thinking`运行长Codex会话的用户。

Highlights:

- 改进`deepseek-thinking`长会话上下文效率
- thinking模式默认启用tool-outputtrimming
- 超大的`shell_command`和`interactive_shell`输出会在重新进入模型上下文前被压缩
- 大型结构化工具输出会尽量先紧凑序列化，再进入裁剪路径
- `image_payload`类工具输出有专门的12000字符上限
- 新增`dsproxy debug behavioral --thinking`运行态ready检查
- 真实验证快照：已从`shell_command`和`interactive_shell`裁掉`44822`字符
- 快照收益：约等于latest observed context size的`16.6%`，或max observed context size的`11.1%`
- README已补充当前compaction类别和行为
- runtime版本同步为`v0.3.0-alpha`
- 完整测试通过：242 passed
- 已在干净checkout上验证upgrade dry-run
- 发布后runtime验证通过：thinking proxy ready，behavioral check ready

从旧版本升级：

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

从本版本以后升级：

```bash
dsproxy upgrade
```

预览升级：

```bash
dsproxy upgrade --dry-run
```

验证：

```bash
dsproxy --version
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
dsproxy debug behavioral --thinking --limit 200 --timeout 5
```

已知限制：

- 本版本改进的是tool-outputtrimming和long-sessionobservability，不等同于完全复现原生Codex的semanticcompaction。
- 超大工具输出的中间部分可能被省略。如果需要精确复现，请把完整日志保存为文件。
- 大imagepayload真实会话验证仍是独立后续工作。
