# 架构说明

## 总体结构

Codex通过OpenAI Responses风格接口访问本地proxy。

    Codex CLI
      -> Responses API
    deepseek-responses-proxy
      -> ChatCompletions API
    DeepSeek upstream

## 关键模块

deepseek_responses_proxy/app.py是FastAPI应用主体。

deepseek_responses_proxy/cli.py提供dsproxy命令行入口。

SQLite保存response历史和usage ledger。

.debug保存上下文裁剪、压缩、工具桥接和活性守卫报告。

## 关键能力

- Responses envelope转换
- tool_call和function_call协议修复
- Codex工具转发
- 上下文裁剪
- 持久本地压缩
- 活性守卫和LLM judge
- usage按内部调用归因
- 自适应压缩预算策略

## 用量归因

v2.3a9后，每次上游DeepSeek调用都会记录usage event。

重要字段：

- purpose
- call_index
- requested_model
- effective_model
- upstream_model
- prompt_tokens
- completion_tokens
- total_tokens

