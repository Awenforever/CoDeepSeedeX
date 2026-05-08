# v2.6a1-docs-and-upgrade-path

## 概要

本版本新增两种互相兼容的升级方式，并同步v2.6a引入的Codex默认MCP策略文档。

## 升级方式

- `dsproxy upgrade`：用于较新版本的git checkout安装
- 再次运行one-line installer：用于`v0.1.0-alpha`等旧版本

## 变更

- 新增`dsproxy upgrade`
- 新增中英文升级文档
- 更新README升级说明
- 说明v2.6a+的MCP行为：
  - 默认策略为`codex`
  - 默认后端为`stdio`
  - 默认不需要proxy侧MCP allowlist
  - 默认不拒绝写入型MCP tool
- 说明当前只支持stdio MCP传输

## 兼容性

旧版本没有`dsproxy upgrade`命令，应重新运行目标版本one-line installer完成升级。
