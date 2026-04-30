# 🏛️ Chinese Laws & Regulations Database

[中文](README.md) · [Русский](README.ru.md)

> A structured open dataset of current Chinese laws and regulations — raw documents, structured JSON, SQLite database, and Markdown full text, for search, research, and application development.

---

## 📊 Data Overview

| Category | Count | law_id Range |
|----------|------:|--------------|
| 🔴 Constitution (宪法) | 1 | `1000001–1099999` |
| 🟠 Laws (法律) | 442 | `1100001–1999999` |
| 🟡 Amendments (修正案) | 12 | `2000001–2099999` |
| 🟡 Decisions (决定) | 4 | `2100001–2199999` |
| 🟢 Legal Interpretations (法律解释) | 25 | `3000001–3499999` |
| 🟢 Judicial Interpretations (司法解释) | 682 | `3500001–4999999` |
| 🔵 Administrative Regulations (行政法规) | 727 | `5000001–6499999` |
| 🔵 Supervisory Regulations (监察法规) | 3 | `6500001–6999999` |
| ⚪ Local Regulations (reserved) | — | `7000001–7999999` |
| ⚪ Local Rules (reserved) | — | `8000001–8999999` |
| **Total** | **1896** | |

**Legal domains covered:** Constitutional Law · Civil & Commercial Law · Civil Code · Administrative Law · Economic Law · Social Law · Criminal Law · Procedural Law

---

## 📁 Directory Structure

```
laws_data/
├── 📂 sources/                    # Source files (docx/doc + xlsx index)
├── 📂 json/                       # Structured JSON (by category, pipeline output)
├── 📂 markdown/                   # Full-text Markdown (by legal domain, from DB)
├── 📂 references/
│   └── article_references.json   # Article cross-references
├── 📂 scripts/
│   ├── config.py                  # Path configuration
│   ├── utils.py                   # Shared utilities
│   ├── generate_law_index.py      # Stable law_id assignment
│   ├── extract_references.py      # Citation extraction
│   ├── pipeline.py                # Full pipeline (with stage-skip flags)
│   ├── verify_db.py               # DB ↔ JSON consistency check
│   ├── docx_to_json/              # Stage 1: docx → JSON
│   ├── json_to_db/                # Stage 2: JSON → SQLite
│   └── db_to_md/                  # Stage 3: DB → Markdown
├── 📄 law_index.json              # Global law ID index (1896 entries)
└── 🗄️  law_content.db             # SQLite database (~100MB)
```

---

## 🗄️ Database Schema

Run `python3 scripts/pipeline.py` to generate `law_content.db`.

### 🟠 `laws` — One row per law

| Field | Type | Description |
|-------|------|-------------|
| `id` | INTEGER PK | Equals `law_id`, consistent with JSON files |
| `title` | TEXT | Full title |
| `filename` | TEXT UNIQUE | Format: `{title}_{YYYYMMDD}` |
| `category` | TEXT | Category (法律 / 行政法规 / 司法解释 …) |
| `legal_domain` | TEXT | Legal domain (民法商法 / 刑法 / 行政法 …) |
| `pub_date` | TEXT | Promulgation date `YYYY-MM-DD` |
| `effective_date` | TEXT | Effective date `YYYY-MM-DD` |
| `promulgation_info` | TEXT | Full promulgation notice text |
| `issuing_org` | TEXT | Issuing authority (Supreme Court / State Council …) |
| `doc_number` | TEXT | Document number (e.g. 法释〔2000〕29号) |
| `total_articles` | INTEGER | Total article count |
| `full_text` | TEXT | Full text (whitespace-normalized) |
| `version_date` | TEXT | Same as `pub_date`, for multi-version tracking |
| `is_current` | INTEGER | **1 = current version, 0 = historical** (latest pub_date wins) |

---

### 🔵 `nodes` — Unified storage for parts / chapters / sections / articles

| Field | Type | Description |
|-------|------|-------------|
| `id` | INTEGER PK | Auto-increment primary key |
| `law_id` | INTEGER FK | References `laws.id` |
| `parent_id` | INTEGER FK | Parent node (NULL for top-level parts) |
| `type` | TEXT | `part` / `chapter` / `section` / `article` |
| `title` | TEXT | Heading text; for articles same as `article_number` |
| `article_number` | TEXT | Article label, e.g. `第一条` (NULL for structural nodes) |
| `content` | TEXT | Display text (heading for structural nodes, body for articles) |
| `order_index` | INTEGER | Position within parent |
| `global_order` | INTEGER | Depth-first global sequence — `ORDER BY global_order` gives reading order |
| `part_num` | INTEGER | Part number (NULL if no part structure) |
| `chapter_num` | INTEGER | Chapter number |
| `section_num` | INTEGER | Section number (NULL if no section structure) |
| `article_num` | INTEGER | Article number (第十二条 → `12`) |

> **Precise lookup:** `WHERE law_id=1100001 AND chapter_num=3 AND article_num=15`

---

### 🟢 `nodes_fts` — Full-text search (virtual table)

| Field | Description |
|-------|-------------|
| `content` | Article body (mirrors `nodes.content`) |
| `article_number` | Article label |

- Engine: FTS5, `tokenize='trigram'`
- Supports arbitrary Chinese substring search (minimum 3 characters)
- `rowid` maps to `nodes.id`

---

### 🔴 `article_references` — Cross-article citations (placeholder, not yet populated)

| Field | Type | Description |
|-------|------|-------------|
| `from_id` | INTEGER FK | Citing node (`nodes.id`) |
| `to_id` | INTEGER FK | Cited node (`nodes.id`) |

> Current citation data is stored in `references/article_references.json` (see below).

---

## 📎 law_index.json — Global Law ID Index

One entry per law, IDs are permanent (new laws are appended, existing IDs never change):

```json
{
  "law_id":         1100001,
  "filename":       "中华人民共和国合同法_19990315",
  "title":          "中华人民共和国合同法",
  "category":       "法律",
  "legal_domain":   "民法商法",
  "pub_date":       "1999-03-15",
  "effective_date": "1999-10-01"
}
```

---

## 📋 JSON Format

Each file corresponds to one law. Filename: `{title}_{YYYYMMDD}.json`.

**Without part structure (most laws):**

```json
{
  "law_id": 1100001,
  "title": "中华人民共和国合同法",
  "category": "法律",
  "pub_date": "1999-03-15",
  "chapters": [
    {
      "title": "第一章　一般规定",
      "order_index": 1,
      "global_order": 1,
      "articles": [
        {
          "title": "第一条　",
          "content": "第一条　为了保护合同当事人的合法权益...",
          "order_index": 1,
          "global_order": 2
        }
      ]
    }
  ]
}
```

**With part structure (Civil Code, Criminal Law, Civil Procedure Law, etc. — 8 laws):**

```json
{
  "law_id": 1100313,
  "title": "中华人民共和国民法典",
  "parts": [
    {
      "title": "第一编　总则",
      "order_index": 1,
      "global_order": 1,
      "chapters": [ "..." ]
    }
  ]
}
```

---

## 🔗 article_references.json — Citation Graph

Covers only `is_current=1` laws. **2,784 citations** total (817 cross-law, 1,967 self-references), 94.7% resolved.

```json
{
  "from_law_id":      3500601,
  "from_law":         "人民检察院公益诉讼办案规则",
  "from_article":     "第六十六条",
  "from_article_num": 66,
  "from_chapter_num": 6,
  "from_section_num": 8,
  "from_part_num":    null,
  "refs": [
    {
      "type":           "cross_law",
      "to_law_id":      1100296,
      "to_law":         "中华人民共和国法官法",
      "to_article":     "第四十六条",
      "to_article_num": 46,
      "to_chapter_num": 4,
      "to_section_num": null,
      "to_part_num":    null,
      "resolved":       true,
      "raw_text":       "《中华人民共和国法官法》第四十六条"
    }
  ]
}
```

---

## ⚡ Common Queries

```sql
-- Full content of a law in reading order
SELECT * FROM nodes WHERE law_id = 1100001 ORDER BY global_order;

-- Precise article lookup: Civil Code Part 3, Chapter 5, Article 12
SELECT * FROM nodes
WHERE law_id = 1100313 AND part_num = 3 AND chapter_num = 5 AND article_num = 12;

-- Full-text search (any Chinese phrase, min 3 chars)
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- Current versions only
SELECT * FROM laws WHERE legal_domain = '民法商法' AND is_current = 1;

-- All judicial interpretations by the Supreme Court
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;

-- All versions of a law
SELECT title, pub_date, is_current FROM laws
WHERE title = '中华人民共和国公司法' ORDER BY pub_date;
```

---

## 🚀 Regeneration

```bash
pip install python-docx xlrd

# Full pipeline
python3 scripts/pipeline.py

# Skip stages (e.g. skip docx parsing when JSON already exists)
python3 scripts/pipeline.py --skip-docx
python3 scripts/pipeline.py --skip-docx --skip-index
python3 scripts/pipeline.py --skip-docx --skip-md

# Only regenerate citations
python3 scripts/pipeline.py --only-refs

# Run each stage individually
cd scripts
python3 -m docx_to_json.converter   # docx → JSON
python3 generate_law_index.py        # assign/update law_id
python3 -m json_to_db.builder        # JSON → DB
python3 -m db_to_md.renderer         # DB → Markdown
python3 extract_references.py        # extract citations

python3 verify_db.py                 # verify DB ↔ JSON consistency (optional)
```

After updating source files, simply re-run `pipeline.py` — no manual intervention needed.
