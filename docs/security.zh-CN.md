# 安全说明

本项目会让Codex通过本地proxy与DeepSeek上游模型交互。

根据Codex配置，模型可能触发工具调用、文件修改、命令执行和MCP工具调用。

## 基本原则

只监听本地地址：

    127.0.0.1

不要开放公网端口。

不要在不可信仓库中使用高权限Codex配置。

不要把DEEPSEEK_API_KEY提交到Git。

.debug目录和SQLite usage数据库可能包含请求摘要、路径、工具输出摘要和用量信息。

## 建议

- 使用dsproxy doctor检查运行态
- 只在可信工作区中使用deepseek-thinking
- 谨慎使用danger-full-access
- 定期查看.debug和日志
- 发布前检查密钥泄漏

