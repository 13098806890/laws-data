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

Все исходные документы загружены с **[Национальной базы данных законов и нормативных актов](https://flk.npc.gov.cn/)** (国家法律法规数据库) — официальной платформы правового поиска Всекитайского собрания народных представителей. Файлы скачиваются в формате docx / doc и преобразуются в структурированные данные с помощью pipeline этого проекта. Платформа поддерживается Комиссией по законодательству Постоянного комитета ВСНП и является авторитетным каналом публикации всех категорий действующего китайского законодательства.

---

## 📁 Структура каталогов

```
laws_data/
├── 📂 sources/                    # Исходные файлы (docx/doc + xlsx индекс)
├── 📂 json/                       # Структурированный JSON (по категориям, результат pipeline)
│   ├── 法律/
│   ├── 司法解释/
│   ├── 行政法规/
│   ├── 宪法/
│   └── 监察法规/
├── 📂 民法典/                     # Markdown полные тексты (по отраслям, только is_current=1)
│   └── 司法解释/                  # 9 судебных толкований ГК
├── 📂 民法商法/
│   └── 司法解释/
├── 📂 刑法/
│   ├── 司法解释/
│   └── 法律解释/
├── 📂 行政法/
├── 📂 经济法/
├── 📂 社会法/
├── 📂 宪法相关法/
├── 📂 诉讼与非诉讼程序法/
│   └── 司法解释/
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

### 🟠 `laws` — По одной строке на закон

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Равен `law_id`, согласован с JSON-файлами |
| `title` | TEXT | Полное название |
| `filename` | TEXT UNIQUE | Формат: `{название}_{YYYYMMDD}` |
| `category` | TEXT | Категория (法律 / 行政法规 / 司法解释 …) |
| `legal_domain` | TEXT | Правовая отрасль |
| `pub_date` | TEXT | Дата опубликования `YYYY-MM-DD` |
| `effective_date` | TEXT | Дата вступления в силу `YYYY-MM-DD` |
| `promulgation_info` | TEXT | Полный текст уведомления об опубликовании |
| `issuing_org` | TEXT | Издающий орган |
| `doc_number` | TEXT | Номер документа |
| `total_articles` | INTEGER | Общее число статей |
| `full_text` | TEXT | Полный текст закона |
| `version_date` | TEXT | То же, что `pub_date`, для разграничения версий |
| `is_current` | INTEGER | **1 = действующая версия, 0 = историческая** |

---

### 🔵 `nodes` — Единое хранилище для разделов / глав / параграфов / статей

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Автоинкремент |
| `law_id` | INTEGER FK | Ссылка на `laws.id` |
| `parent_id` | INTEGER FK | Родительский узел |
| `type` | TEXT | `part` / `chapter` / `section` / `article` |
| `title` | TEXT | Заголовок |
| `article_number` | TEXT | Номер статьи, напр. `第一条` |
| `content` | TEXT | Текст для отображения |
| `order_index` | INTEGER | Позиция внутри родительского узла |
| `global_order` | INTEGER | Глобальный порядок обхода в глубину |
| `part_num` | INTEGER | Номер раздела |
| `chapter_num` | INTEGER | Номер главы |
| `section_num` | INTEGER | Номер параграфа |
| `article_num` | INTEGER | Номер статьи (第十二条 → `12`) |

---

### 🟢 `nodes_fts` — Полнотекстовый поиск (виртуальная таблица)

- Движок: FTS5, `tokenize='trigram'`
- Поддерживает поиск любых китайских подстрок (минимум 3 символа)
- `rowid` соответствует `nodes.id`

---

### 🔴 `article_references` — Межстатейные ссылки

| Поле | Тип | Описание |
|------|-----|----------|
| `from_node_id` | INTEGER FK | Ссылающийся узел |
| `from_law_id` | INTEGER FK | Ссылающийся закон |
| `from_article_num` | INTEGER | Номер ссылающейся статьи |
| `from_chapter_num` | INTEGER | Номер главы |
| `from_section_num` | INTEGER | Номер параграфа |
| `from_part_num` | INTEGER | Номер раздела |
| `to_node_id` | INTEGER FK | Цитируемый узел |
| `to_law_id` | INTEGER FK | Цитируемый закон |
| `to_article_num` | INTEGER | Номер цитируемой статьи |
| `to_chapter_num` | INTEGER | Номер главы |
| `to_section_num` | INTEGER | Номер параграфа |
| `to_part_num` | INTEGER | Номер раздела |
| `ref_type` | TEXT | `cross_law` / `self_ref` |
| `resolved` | INTEGER | 1 = разрешено, 0 = не разрешено |
| `raw_text` | TEXT | Исходный текст ссылки |

---

## 📎 law_index.json — Глобальный индекс law_id

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

## 🔗 article_references.json — Граф ссылок

Охватывает только законы с `is_current=1`. **4 994 ссылки** (2 986 межзаконных, 2 008 самоссылок), разрешено 98,0%.

---

## 📝 Гиперссылки и маркеры цитирования в Markdown

В каждом Markdown-файле:

- **Якоря статей**: каждая статья имеет якорь `<a id="art-N">`, адресуемый через `filename.md#art-N`
- **Исходящие ссылки**: упоминания других законов в тексте статей автоматически преобразуются в кликабельные межфайловые ссылки
- **Входящие маркеры**: статьи, на которые ссылаются другие законы, получают надстрочные цифры `[1]` `[2]` … в конце; при наведении отображается `被《название》第N条引用`; клик переходит к статье-источнику

Отображаются только законы с `is_current=1`.

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

# Пропуск этапов
python3 scripts/pipeline.py --skip-docx
python3 scripts/pipeline.py --skip-docx --skip-index
python3 scripts/pipeline.py --skip-docx --skip-md

# Только обновить ссылки
python3 scripts/pipeline.py --only-refs

# Каждый этап отдельно
cd scripts
python3 -m docx_to_json.converter
python3 generate_law_index.py
python3 -m json_to_db.builder
python3 -m db_to_md.renderer
python3 extract_references.py

python3 verify_db.py
```

После обновления исходных файлов достаточно повторно запустить `pipeline.py` — ручное вмешательство не требуется.
