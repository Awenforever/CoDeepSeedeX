# Security Notes

This project lets Codex talk to DeepSeek upstream models through a local proxy.

Depending on your Codex configuration, the model may call tools, modify files, run commands and invoke MCP tools.

## Principles

Bind only to localhost:

    127.0.0.1

Do not expose the proxy to the public internet.

Do not use high-privilege Codex profiles in untrusted repositories.

Do not commit DEEPSEEK_API_KEY to Git.

The .debug directory and SQLite usage database may contain request summaries, paths, tool output summaries and usage information.

## Recommendations

- Use dsproxy doctor to check runtime state
- Use deepseek-thinking only in trusted workspaces
- Be careful with danger-full-access
- Review .debug and logs regularly
- Check for leaked secrets before release
