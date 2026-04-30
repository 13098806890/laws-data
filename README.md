# 中国法律法规数据库

中国现行法律法规的结构化数据集，包含原始文档（docx）、结构化 JSON、SQLite 数据库和 Markdown 全文，供检索、研究和应用开发使用。

## 数据概览

| 类别 | 数量 |
|------|------|
| 法律 | 442 |
| 行政法规 | 727 |
| 司法解释 | 682 |
| 法律解释 | 25 |
| 修正案 | 12 |
| 有关法律问题和重大问题的决定 | 4 |
| 监察法规 | 3 |
| 宪法 | 1 |
| **合计** | **1896** |

覆盖法律部门：宪法相关法、民法商法、民法典、行政法、经济法、社会法、刑法、诉讼与非诉讼程序法

## 目录结构

```
laws_data/
├── sources/               # 源文件（docx/doc + xlsx 目录索引）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── json/                  # 结构化 JSON（按 category 分类，pipeline 产物）
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── markdown/              # Markdown 全文（按 legal_domain 分类，从 DB 生成）
│   ├── 民法商法/
│   │   └── 司法解释/
│   ├── 刑法/
│   │   ├── 司法解释/
│   │   └── 法律解释/
│   └── ...
├── scripts/
│   ├── config.py          # 路径配置
│   ├── utils.py           # 公共工具函数
│   ├── docx_to_json/      # 第一阶段：docx → JSON
│   │   ├── converter.py
│   │   ├── domain.py
│   │   ├── effective_date.py
│   │   └── structure.py
│   ├── json_to_db/        # 第二阶段：JSON → SQLite
│   │   └── builder.py
│   ├── db_to_md/          # 第三阶段：DB → Markdown
│   │   └── renderer.py
│   ├── pipeline.py        # 完整流程（三阶段串联）
│   └── verify_db.py       # 数据库与 JSON 一致性验证
├── law_content.db         # SQLite 数据库（pipeline 产物，约 72MB）
└── CLAUDE.md              # 详细技术说明
```

## JSON 数据格式

每个文件对应一部法律，文件名格式为 `{标题}_{公布日期YYYYMMDD}.json`。

**无编结构（大多数法律）：**

```json
{
  "title": "中华人民共和国合同法",
  "category": "法律",
  "pub_date": "1999-03-15",
  "effective_date": "1999-10-01",
  "promulgation_info": "...",
  "issuing_org": "全国人民代表大会常务委员会",
  "doc_number": "",
  "legal_domain": "民法商法",
  "total_articles": 428,
  "chapters": [
    {
      "title": "第一章　一般规定",
      "order_index": 1,
      "global_order": 1,
      "sections": [],
      "articles": [
        {
          "title": "第一条　",
          "content": "第一条　为了保护合同当事人的合法权益...",
          "order_index": 1,
          "global_order": 2
        }
      ]
    }
  ],
  "full_text": "..."
}
```

**有编结构（民法典、刑法、民事诉讼法等 8 部）：**

```json
{
  "title": "中华人民共和国民法典",
  "parts": [
    {
      "title": "第一编　总则",
      "order_index": 1,
      "global_order": 1,
      "chapters": [...]
    }
  ]
}
```

`global_order` 为深度优先全局序号，按此字段排序即可得到完整正文顺序。

## SQLite 数据库

运行 `python3 scripts/pipeline.py` 生成 `law_content.db`（约 72MB）。

### laws 表

| 字段 | 说明 |
|------|------|
| id | 主键 |
| title | 完整标题 |
| filename | 唯一键，格式 `{标题}_{YYYYMMDD}` |
| category | 法律分类 |
| legal_domain | 法律部门 |
| pub_date | 公布日期 |
| effective_date | 生效日期 |
| promulgation_info | 发布说明全文 |
| issuing_org | 发布机关（最高人民法院 / 最高人民检察院 / 国务院等） |
| doc_number | 发文字号（法释〔2000〕29号 等） |
| version_date | 版本日期（多版本区分） |
| is_current | 是否现行版本（默认 1） |

### nodes 表

| 字段 | 说明 |
|------|------|
| id | 主键 |
| law_id | 所属法律 |
| parent_id | 父节点（编的 parent 为 NULL） |
| type | `part` / `chapter` / `section` / `article` |
| title | 编/章/节标题 |
| article_number | 条文编号，如"第一条" |
| content | 展示文本（编/章/节为标题，条文为正文） |
| order_index | 在父节点内的序号 |
| global_order | 全文深度优先序号 |

### nodes_fts 虚拟表
FTS5，`tokenize='trigram'`，索引 `content` 和 `article_number`，支持任意中文短语搜索。

### 常用查询

```sql
-- 按顺序展示某法律全部内容
SELECT * FROM nodes WHERE law_id = ? ORDER BY global_order;

-- 某章下所有条文
SELECT * FROM nodes WHERE parent_id = ? AND type = 'article';

-- 全文搜索
SELECT n.article_number, n.content, l.title AS law_title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- 按法律部门筛选
SELECT * FROM laws WHERE legal_domain = '民法商法' AND is_current = 1;

-- 查某机构发布的全部司法解释
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
```

## 重新生成

```bash
pip install python-docx xlrd
python3 scripts/pipeline.py        # 完整流程：docx → JSON → DB → Markdown

# 各阶段也可单独运行
cd scripts
python3 -m docx_to_json.converter  # 仅重新生成 JSON
python3 -m json_to_db.builder      # 仅重新生成数据库
python3 -m db_to_md.renderer       # 仅重新生成 Markdown

python3 scripts/verify_db.py       # 验证数据库与 JSON 一致性（可选）
```

更新源文件后直接重跑 `pipeline.py` 即可，无需手动干预。
