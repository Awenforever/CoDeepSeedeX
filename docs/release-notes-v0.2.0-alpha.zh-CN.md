# CoDeepSeedeX v0.2.0-alpha

## 概要

内部里程碑：`v2.6a2-release-upgrade-defaults`。


本版本在正式发布前完善升级体验。

## 变更

- `dsproxy upgrade`不再默认升级到当前已安装版本。
- `dsproxy upgrade`现在默认更新到`origin/master`上的最新`master`。
- README中的升级内容已移动到one-line install后面。
- 默认升级命令不再硬编码具体版本。
- 对`v0.1.0-alpha`等旧版本，继续使用one-line installer作为兼容升级路径。

## 升级

默认升级到最新版：

```bash
dsproxy upgrade
```

预览：

```bash
dsproxy upgrade --dry-run
```

旧版本没有`dsproxy upgrade`时：

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```
