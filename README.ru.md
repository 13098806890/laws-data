# 🏛️ База данных законов и нормативных актов Китая

[中文](README.md) · [English](README.en.md)

> Структурированный открытый набор данных действующих законов и нормативных актов КНР — исходные документы, структурированный JSON, база данных SQLite и полные тексты Markdown для поиска, исследований и разработки приложений.

---

## 📊 Обзор данных

| Категория | Кол-во | Диапазон law_id |
|-----------|-------:|-----------------|
| 🔴 Конституция (宪法) | 1 | `1000001–1099999` |
| 🟠 Законы (法律) | 442 | `1100001–1999999` |
| 🟡 Поправки (修正案) | 12 | `2000001–2099999` |
| 🟡 Решения (决定) | 4 | `2100001–2199999` |
| 🟢 Правовые толкования (法律解释) | 25 | `3000001–3499999` |
| 🟢 Судебные толкования (司法解释) | 682 | `3500001–4999999` |
| 🔵 Административные регламенты (行政法规) | 727 | `5000001–6499999` |
| 🔵 Надзорные регламенты (监察法规) | 3 | `6500001–6999999` |
| ⚪ Местные нормативные акты (резерв) | — | `7000001–7999999` |
| ⚪ Местные правила (резерв) | — | `8000001–8999999` |
| **Итого** | **1896** | |

**Охватываемые правовые отрасли:** Конституционное право · Гражданское и коммерческое право · Гражданский кодекс · Административное право · Экономическое право · Социальное право · Уголовное право · Процессуальное право

## 📦 Источник данных

Все исходные документы загружены с **[Национальной базы данных законов и нормативных актов](https://flk.npc.gov.cn/)** (国家法律法规数据库) — официальной платформы правового поиска Всекитайского собрания народных представителей. Файлы скачиваются в формате docx / doc и преобразуются в структурированные данные с помощью pipeline этого проекта. Платформа поддерживается Комиссией по законодательству Постоянного комитета ВСНП и является авторитетным каналом публикации всех категорий действующего китайского законодательства: Конституции, законов, административных регламентов и судебных толкований.

---

## 📁 Структура каталогов

```
laws_data/
├── 📂 sources/                    # Исходные файлы (docx/doc + xlsx индекс)
├── 📂 json/                       # Структурированный JSON (по категориям, результат pipeline)
├── 📂 markdown/                   # Полные тексты Markdown (по правовым отраслям, из БД)
├── 📂 references/
│   └── article_references.json   # Межстатейные ссылки
├── 📂 scripts/
│   ├── config.py                  # Конфигурация путей
│   ├── utils.py                   # Общие утилиты
│   ├── generate_law_index.py      # Присвоение стабильных law_id
│   ├── extract_references.py      # Извлечение ссылок
│   ├── pipeline.py                # Полный pipeline (с флагами пропуска этапов)
│   ├── verify_db.py               # Проверка согласованности БД и JSON
│   ├── docx_to_json/              # Этап 1: docx → JSON
│   ├── json_to_db/                # Этап 2: JSON → SQLite
│   └── db_to_md/                  # Этап 3: DB → Markdown
├── 📄 law_index.json              # Глобальный индекс law_id (1896 записей)
└── 🗄️  law_content.db             # База данных SQLite (~100MB)
```

---

## 🗄️ Структура базы данных

Запустите `python3 scripts/pipeline.py` для генерации `law_content.db`.

### 🟠 `laws` — По одной строке на закон

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Равен `law_id`, согласован с JSON-файлами |
| `title` | TEXT | Полное название |
| `filename` | TEXT UNIQUE | Формат: `{название}_{YYYYMMDD}` |
| `category` | TEXT | Категория (法律 / 行政法规 / 司法解释 …) |
| `legal_domain` | TEXT | Правовая отрасль (民法商法 / 刑法 / 行政法 …) |
| `pub_date` | TEXT | Дата опубликования `YYYY-MM-DD` |
| `effective_date` | TEXT | Дата вступления в силу `YYYY-MM-DD` |
| `promulgation_info` | TEXT | Полный текст уведомления об опубликовании |
| `issuing_org` | TEXT | Издающий орган (Верховный суд / Госсовет …) |
| `doc_number` | TEXT | Номер документа (напр. 法释〔2000〕29号) |
| `total_articles` | INTEGER | Общее число статей |
| `full_text` | TEXT | Полный текст закона (нормализованные пробелы) |
| `version_date` | TEXT | То же, что `pub_date`, для разграничения версий |
| `is_current` | INTEGER | **1 = действующая версия, 0 = историческая** (берётся с наибольшим pub_date) |

---

### 🔵 `nodes` — Единое хранилище для разделов / глав / параграфов / статей

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `law_id` | INTEGER FK | Ссылка на `laws.id` |
| `parent_id` | INTEGER FK | Родительский узел (NULL для разделов верхнего уровня) |
| `type` | TEXT | `part` / `chapter` / `section` / `article` |
| `title` | TEXT | Заголовок; для статей совпадает с `article_number` |
| `article_number` | TEXT | Номер статьи, напр. `第一条` (NULL для структурных узлов) |
| `content` | TEXT | Текст для отображения (заголовок для структурных, тело для статей) |
| `order_index` | INTEGER | Позиция внутри родительского узла |
| `global_order` | INTEGER | Глобальный порядок обхода в глубину — `ORDER BY global_order` даёт порядок чтения |
| `part_num` | INTEGER | Номер раздела (NULL при отсутствии разделов) |
| `chapter_num` | INTEGER | Номер главы |
| `section_num` | INTEGER | Номер параграфа (NULL при отсутствии) |
| `article_num` | INTEGER | Номер статьи (第十二条 → `12`) |

> **Точный поиск:** `WHERE law_id=1100001 AND chapter_num=3 AND article_num=15`

---

### 🟢 `nodes_fts` — Полнотекстовый поиск (виртуальная таблица)

| Поле | Описание |
|------|----------|
| `content` | Текст статьи (зеркало `nodes.content`) |
| `article_number` | Номер статьи |

- Движок: FTS5, `tokenize='trigram'`
- Поддерживает поиск любых китайских подстрок (минимум 3 символа)
- `rowid` соответствует `nodes.id`

---

### 🔴 `article_references` — Межстатейные ссылки (заготовка, пока не заполнена)

| Поле | Тип | Описание |
|------|-----|----------|
| `from_id` | INTEGER FK | Ссылающийся узел (`nodes.id`) |
| `to_id` | INTEGER FK | Цитируемый узел (`nodes.id`) |

> Данные о ссылках хранятся в `references/article_references.json` (см. ниже).

---

## 📎 law_index.json — Глобальный индекс law_id

По одной записи на закон; ID постоянны (новые законы добавляются в конец, существующие ID не меняются):

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

## 📋 Формат JSON

Каждый файл соответствует одному закону. Имя файла: `{название}_{YYYYMMDD}.json`.

**Без структуры разделов (большинство законов):**

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

**Со структурой разделов (Гражданский кодекс, УК, ГПК и др. — 8 законов):**

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

## 🔗 article_references.json — Граф ссылок

Охватывает только законы с `is_current=1`. **2 784 ссылки** (817 межзаконных, 1 967 самоссылок), разрешено 94,7%.

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

## ⚡ Типичные запросы

```sql
-- Полное содержание закона в порядке чтения
SELECT * FROM nodes WHERE law_id = 1100001 ORDER BY global_order;

-- Точная адресация: ГК, раздел 3, глава 5, статья 12
SELECT * FROM nodes
WHERE law_id = 1100313 AND part_num = 3 AND chapter_num = 5 AND article_num = 12;

-- Полнотекстовый поиск (любая китайская фраза, мин. 3 символа)
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- Только действующие версии
SELECT * FROM laws WHERE legal_domain = '民法商法' AND is_current = 1;

-- Все судебные толкования Верховного суда
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;

-- Все версии закона
SELECT title, pub_date, is_current FROM laws
WHERE title = '中华人民共和国公司法' ORDER BY pub_date;
```

---

## 🚀 Повторная генерация

```bash
pip install python-docx xlrd

# Полный pipeline
python3 scripts/pipeline.py

# Пропуск этапов (например, если JSON уже создан)
python3 scripts/pipeline.py --skip-docx
python3 scripts/pipeline.py --skip-docx --skip-index
python3 scripts/pipeline.py --skip-docx --skip-md

# Только обновить ссылки
python3 scripts/pipeline.py --only-refs

# Каждый этап отдельно
cd scripts
python3 -m docx_to_json.converter   # docx → JSON
python3 generate_law_index.py        # присвоить/обновить law_id
python3 -m json_to_db.builder        # JSON → DB
python3 -m db_to_md.renderer         # DB → Markdown
python3 extract_references.py        # извлечь ссылки

python3 verify_db.py                 # проверить согласованность (опционально)
```

После обновления исходных файлов достаточно повторно запустить `pipeline.py` — ручное вмешательство не требуется.
