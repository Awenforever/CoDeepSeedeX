# CoDeepSeedeX v0.3.5-alpha

## 概要

CoDeepSeedeX v0.3.5-alpha完成p2.8provider配置开发线，并将经过测试的alpha版本发布在commit `53897ad`。

## 变更

- 将API key验证集成到手动provider配置命令。
- 将API key验证集成到安装和bootstrap引导配置流程。
- provider验证继续保留在既有配置路径中，没有新增单独的`dsproxy config test-provider --kind web-search|image --provider <name>`命令。
- 扩展并加固web search和文生图provider支持。
- 新增model provider catalog相关能力。
- 更新README和运维说明，补充provider配置、免费额度和申请入口提示，以及`Other`自定义server路径。
- 新增`docs/custom_api_handoff.md`，作为自定义tool server配置的agent交接清单。

## Release状态

- 公开Release tag：`v0.3.5-alpha`
- Release标题：`CoDeepSeedeX v0.3.5-alpha`
- Release commit：`53897ad`
- Release资产：`bootstrap.sh`、`install.sh`
- 默认安装和升级目标：GitHub Latest Release

## 兼容性

alpha阶段公开tag保持`v0.3.5-alpha`形式。本次发布不要使用普通`v0.3.5`tag。
