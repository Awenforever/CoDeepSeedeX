# 升级

CoDeepSeedeX支持两种互相兼容的升级方式。

## 方式A：dsproxy upgrade

适用于已经包含`upgrade`命令的新版本：

```bash
dsproxy upgrade
```

预览升级计划：

```bash
dsproxy upgrade --dry-run
```

常用选项：

```bash
dsproxy upgrade --skip-profile
dsproxy upgrade --no-restart
dsproxy upgrade --allow-dirty
```

该命令会：

1.确认当前安装是git checkout
2.备份本地env文件和Codex配置
3.拉取tags
4.切换到目标tag
5.以editable模式重新安装包
6.默认刷新Codex profiles，除非使用`--skip-profile`
7.默认重启本地proxy，除非使用`--no-restart`
8.默认验证`/healthz`，除非使用`--no-verify`

## 方式B：再次运行one-line installer

适用于从`v0.1.0-alpha`等旧版本升级，或当前环境还没有`dsproxy upgrade`命令的情况：

```bash
curl -fsSL https://raw.githubusercontent.com/Awenforever/CoDeepSeedeX/master/scripts/install.sh | bash
```

该方式与方式A兼容。安装器会刷新本地安装和Codex profiles，默认保留本地env和Codex配置。

除非确实想删除本地数据，否则不要使用卸载命令里的`--remove-files`。

## 验证

```bash
dsproxy --version
dsproxy doctor --thinking
curl -sS http://127.0.0.1:8000/healthz
curl -sS http://127.0.0.1:8001/healthz
```
