# 使用手册

## 常用命令

查看版本：

    dsproxy --version

初始化配置：

    dsproxy config init

启动thinking proxy：

    dsproxy start thinking

查看状态：

    dsproxy status thinking

诊断：

    dsproxy doctor --thinking

查看日志：

    dsproxy logs --thinking --lines 120

停止：

    dsproxy stop thinking

## Codex

安装profile：

    dsproxy install-codex-profile

运行：

    codex --profile deepseek-thinking

## 用量统计

总览：

    dsproxy usage --thinking --summary

按内部调用类型查看：

    dsproxy usage --thinking --summary --purpose primary
    dsproxy usage --thinking --summary --purpose tool_bridge
    dsproxy usage --thinking --summary --purpose compaction
    dsproxy usage --thinking --summary --purpose liveness_judge
    dsproxy usage --thinking --summary --purpose liveness_retry

## purpose字段

primary表示主模型调用。

tool_bridge表示工具调用后的续跑。

compaction表示上下文压缩摘要调用。

liveness_judge表示判断模型是否应该继续调用工具的轻量判定调用。

liveness_retry表示活性守卫触发后的重试调用。

## Codex TUI内置命令

进入`codex --profile deepseek-thinking`后，可以使用`/status`查看状态，使用`/model`切换模型或推理强度，使用`/plan`进入或使用任务规划模式。

## 升级

参见[升级](upgrade.zh-CN.md)了解`dsproxy upgrade`和再次运行one-line installer两种升级路径。
