# 故障排查

## 端口被占用

现象：

    address already in use

检查：

    ss -ltnp | grep -E ':8000|:8001'

停止thinking proxy：

    dsproxy stop --thinking

如果仍有旧进程，手动kill后再启动。

## CLI版本与服务版本不一致

运行：

    dsproxy doctor --thinking

重点看：

    version_match

如果为false，说明端口上运行的是旧版本服务。停止旧服务后重启。

## API key缺失

检查：

    echo "$DEEPSEEK_API_KEY"

设置：

    export DEEPSEEK_API_KEY="..."

## Codex profile不存在

重新安装：

    dsproxy install-codex-profile

检查Codex配置：

    grep -nA20 'profiles.deepseek-thinking' ~/.codex/config.toml

## 上下文成本过高

查看usage：

    dsproxy usage --thinking --summary
    dsproxy usage --thinking --summary --purpose compaction
    dsproxy usage --thinking --summary --purpose tool_bridge

如果tool_bridge过高，可以降低工具轮数。

如果compaction过高，可以检查：

    python3 -m json.tool .debug/context_compaction_report.json
