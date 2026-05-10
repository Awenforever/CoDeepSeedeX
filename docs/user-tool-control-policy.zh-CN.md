# 用户工具控制策略手册

## 1.目标

本手册定义CoDeepSeedeX在用户表达“停止、暂停、先解释、先回答”等意图时，如何判断是否应继续工具相关流程。

本策略的核心目标不是理解所有自然语言，而是建立可审计、可回滚、低误伤的工具控制边界。

## 2.基本原则

### 2.1不依赖关键词穷举

自然语言无法穷举。策略不得简单写成“出现暂停或stop就禁止工具”。

### 2.2默认先dry-run

P1a阶段只记录策略判断，不改变真实工具执行行为。

默认模式：

```text
DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE=dry_run
```

dry-run只写报告和trace，不移除tools，不拦截tool_call，不改变tool bridge行为。

### 2.3高风险不等于所有外部副作用

本项目中，“真正高风险”默认指不可逆或难恢复的数据改变，尤其是删除、覆写、强制重置、不可恢复发布等。

点击、发送、发表、打开APP等属于用户可见外部副作用，不默认等同于高风险不可逆操作。

## 3.用户信号分类

### 3.1explicit_tool_stop

用户明确要求不要继续工具、命令、执行、运行、调用、ADB、uiautomator、截图等。

例子：

```text
不要继续执行命令
别再调用ADB了
先不要截图
do not run commands
no more tools
don't use tools
```

dry-run预期：

```text
decision_if_enabled=would_suppress_tools
```

### 3.2answer_or_explain_only

用户只要求先回答、先解释、先说明，没有明确授权同一轮继续执行后续工具任务。

例子：

```text
先回答我这个问题
先解释清楚
先不要急着往下做
answer first
explain first
```

dry-run预期：

```text
decision_if_enabled=would_suppress_tools
```

### 3.2.1ordered_explain_then_continue

用户明确表达有序并列任务：先解释或先回答，然后继续执行后续任务。

例子：

```text
先解释原因，然后继续执行测试
先说明方案，再运行命令
Explain first, then run the command
Answer first, then continue the test
```

dry-run预期：

```text
decision_if_enabled=split_turn_required
```

含义：enabled阶段不应在同一轮中一边解释一边执行工具。应先返回解释和计划，等待下一轮“继续”后再执行。否则用户并不能在工具执行前真正看到解释。

### 3.2.2ambiguous_answer_first

用户要求先解释，同时提到后续处理，但是否授权同轮继续执行不明确。

例子：

```text
先解释一下，然后看情况继续
先说说，再处理
Explain first, then maybe continue
```

dry-run预期：

```text
decision_if_enabled=would_require_confirmation
```

### 3.3ambiguous_stop

用户只说“停一下、暂停、hold on、stop”等，没有明确工具上下文。

例子：

```text
停一下
暂停
hold on
stop
wait
```

dry-run预期：

```text
decision_if_enabled=observe_only
```

enabled阶段不得直接等同于工具停止，应优先要求确认或只禁止保活重试。

### 3.4quoted_or_meta_stop_discussion

用户是在引用、讨论、解释某句“不要继续执行命令”，并非发出当前指令。

例子：

```text
帮我解释这句：“不要继续执行命令”是什么意思
如果我说do not use tools，你会怎么判断
日志里出现“暂停执行”是什么意思
```

dry-run预期：

```text
decision_if_enabled=allow_tools
```

### 3.5negated_stop

用户明确否定停止意图。

例子：

```text
不是让你停止执行
不要误以为我让你停
don't stop
not asking you to stop
```

dry-run预期：

```text
decision_if_enabled=allow_tools
```

## 4.assistant保活负样本

保活检测器的职责是防止agent说“我接下来运行命令”但没有发tool_call导致流程假停。

但如果assistant表达的是暂停执行并解释，不能触发保活重试。

应判为不需要tool_call的例子：

```text
接下来我将暂停执行任务，并且先向你解释清楚
我先不继续操作，先说明原因
你要求我不要继续执行命令，所以我先解释当前判断
I will pause tool execution and explain first
I’ll stop running commands and answer your question
```

仍应触发保活的例子：

```text
Now let me inspect the UI and run the next shell command:
dumpsys没返回内容。换用uiautomator2直接检查当前状态并截图：
```

## 5.工具风险分级

### R0_safe_readonly

低风险只读或无状态工具。

例子：

```text
proxy_status
proxy_time
proxy_usage_summary
proxy_balance
```

### R1_read_or_privacy_context

只读但可能暴露上下文、隐私或受prompt injection影响。

例子：

```text
截图
uiautomator dump
adb dumpsys
读取日志
读取文件
web搜索
```

这不是不可逆高风险。

### R2_external_or_user_visible_side_effect

可逆或可补救的外部副作用。

例子：

```text
点击
打开APP
跳转页面
发送消息
发表内容
提交表单
```

按当前项目边界，它们不默认归为真正高风险。

### R3_destructive_or_overwrite

不可逆或难恢复的数据改变。

例子：

```text
rm
rmdir
delete
overwrite
truncate
dd写盘
格式化
git reset --hard
git clean -fd
数据库drop/delete/update无备份
覆盖已有tag
force push
发布release后不可恢复覆盖
```

enabled阶段优先只对R3启用强确认或fail-closed。

### R3_capable_requires_command_audit

工具本身具有执行任意命令的能力，例如shell。仅凭工具名不能确定本次操作是否高风险，需要结合实际命令审计。

## 6.dry-run报告

P1a写入：

```text
.debug/user_tool_control_policy_report.json
```

核心字段：

```json
{
  "mode": "dry_run",
  "user_signal": "explicit_tool_stop",
  "decision_if_enabled": "would_suppress_tools",
  "tool_names": ["shell"],
  "tool_risks": {"shell": "R3_capable_requires_command_audit"},
  "max_tool_risk": "R3_capable_requires_command_audit",
  "policy_is_dry_run_only": true
}
```

## 7.enabled阶段原则

P1a不启用真实拦截。后续P1b若启用，应遵循：

```text
explicit_tool_stop + 任意工具 = suppress_tools
answer_or_explain_only + 任意工具 = suppress_tools
ordered_explain_then_continue + 任意工具 = split_turn_required
ambiguous_answer_first + 任意工具 = require_confirmation
ambiguous_stop + R3 = require_confirmation
ambiguous_stop + R0/R1/R2 = observe_only或require_confirmation
无停止信号 + R3_destructive_or_overwrite = require_confirmation
无停止信号 + R0/R1/R2 = allow_tools
```

## 8.不可承诺事项

本策略不能承诺完全理解用户意图，也不能保证零误判。

可承诺的是：

```text
判断过程可审计
dry-run不会改变执行行为
高风险定义明确
后续enabled可以fail-closed
误判样本可加入反例库回归测试
```


## 9.P1b顺序任务修正

P1b实现前必须区分“只要求先解释”和“先解释后继续执行”。

错误做法：

```text
answer_or_explain_first → 一律suppress_tools
```

修正做法：

```text
answer_or_explain_only → suppress_tools
ordered_explain_then_continue → split_turn_required
ambiguous_answer_first → require_confirmation
```

`split_turn_required`不是拒绝执行后续任务，而是把执行拆到下一轮。原因是同一轮工具调用通常发生在最终回复前，用户无法先看到解释再让工具执行。拆成两轮才能严格满足“先解释，然后执行”的顺序语义。
