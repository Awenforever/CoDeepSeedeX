# 发布检查清单

本清单用于准备第一个公开技术预览版。

目标发布标签：

    v0.1.0-alpha

## 必要检查

- 确认git status为空
- 确认全量pytest通过
- 确认dsproxy --version输出目标版本
- 确认dsproxy doctor --thinking显示version_match=true
- 确认dsproxy install-codex-profile可写入临时Codex配置
- 确认dsproxy uninstall-codex-profile只删除自身profile和provider
- 确认scripts/install.sh通过bash -n
- 确认scripts/secret-scan.py无发现
- 确认README.md和README.zh-CN.md没有把私人路径作为安装默认值
- 公开一行安装前，必须确认scripts/install.sh中的仓库地址正确
- 测试fresh clone安装
- 测试WSL安装
- 测试缺失DEEPSEEK_API_KEY时的诊断提示
- 确认proxy只监听127.0.0.1
- 确认没有提交密钥

## 发布说明

见：

    docs/release-notes-v0.1.0-alpha.en.md
    docs/release-notes-v0.1.0-alpha.zh-CN.md
