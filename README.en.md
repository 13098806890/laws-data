# 🏛️ Chinese Laws & Regulations Database

[中文](README.md) · [Русский](README.ru.md) · [LICENSE](LICENSE)

> A structured open dataset of current Chinese laws and regulations — raw documents, structured JSON, SQLite database, and Markdown full text, for search, research, and application development.

**License**: [MIT](LICENSE). Legal texts are sourced from official public channels (not subject to copyright); the structured data and translations are likewise open under MIT — free for commercial use, redistribution, and modification.

**Getting started**: download the prebuilt database or build it yourself — see [Quick Start](#-quick-start) below.

---

## 📊 Data Overview

| Category | Count |
|----------|-----:|
| Constitution (宪法) | 1 |
| Laws (法律) | 448 |
| Amendments (修正案) | 12 |
| Legal Interpretations (法律解释) | 25 |
| Judicial Interpretations (司法解释) | 1,157 |
| Administrative Regulations (行政法规) | 727 |
| Supervisory Regulations (监察法规) | 3 |
| Decisions (有关法律问题和重大问题的决定, partial) | 4 |
| **Total** | **2,377** |

Of these, **1,735** are current (`is_current=1`). **78,788** article nodes (87,810 nodes including chapters and other structural levels), **5,319** article references (2,559 cross-law + 2,760 self-ref), 98.4% resolved.

### 🌐 English Translation

| Metric | Progress |
|------|-----:|
| Articles translated (current laws) | **60,744/60,745 (99.99%)** |
| Law titles translated | 2,097 |
| Chinese full-text search | `nodes_fts` (trigram, ≥3 chars) + `nodes_fts_bigram` (unicode61, 1–2 chars) |
| Laws covered | 2,377 (incl. gazette sources) |

Translation runs through a two-phase pipeline (`translate_to_en.py`): batch title translation first, then article-by-article translation with glossary and law-name context. Terminology consistency is enforced via 39 specialist experts' `nameEn`, 6 expert-group `nameEn`, and 101 `RequiredInfo.fieldEn` entries.

### 📖 Supreme People's Court Gazette

Full data from the SPC Gazette (gongbao.court.gov.cn) is additionally included:

| Type | Count |
|------|-----:|
| Guiding Cases (指导案例) | 986 |
| Judicial Documents (司法文件) | 860 |
| Selected Judgments (裁判文书) | 443 |
| Gazette Judicial Interpretations | 839 (merged into main `laws`/`nodes` tables) |

All gazette documents have citation links to main-DB articles (3,529 links).

This dataset powers the [ChineseLawsSearch](https://github.com/doxie/LawsSearch) iOS app.

---

## 📦 Data Source

**Main library**: all original documents come from the **[National Laws and Regulations Database](https://flk.npc.gov.cn/)** (国家法律法规数据库), the official platform of the NPC Standing Committee's Legislative Affairs Commission, downloaded as docx/doc and processed by this pipeline.

A few files whose original docx is missing or malformed are replaced with web-scraped text from the SPC website — see `sources/_web_sources/README.md`.

**SPC Gazette**: scraped from [gongbao.court.gov.cn](https://gongbao.court.gov.cn) via `scripts/fetch_gongbao.py`, stored under `最高人民法院公报/` (JSON format).

---

## 📁 Directory Structure

```
laws_data/
├── 📂 sources/                    # Source files (docx/doc + xlsx index)
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   ├── 监察法规/
│   └── _web_sources/              # Web-scraped replacement files + HTML cache
├── 📂 json/                       # Structured JSON (by category, pipeline output)
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── 📂 json_en/                    # English translations (mirrors json/)
├── 📂 json_en_gongbao/            # Gazette document English translations (al/cpwsxd/sfwj)
├── 📂 宪法与国家机构/             # Markdown full text (by subject_area menu, is_current=1)
├── 📂 民事与商事/
├── 📂 刑事/
├── 📂 行政与公法/
├── 📂 经济、税务与金融/
├── 📂 劳动与社会保障/
├── 📂 诉讼与司法程序/
├── 📂 其他/
├── 📂 references/
│   ├── article_references.json    # Article cross-references (pipeline output)
│   ├── law_title_en_map.json      # Law title English map
│   └── heading_en_map.json        # Structural heading English map
├── 📂 最高人民法院公报/            # Full gazette data (fetch_gongbao.py output, JSON)
│   ├── 指导案例/                  # 986 (al)
│   ├── 司法文件/                  # 860 (sfwj)
│   ├── 裁判文书/                  # 443 (cpwsxd)
│   └── 司法解释/                  # 839 (merged into main laws/nodes)
├── 📂 knowledge/                  # Knowledge-graph JSON (taxonomy/hierarchy/relations/versions)
├── 📂 docs/                       # Documentation (archive/ history, translation/ reports, guides/)
├── 📂 scripts/
│   ├── config.py                  # Path configuration (BASE_DIR, DB_PATH etc.; LAWS_REPO_PATH env override)
│   ├── utils.py                   # Shared utilities (title_from_stem, pub_date_from_stem)
│   ├── law_id_registry.py         # Single authoritative law_id registry
│   ├── pipeline.py                # Main pipeline entry (7 stages, incl. gazette import, EN import, validation)
│   ├── download_db.py             # Download prebuilt DB from GitHub Releases
│   ├── fetch_gongbao.py           # SPC Gazette scraper (5 targets)
│   ├── build_gongbao_db.py        # Gazette data → law_content.db (stage 7)
│   ├── classify_gongbao_domain.py # legal_domain tagging for gazette judicial interpretations
│   ├── import_en.py               # json_en → nodes.content_en / laws.title_en
│   ├── translate_to_en.py         # English translation script (batched by tier)
│   ├── generate_law_index.py      # Stable law_id assignment
│   ├── extract_references.py      # Article citation extraction
│   ├── fetch_web_sources.py       # Web scraping → .txt replacement files
│   ├── verify_db.py               # DB ↔ JSON consistency check (incl. EN coverage)
│   ├── build_aliases.py           # Build term_aliases (LLM + FTS validation)
│   ├── build_enhancements.py      # Build RAG enhancement tables
│   ├── test_rag.py                # Basic RAG pipeline
│   ├── legal_chain_agent.py       # Article-chain reasoning agent
│   ├── legal_expert_agent.py      # Multi-layer expert system entry
│   ├── agents/                    # Expert system modules
│   ├── docx_to_json/              # Stage 1: docx/txt → JSON
│   │   ├── converter.py           # Main entry, paragraph parsing, structure recognition
│   │   ├── structure.py           # Hierarchy assembly, global_order assignment
│   │   ├── domain.py              # legal_domain mapping (scoring), xlsx index reading
│   │   ├── effective_date.py      # Effective-date extraction
│   │   └── subject_area.py        # Administrative-regulation subtopic classification
│   ├── json_to_db/                # Stage 3: JSON → SQLite
│   │   ├── builder.py             # Table creation, law/node/FTS writing
│   │   └── export_menu.py         # Export law_menu.json navigation index
│   └── db_to_md/                  # Stage 6: DB → Markdown
│       └── renderer.py            # Menu-grouped full Markdown rendering
├── 📄 law_index.json              # Stable law_id index (survives rebuilds)
├── 📄 law_menu.json               # Sidebar navigation index (by subject_area)
├── 🗄️  law_content.db             # Main database (~460MB, not committed; download or build)
├── 🗄️  law_enhancements.db        # RAG enhancement database (~128KB)
├── 📄 LICENSE                     # MIT
├── 📄 CONTRIBUTING.md             # Contribution guide
└── 📄 CLAUDE.md                   # Maintenance notes
```

---

## 🔄 Main Pipeline

**Entry point**: `python3 scripts/pipeline.py`

The pipeline runs seven stages sequentially and rebuilds everything from scratch (no incremental mode), ~5–10 min per run.

### Stage 1: `docx_to_json` — source files → structured JSON

**Input**: `.docx` / `.doc` / `.txt` files under `sources/` (`.txt` takes precedence over same-name `.docx`, used to replace defective originals)

**Output**: `.json` files under `json/`, one per law

**Steps**:

1. **xlsx index preload** (`domain.py`): each source directory has `法律法规文件目录_*.xlsx` with 4 columns (title | pub date | effective date | category). Preloaded into a `{title}_{YYYYMMDD}` → `{effective_date, category}` index, authoritative over body-extracted results.
2. **Paragraph extraction** (`converter.py`): reads docx paragraphs / txt lines; recognizes issuing authority (12-org whitelist exact match) and document number (regex `org-abbrev〔year〕num`).
3. **Effective-date extraction** (`effective_date.py`): from promulgation paragraphs; xlsx value overrides.
4. **Structure recognition** (converter main loop): `第X编` → part; `第X章` or Chinese-numeral headings (`一、管辖`, common in judicial interpretations) → chapter; `第X节` → section; `第X条` → article (supports splitting merged multi-article paragraphs); short files without structure → single article whose content is full_text.
5. **Hierarchy assembly** (`structure.py`): nested dict per part/chapter/section/article, `global_order` assigned depth-first so `ORDER BY global_order` restores reading order.
6. **Metadata**: `title` from filename (never from docx body), `category` from xlsx, `legal_domain` (prefer `LAWS_REPO_PATH` directory match, then manual supplements, then keyword rules).

**Special handling**:
- Civil Code has 7 parts; the "General Provisions" part heading is hardcoded (missing in source file)
- Articles directly under a part use a `_DIRECT_` placeholder chapter, no extra nodes created
- 九民纪要-style files (`1.【标题】正文`) are pre-converted by `fetch_web_sources.py` into `第N条　【标题】正文`

---

### Stage 2: `generate_law_index` — stable law_id assignment

**Input**: all `.json` files under `json/`

**Output**: `scripts/law_index.json` (persistent index, IDs stable across rebuilds)

Each law is keyed by `{title}_{pub_date}`; first sighting gets a permanent ID (auto-increment from 1000001). Rebuilds keep existing IDs, new laws append new ones. This keeps `article_references` and other cross-library references valid across rebuilds.

---

### Stage 3: `json_to_db` — JSON → SQLite

**Input**: `json/`, `law_index.json`

**Output**: `law_content.db` (fully rebuilt, old file dropped)

**Steps**:

1. **Table creation** (`builder.py`): `laws`, `nodes`, `nodes_fts` (trigram FTS5), `nodes_fts_bigram` (unicode61 FTS5), `article_references` + indexes. Both FTS tables are **external content tables** (`content="nodes"`) — no text duplication, saves ~175MB.
2. **laws rows**: metadata from JSON, stable ID from `law_index.json`, aliases from `law_aliases.py`.
3. **nodes rows** (recursive): part → chapter → section → article with `parent_id`, `global_order`, `part_num`, `chapter_num`, `section_num`, `article_num`; every article inserted into both FTS tables.
4. **FTS optimize** after all inserts.
5. **Gazette interpretation tagging** (`classify_gongbao_domain.py`): assign legal_domain to `source='gongbao'` interpretations.
6. **Menu export**: `law_menu.json` (grouped by subject_area, with title_en) for the iOS sidebar.

---

### Stage 4: `extract_references` — article citation extraction

**Input**: `law_content.db` (nodes)

**Output**: `references/article_references.json`, plus the `article_references` table in `law_content.db`

Three citation patterns are recognized over all `is_current=1` articles:

1. **Quoted cross-law**: `《法律名》第X条`, resolved via `art_index`; both short titles (sans "中华人民共和国" prefix) and full names match.
2. **Unquoted short title**: `刑法第X条` etc., via dynamically built short-title regexes, matched longest-first to avoid ambiguity.
3. **Self-reference**: `本法/本条例/本规定第X条`; criminal-law-amendment "本法第X条" is redirected to the Criminal Code and marked `cross_law`.

**Current stats**: 5,319 citations (2,559 cross-law, 2,760 self-ref), 98.4% resolved.

---

### Stage 5: English import (`import_en.py`)

**Input**: `json_en/` (article translations), `references/heading_en_map.json` (heading translations)

**Output**: `nodes.content_en`, `laws.title_en`

- Articles matched by `article_number`, idempotent (`WHERE content_en IS NULL` never overwrites)
- Structural headings written from `heading_en_map.json` (stable key `law_id:type:order_index`)

---

### Stage 6: `db_to_md` — DB → Markdown

**Input**: `law_content.db` (`is_current=1` laws)

**Output**: `.md` files grouped by subject_area menu (宪法与国家机构/ 民事与商事/ 刑事/ 行政与公法/ 经济、税务与金融/ 劳动与社会保障/ 诉讼与司法程序/ 其他)

Every article gets an `<a id="art-N">` anchor; outgoing citations in the body become cross-file Markdown links.

---

### Stage 7: Gazette import (`build_gongbao_db`)

**Prerequisite**: JSON files under `最高人民法院公报/` (scraped by `fetch_gongbao.py`)

**Output**: two new tables in `law_content.db`; gazette judicial interpretations merged into main `laws`/`nodes`:

| Table | Description |
|----|------|
| `gongbao_docs` | Judgments + guiding cases + judicial documents, 2,289 total; `source` distinguishes `al`/`cpwsxd`/`sfwj` |
| `gongbao_case_law_links` | Gazette-doc → main-law-article links, 3,529 total, 99.8% resolved |
| `gongbao_docs_fts` | FTS5 trigram full-text index (external content table) |

Gazette judicial interpretations (839, IDs 3500010–3501473) are not kept in a separate table — they are written as `source='gongbao'` into the main `laws`/`nodes`. law_id assignment strictly follows `scripts/law_id_registry.py` (blocklist → json_en embedded → law_index, three-level), no fuzzy mapping.

**Standalone run**:

```bash
python3 scripts/build_gongbao_db.py          # create tables + import (skip if exists)
python3 scripts/build_gongbao_db.py --drop   # drop old tables first, then rebuild
```

**Gazette scraping**:

```bash
# All targets (first run ~2–3 hours)
python3 scripts/fetch_gongbao.py --target al      # guiding cases
python3 scripts/fetch_gongbao.py --target sfwj    # judicial documents
python3 scripts/fetch_gongbao.py --target cpwsxd  # judgments
python3 scripts/fetch_gongbao.py --target sfjs    # gazette judicial interpretations
python3 scripts/fetch_gongbao.py --target flxd    # laws/regulations (reference)

# Incremental (skip already-fetched files)
python3 scripts/fetch_gongbao.py --target al --skip-existing
```

---

### Run flags

```bash
python3 scripts/pipeline.py                          # full seven-stage run
python3 scripts/pipeline.py --docx                   # force re-run docx → JSON (auto-detected otherwise)
python3 scripts/pipeline.py --skip-index             # skip law_index generation
python3 scripts/pipeline.py --skip-db                # skip JSON → DB
python3 scripts/pipeline.py --skip-md                # skip DB → Markdown
python3 scripts/pipeline.py --skip-gongbao           # skip gazette import
python3 scripts/pipeline.py --skip-en                # skip English import
python3 scripts/pipeline.py --only-refs              # only re-run citation extraction
python3 scripts/pipeline.py --validate               # additionally validate content_en vs json_en

# Individual stages
cd scripts
python3 -m docx_to_json.converter     # stage 1
python3 generate_law_index.py          # stage 2
python3 -m json_to_db.builder          # stage 3
python3 extract_references.py          # stage 4 (JSON only)
python3 import_en.py                   # stage 5 (English import)
python3 -m db_to_md.renderer           # stage 6
python3 build_gongbao_db.py --drop     # stage 7 (standalone rebuild)
python3 fetch_web_sources.py           # web replacement files (standalone)
python3 verify_db.py                   # verify DB ↔ JSON consistency (optional)
```

---

## 🗄️ Database Schema

Two SQLite databases:

- **`law_content.db`** (~460MB) — main database, fully generated by `pipeline.py`, includes gazette data. **Not committed to git**; download from [GitHub Releases](https://github.com/doxie/laws-data/releases) or build locally.
- **`law_enhancements.db`** (~128KB) — RAG enhancement database, maintained independently by `build_enhancements.py`.

### `law_content.db` tables

#### 🟠 `laws` — one row per law

| Field | Type | Description |
|------|------|------|
| `id` | INTEGER PK | Stable primary key from `generate_law_index.py`, survives rebuilds |
| `title` | TEXT | Full title from filename (not from docx body) |
| `title_en` | TEXT | English title, imported from json_en |
| `filename` | TEXT UNIQUE | Format: `{title}_{YYYYMMDD}`, no extension |
| `category` | TEXT | `法律` / `行政法规` / `司法解释` / `修正案` / `法律解释` / `宪法` / `监察法规` / `有关法律问题和重大问题的决定（部分）` |
| `legal_domain` | TEXT | `民法典` / `民法商法` / `刑法` / `行政法` / `经济法` / `社会法` / `宪法相关法` / `诉讼与非诉讼程序法` |
| `subject_area` | TEXT | Menu subtopic (all laws since v2.0.0, written back by export_menu.py) |
| `pub_date` | TEXT | Promulgation date `YYYY-MM-DD` |
| `effective_date` | TEXT | Effective date; xlsx is authoritative |
| `promulgation_info` | TEXT | Full promulgation notice |
| `issuing_org` | TEXT | Issuing authority (12-org whitelist) |
| `doc_number` | TEXT | Document number (法释〔2000〕29号 etc.) |
| `total_articles` | INTEGER | Article count |
| `full_text` | TEXT | Complete law text |
| `version_date` | TEXT | Same as `pub_date`; multi-version disambiguation |
| `is_current` | INTEGER | **1 = current**; 0 = historical or explicitly repealed (`repealed_by` non-empty) |
| `aliases` | TEXT | Comma-separated aliases (民法典,民法), for search expansion |
| `source` | TEXT | `flk` (main library) / `gongbao` (SPC Gazette) |

```sql
-- Search by alias
SELECT * FROM laws WHERE is_current=1 AND (title LIKE '%民法%' OR aliases LIKE '%民法%');

-- Supreme Court judicial interpretations
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
```

#### 🔵 `nodes` — parts / chapters / sections / articles in one table

| Field | Type | Description |
|------|------|------|
| `id` | INTEGER PK | Auto-increment |
| `law_id` | INTEGER FK | References `laws.id` |
| `parent_id` | INTEGER FK | Parent id; NULL for parts |
| `type` | TEXT | `part` / `chapter` / `section` / `article` |
| `title` | TEXT | Heading text for structural nodes; same as `article_number` for articles |
| `article_number` | TEXT | e.g. `第一条`; NULL for structural nodes |
| `content` | TEXT | Heading text for structural nodes, article body otherwise |
| `content_en` | TEXT | English translation (articles + headings), imported by import_en.py |
| `order_index` | INTEGER | Position within parent |
| `global_order` | INTEGER | Depth-first global sequence — `ORDER BY global_order` restores reading order |
| `part_num` | INTEGER | Part number (NULL if no part structure) |
| `chapter_num` | INTEGER | Chapter number |
| `section_num` | INTEGER | Section number (NULL if no section structure) |
| `article_num` | INTEGER | Integer article number (第十二条 → 12), enables range queries |

Notes:
- `part` structure exists in 9 laws (Civil Code, Criminal Law ×2, Criminal Procedure Law ×2, Civil Procedure Law ×3, Eco-Environment Code)
- Some judicial interpretations use Chinese-numeral headings (`一、管辖`) instead of chapters; still mapped to `chapter`
- Short documents without structure (legal interpretations, replies) are written as a single `article` (content = full_text)

```sql
-- Law full text in reading order
SELECT type, title, content FROM nodes WHERE law_id = ? ORDER BY global_order;

-- Articles 10–20
SELECT article_number, content FROM nodes
WHERE law_id = ? AND type = 'article' AND article_num BETWEEN 10 AND 20;
```

#### 🟢 `nodes_fts` — full-text search (≥3 chars)

FTS5 **external content table** (`content="nodes"`) — no text duplication, saves ~175MB. Tokenizer: `trigram`, arbitrary Chinese substring match, minimum 3 characters.

```sql
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article' AND l.is_current = 1;
```

#### 🔵 `nodes_fts_bigram` — short-word search (1–2 chars)

FTS5 external content table, `unicode61` tokenizer, for 1–2 character queries (`婚`, `婚姻`). For ≥3 chars prefer `nodes_fts` (trigram is more precise).

#### 🔴 `article_references` — citation relationships

| Field | Type | Description |
|------|------|------|
| `from_node_id` | INTEGER FK | Citing node |
| `from_law_id` | INTEGER FK | Citing law |
| `from_article_num` | INTEGER | Citing article number |
| `to_node_id` | INTEGER FK | Cited node (when resolved) |
| `to_law_id` | INTEGER FK | Cited law |
| `to_article_num` | INTEGER | Cited article number |
| `ref_type` | TEXT | `cross_law` / `self_ref` |
| `resolved` | INTEGER | 1 = resolved to a specific node |
| `raw_text` | TEXT | Original citation string, e.g. `《中华人民共和国民法典》第一千二百零八条` |

Covers all `is_current=1` articles; extracted by `extract_references.py`, updated automatically with the pipeline.

---

### `law_content.db` gazette extension tables

Written by `build_gongbao_db.py` (pipeline stage 7).

#### `gongbao_docs` — judgments / guiding cases / judicial documents (2,289)

| Field | Description |
|------|------|
| `source` | `al` / `cpwsxd` / `sfwj` |
| `case_number` | Guiding-case number, e.g. `指导性案例212号` (al only) |
| `title` | Case/document title |
| `issue` | Gazette issue, e.g. `2024年01期` |
| `year` / `issue_num` | Year / issue (integers, sortable) |
| `pub_date` | Publish date |
| `url` | Original link (gongbao.court.gov.cn) |
| `ruling_gist` | Key ruling / summary (≤500 chars, extracted from body) |
| `keywords` | Keywords (comma-separated) |
| `full_text` | Full text |

#### `gongbao_case_law_links` — gazette docs → main law articles (3,529)

`《Law name》第N条` citations extracted from `gongbao_docs` bodies, linked to `laws.id` and `nodes.id`, 99.8% resolved.

#### `gongbao_docs_fts`

FTS5 external content table, `tokenize="trigram"`, indexes `title`, `ruling_gist`, `keywords`, `full_text`.

```sql
-- Guiding cases whose ruling gist contains "善意取得"
SELECT d.title, d.case_number, d.ruling_gist
FROM gongbao_docs_fts f
JOIN gongbao_docs d ON f.rowid = d.id
WHERE gongbao_docs_fts MATCH '善意取得' AND d.source = 'al'
ORDER BY d.year DESC;

-- Which gazette cases cite a given article
SELECT d.title, d.source, l.article_num
FROM gongbao_case_law_links l
JOIN gongbao_docs d ON l.doc_id = d.id
WHERE l.node_id = ?;
```

---

### `law_enhancements.db` tables

#### `term_aliases` — colloquial → legal terms (134)

LLM-generated candidates, written only after FTS validation confirms hits > 0.

| Field | Description |
|------|------|
| `colloquial` | Everyday language, e.g. `车祸`, `被炒鱿鱼` |
| `legal_term` | Term actually appearing in articles, e.g. `道路交通事故`, `解除劳动合同` |
| `fts_hits` | Hit count in articles |

#### `alias_patches` — manual precision patches (135)

Fills LLM gaps (`离婚`, `误工费`, `工伤` etc.), same schema as `term_aliases`.

#### `topic_law_hints` — topic keywords → recommended laws (115)

Maps question scenarios to the most relevant laws; RAG searches within them first.

#### `keyword_synonyms` — LLM keywords → precise FTS terms (312)

Maps words the LLM coins (`超速驾驶`) to terms with actual hits (`违法驾驶`).

```bash
python3 scripts/build_aliases.py        # rebuild term_aliases (needs Ollama, ~5 min)
python3 scripts/build_enhancements.py   # rebuild the other three tables (static, <1s)
```

---

## 📋 JSON Format

One file per law, filename `{title}_{YYYYMMDD}.json`.

**Without part structure (most laws):**

```json
{
  "law_id": 1100023,
  "title": "中华人民共和国合同法",
  "category": "法律",
  "legal_domain": "民法商法",
  "pub_date": "1999-03-15",
  "effective_date": "1999-10-01",
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
  ]
}
```

**With part structure (Civil Code, Criminal Law, procedure laws, Eco-Environment Code — 9 laws):**

```json
{
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

## 🤖 Legal Q&A Agents

Three escalating Q&A scripts, all supporting DeepSeek / Groq / Ollama providers.

### `test_rag.py` — basic RAG pipeline

Keyword retrieval + LLM filtering: domain routing → keyword extraction + alias expansion → FTS retrieval → relevance filtering → answer generation.

### `legal_chain_agent.py` — article-chain reasoning agent

Adds chapter navigation and citation-chain expansion: question split → domain routing → chapter navigation to fetch articles → FTS supplement → citation-chain expansion (auto-append cited articles) → filter/rank → conclusion.

```bash
python3 scripts/legal_chain_agent.py -q "网购假货怎么维权"
python3 scripts/legal_chain_agent.py -q "..." --provider deepseek
```

### `legal_expert_agent.py` — multi-layer expert system

Three-layer expert architecture (coordinator → 6 expert groups → 17 specialists), with information gathering (auto-extract known facts, batch questions when missing).

```bash
python3 scripts/legal_expert_agent.py -q "公司非法裁员我怎么办"
python3 scripts/legal_expert_agent.py -q "..." --no-interactive  # skip info gathering
```

**Dependencies**: `pip install requests` (online providers); local Ollama needs `ollama pull qwen2.5:3b`.

---

## 🚀 Quick Start

### Option 1: Download the prebuilt database (recommended)

```bash
git clone https://github.com/doxie/laws-data.git
cd laws-data

# Download law_content.db (GitHub Releases asset, ~460MB)
python3 scripts/download_db.py
```

The prebuilt database includes all law texts, English translations, FTS indexes, and gazette data — ready for the iOS app or direct querying.

### Option 2: Full build from source (~5–10 min)

```bash
pip install python-docx xlrd

# Full pipeline (auto-detects source changes, full rebuild)
python3 scripts/pipeline.py

# Force re-run docx → JSON (after source changes)
python3 scripts/pipeline.py --docx

# Verify database integrity (optional)
python3 scripts/verify_db.py
```

After updating source files, just re-run `pipeline.py` — the pipeline is stateless and rebuilds everything.

---

## ⚠️ Known Limitations

- FTS trigram minimum match is 3 chars; 1–2 char search uses `nodes_fts_bigram`
- Citations are extracted only from `is_current=1` articles
- 83 citations are unresolved because the target law is not in the dataset (e.g. 执业医师法)
- `json/` **must mirror `sources/`** (flat by category) — do not reorganize by `legal_domain`, or `builder.py`'s path scanning breaks
- `law_content.db` is not committed to git (~460MB); download from [GitHub Releases](https://github.com/doxie/laws-data/releases) or build locally

---

## 🤝 Contributing

Issues and PRs welcome — law-data corrections, English translations, and pipeline improvements all appreciated. See [CONTRIBUTING.md](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md).

## 📄 License

[MIT License](LICENSE). Legal texts are sourced from official public channels (National Laws and Regulations Database, SPC Gazette) and are not subject to copyright; the structured data and translations are likewise open under MIT.
