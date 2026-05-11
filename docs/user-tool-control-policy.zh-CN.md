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


## 10.组合审计修正记录

关键词组合审计发现两类边界问题：

```text
先解释，再处理目标测试
日志里出现“不要调用工具”是什么意思
What does "do not use tools" mean?
If I say "do not run commands", how would you classify it?
```

修正规则：

```text
“再处理”应视为有序后续动作，不应默认归为ambiguous_answer_first。
引用、日志、字段、句子解释、what does、if I say等元讨论语境，应优先归为quoted_or_meta_stop_discussion。
```

这些规则只修正分类，不启用真实工具拦截。


## 11.P1b enabled turn-control实现边界

P1b第一版enabled只启用turn-control，不启用命令级危险审计。

启用方式：

```text
DEEPSEEK_PROXY_USER_TOOL_CONTROL_POLICY_MODE=enabled
```

实际生效的decision：

```text
would_suppress_tools
split_turn_required
```

生效行为：

```text
1.本轮传给上游的tools被移除。
2.本轮liveness retry被抑制。
3.如果上游仍返回tool_call，proxy不会执行工具，而是返回最终assistant说明消息。
```

暂不生效的decision：

```text
observe_only
would_require_confirmation
allow_tools
```

暂不处理：

```text
delete/overwrite命令级审计
shell参数级危险命令识别
ambiguous_stop真实拦截
ambiguous_answer_first真实拦截
```


## 12.自动注入工具的移除语义

P1b enabled turn-control中的`tools_removed_from_upstream`表示本轮实际从上游payload移除的全部工具，而不只表示用户请求中显式提供的工具。

例如用户请求里只显式提供`shell`，但proxy在运行时还自动追加`proxy_echo`和`proxy_time`，那么在以下信号触发时：

```text
explicit_tool_stop
answer_or_explain_only
ordered_explain_then_continue
```

实际移除结果应为：

```text
tools_removed_from_upstream=["shell","proxy_echo","proxy_time"]
effective_tool_names=[]
```

这是预期行为。原因是用户要求“不要继续调用工具”或“先解释”时，本轮应移除所有可用工具，包括proxy自动注入的只读辅助工具。否则模型仍可能通过自动注入工具进入tool path，违背turn-control边界。

非拦截路径不应移除这些自动注入工具。例如：

```text
ambiguous_stop → observe_only
quoted_or_meta_stop_discussion → allow_tools
```

这类场景下，`effective_tool_names`可以同时包含用户请求工具和`proxy_echo`、`proxy_time`。


## 13.P1c命令级风险dry-run报告

P1c第一版只新增命令级风险dry-run报告，不改变工具执行行为。

报告路径：

```text
.debug/user_tool_command_risk_report.json
```

触发位置：

```text
模型返回tool_call之后
proxy本地执行proxy工具或MCP代理工具之前
```

原因是命令参数只在`tool_call["function"]["arguments"]`中出现。pre-upstream阶段只能看到工具schema和工具名，无法判断具体命令是否包含删除、覆写或破坏性操作。

当前dry-run报告字段包括：

```text
mode
phase
tool_call_count
tool_names
max_command_risk
decision_if_enabled
tool_calls[].tool_name
tool_calls[].tool_name_risk
tool_calls[].command_risk
tool_calls[].candidate_count
tool_calls[].candidates
tool_calls[].arguments_preview
```

风险级别：

```text
C0_no_command_or_no_arguments
C1_readonly_or_unknown
C2_side_effect
C3_destructive_or_overwrite
```

第一版识别范围包括：

```text
rm/rmdir/del/Remove-Item
git reset --hard
git clean -fd/-fdx
git push --force
git branch -D
git tag -d
SQL drop/truncate/delete/update
shell重定向覆写
tee文件写入
mv/cp -f潜在覆写
rsync --delete
dd of=
apply_patch Add/Update/Delete File
```

当前不会真实拦截这些命令。`decision_if_enabled=would_require_confirmation`只表示未来enabled阶段应要求确认或阻止自动执行。


## 14.P1c Codex-aligned C4-only边界

P1c后续策略必须遵循以下原则：

```text
Proxy must not create a narrower safety boundary than Codex for normal development workflows.
```

中文表述：

```text
proxy不得把正常开发工作流的安全边界缩得比Codex更窄。
Codex沙箱仍然是常规编辑、写文件、apply_patch、依赖安装、项目内清理的默认安全边界。
proxy只补充C4灾难级风险门，用于磁盘级、系统根目录、用户目录、Windows挂载盘、生产数据库等大范围不可逆操作。
```

因此，P1c风险等级调整为：

```text
C0_no_command_or_no_arguments
C1_readonly_or_unknown
C2_routine_side_effect
C3_codex_governed_destructive
C4_catastrophic_or_out_of_sandbox
```

默认执行边界：

```text
C0/C1：只观察
C2：允许，属于正常开发副作用
C3：允许，交给Codex沙箱和Codex审批策略
C4：未来proxy gate候选，需要强确认或拦截
```

正常开发动作不应被proxy拦截：

```text
apply_patch Update File: deepseek_responses_proxy/app.py
apply_patch Add File: tests/test_x.py
write_file docs/new.md
write_file /tmp/report.txt
rm -rf .pytest_cache
rm -rf __pycache__
rm -rf dist
rm -rf build
rm -rf /tmp/v2.7*.txt
git add
git commit
依赖安装
```

C4灾难级动作示例：

```text
rm -rf /
rm -rf /*
rm -rf ~
rm -rf /home
rm -rf /home/*
rm -rf /mnt/c
rm -rf /mnt/c/*
rm -rf /mnt/d
rm -rf /mnt/d/*
Remove-Item -Recurse -Force C:\
Remove-Item -Recurse -Force D:\
del /s /q C:\*
del /s /q D:\*
format C:
format D:
diskpart clean
mkfs.*
dd if=... of=/dev/sdX
drop database
truncate production table
git push --force到main/master/production
```

`decision_if_enabled`的新语义：

```text
observe_only：只观察
allow_routine_side_effect：允许，正常开发副作用
allow_codex_governed：允许，交给Codex沙箱或审批策略
would_require_c4_confirmation：未来C4-only gate候选
```

当前阶段仍是dry-run，不启用真实拦截。


## 15.P1c C4gate dry-run字段

`v2.7a42a1`只增加C4gate观测字段，不启用真实拦截。该阶段用于在真实长会话中观察未来C4gate会如何判定。

新增字段：

```text
c4_gate_mode
c4_gate_triggered
c4_gate_action
c4_gate_tool_call_ids
c4_gate_tool_names
c4_gate_reasons
c4_gate_argument_previews
c4_gate_confirmation_required
c4_gate_resume_supported
c4_gate_effective
```

字段语义：

```text
c4_gate_triggered=true表示当前tool_call中存在C4_catastrophic_or_out_of_sandbox。
c4_gate_action=would_suppress_and_explain表示未来enabled gate会抑制工具执行并返回说明。
c4_gate_effective=false表示当前阶段没有真实拦截。
c4_gate_resume_supported=false表示当前不支持“继续”后自动恢复执行C4。
```

边界保持不变：

```text
C2_routine_side_effect不触发C4gate。
C3_codex_governed_destructive不触发C4gate。
只有C4_catastrophic_or_out_of_sandbox触发C4gate dry-run字段。
```
