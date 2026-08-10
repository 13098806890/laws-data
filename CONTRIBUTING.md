# Contributing to laws_data

欢迎贡献！本仓库维护中国法律法规的结构化开放数据集。所有贡献者需遵循 [Code of Conduct](CODE_OF_CONDUCT.md)。

## 目录结构速览

- `sources/` — 原始 docx/doc 源文件（来自国家法律法规数据库 flk.npc.gov.cn）
- `json/` — 结构化 JSON（pipeline 产物）
- `json_en/` — 英文翻译（社区可贡献翻译）
- `scripts/` — pipeline 与工具脚本
- `law_content.db` — 主数据库（**不提交 git**，从 GitHub Releases 下载或本地构建）

## 如何贡献

### 1. 数据修正（最受欢迎）

发现法律条文内容、发布日期、生效日期错误时：

1. 在 `sources/` 中找到对应源文件（或直接从 flk.npc.gov.cn 下载正确版本）
2. 直接修改源文件或提交 Issue 说明差异（标题 + 链接）
3. 如果已修改源文件，运行 pipeline 重新生成：`python3 scripts/pipeline.py`

> ⚠️ **重要**：不要直接修改 `json/` 或 Markdown 产物，它们由 pipeline 全量重建，会覆盖你的修改。修改必须落在 `sources/` 或解析逻辑（`scripts/docx_to_json/`）。

### 2. 英文翻译

`json_en/` 是 git 可追踪的翻译文件，按 category 镜像 `json/` 结构。翻译流程：

```bash
export DEEPSEEK_API_KEY=sk-...
python3 scripts/translate_to_en.py --dry-run          # 查看待翻译量
python3 scripts/translate_to_en.py --tier T0,T1        # 按引用层级翻译
```

人工翻译可参考 `references/law_title_en_map.json`（标题英译）和 `references/legal_terms_glossary.json`（术语表）保持术语一致。

### 3. 代码改进

- 修复解析 bug：`scripts/docx_to_json/`
- 新增查询能力：`scripts/`
- 先跑通现有测试再提交

## 开发规范

- Python 3.10+，无严格 lint 要求，但请保持现有代码风格
- **不改动 `json/` 目录结构**（必须与 `sources/` 按 category 平铺对应，builder 依赖此约定）
- 新脚本禁止硬编码 `law_id` 分配规则，统一走 `scripts/law_id_registry.py`
- 不提交 `*.db`、`logs/`、`.source_hashes.json`（已在 .gitignore）
- 提交信息用中文或英文均可，描述清楚改动内容

## 提交流程

1. Fork 本仓库
2. 创建 feature 分支：`git checkout -b fix/xxx`
3. 修改并本地验证（如涉及数据，运行 pipeline）
4. 提交并推送，创建 Pull Request
5. 在 PR 描述中说明：改了什么、为什么、如何验证

## 本地环境搭建

```bash
git clone https://github.com/doxie/laws-data.git
cd laws-data
pip install python-docx xlrd

# 方式一：下载预构建数据库（推荐，含全部数据）
python3 scripts/download_db.py

# 方式二：从源码完整构建（约 5-10 分钟）
python3 scripts/pipeline.py
python3 scripts/verify_db.py
```

## Issue 规范

- **数据错误**：请附上正确的官方来源链接（flk.npc.gov.cn / gongbao.court.gov.cn）
- **Bug 报告**：附复现步骤、期望结果、实际结果、相关日志
- **功能请求**：说明使用场景和预期行为
