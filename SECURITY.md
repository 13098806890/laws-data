# Security Policy

## Supported Versions

本仓库为数据 + 工具仓库，主库数据库（law_content.db）通过 GitHub Releases 发布。当前支持最新 release 版本。

## Reporting a Vulnerability

请**不要**通过公开 Issue 报告安全问题。请发送邮件至 [INSERT SECURITY EMAIL]，并在邮件中说明：

- 漏洞类型与影响范围
- 复现步骤
- 受影响的脚本/文件

我们会尽快响应（目标 48 小时内确认）。

## Security Notes

- **数据准确性**：本仓库数据来自官方公开渠道，但处理 pipeline 可能引入解析误差。关键法律决策请以官方来源为准（flk.npc.gov.cn / gongbao.court.gov.cn）。
- **API Key**：`scripts/` 中的 LLM 调用脚本（translate_to_en.py 等）通过环境变量读取 API Key，禁止将 Key 提交到代码中。
- **供应链安全**：依赖仅 `python-docx`、`xlrd` 两个库。提交依赖变更时请谨慎评估。
