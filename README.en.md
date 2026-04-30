# Chinese Laws & Regulations Database

A structured dataset of current Chinese laws and regulations, including source documents (docx), structured JSON, SQLite database, and Markdown full text — for search, research, and application development.

## Data Overview

| Category | Count |
|----------|-------|
| Laws (法律) | 442 |
| Administrative Regulations (行政法规) | 727 |
| Judicial Interpretations (司法解释) | 682 |
| Legal Interpretations (法律解释) | 25 |
| Amendments (修正案) | 12 |
| NPC Decisions (有关法律问题和重大问题的决定) | 4 |
| Supervisory Regulations (监察法规) | 3 |
| Constitution (宪法) | 1 |
| **Total** | **1896** |

Legal domains covered: Constitutional Law, Civil & Commercial Law, Civil Code, Administrative Law, Economic Law, Social Law, Criminal Law, Procedural Law

## Directory Structure

```
laws_data/
├── sources/               # Source files (docx/doc + xlsx index)
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── json/                  # Structured JSON (organized by category, pipeline output)
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── markdown/              # Markdown full text (organized by legal_domain, generated from DB)
│   ├── 民法商法/
│   │   └── 司法解释/
│   ├── 刑法/
│   │   ├── 司法解释/
│   │   └── 法律解释/
│   └── ...
├── scripts/
│   ├── config.py          # Path configuration
│   ├── utils.py           # Shared utilities
│   ├── docx_to_json/      # Stage 1: docx → JSON
│   │   ├── converter.py
│   │   ├── domain.py
│   │   ├── effective_date.py
│   │   └── structure.py
│   ├── json_to_db/        # Stage 2: JSON → SQLite
│   │   └── builder.py
│   ├── db_to_md/          # Stage 3: DB → Markdown
│   │   └── renderer.py
│   ├── pipeline.py        # Full pipeline (all 3 stages)
│   └── verify_db.py       # DB vs JSON consistency check
├── law_content.db         # SQLite database (pipeline output, ~72MB)
└── CLAUDE.md              # Technical reference (Chinese)
```

## JSON Format

Each file corresponds to one law, named `{title}_{promulgation_date_YYYYMMDD}.json`.

**Without parts structure (most laws):**

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

**With parts structure (Civil Code, Criminal Law, Civil Procedure Law, etc. — 8 laws total):**

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

`global_order` is a depth-first global sequence number — sorting by this field gives the correct reading order.

## SQLite Database

Run `python3 scripts/pipeline.py` to generate `law_content.db` (~72MB).

### laws table

| Field | Description |
|-------|-------------|
| id | Primary key |
| title | Full title |
| filename | Unique key, format `{title}_{YYYYMMDD}` |
| category | Document category |
| legal_domain | Legal domain |
| pub_date | Promulgation date |
| effective_date | Effective date |
| promulgation_info | Full promulgation notice text |
| issuing_org | Issuing authority (Supreme Court / Supreme Procuratorate / State Council, etc.) |
| doc_number | Document number (e.g. 法释〔2000〕29号) |
| version_date | Version date (for multi-version distinction) |
| is_current | Whether this is the current version (default 1) |

### nodes table

| Field | Description |
|-------|-------------|
| id | Primary key |
| law_id | Parent law |
| parent_id | Parent node (NULL for parts) |
| type | `part` / `chapter` / `section` / `article` |
| title | Part/chapter/section title |
| article_number | Article number, e.g. "第一条" |
| content | Display text (title for structural nodes, body text for articles) |
| order_index | Sequence within parent node |
| global_order | Depth-first global sequence number |

### nodes_fts virtual table
FTS5 with `tokenize='trigram'`, indexing `content` and `article_number`. Supports arbitrary Chinese phrase search (minimum 3 characters).

### Common Queries

```sql
-- Display full law content in order
SELECT * FROM nodes WHERE law_id = ? ORDER BY global_order;

-- All articles in a chapter
SELECT * FROM nodes WHERE parent_id = ? AND type = 'article';

-- Full-text search
SELECT n.article_number, n.content, l.title AS law_title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- Filter by legal domain
SELECT * FROM laws WHERE legal_domain = '民法商法' AND is_current = 1;

-- All judicial interpretations from the Supreme Court
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
```

## Regenerating

```bash
pip install python-docx xlrd
python3 scripts/pipeline.py        # Full pipeline: docx → JSON → DB → Markdown

# Each stage can also be run independently
cd scripts
python3 -m docx_to_json.converter  # Regenerate JSON only
python3 -m json_to_db.builder      # Regenerate database only
python3 -m db_to_md.renderer       # Regenerate Markdown only

python3 scripts/verify_db.py       # Verify DB vs JSON consistency (optional)
```

After updating source files, simply re-run `pipeline.py` — no manual intervention needed.
