# 🏛️ База данных законов и нормативных актов Китая

[中文](README.md) · [English](README.en.md)

> Структурированный открытый набор данных действующих законов и нормативных актов КНР — исходные документы, структурированный JSON, база данных SQLite и полные тексты Markdown для поиска, исследований и разработки приложений.

---

## 📊 Обзор данных

| Категория | Кол-во |
|-----------|-------:|
| Конституция (宪法) | 1 |
| Законы (法律) | 310 |
| Поправки (修正案) | 12 |
| Решения (决定) | 2 |
| Правовые толкования (法律解释) | 25 |
| Судебные толкования (司法解释) | 566 |
| Административные регламенты (行政法规) | 607 |
| Надзорные регламенты (监察法规) | 2 |
| **Итого** | **1525** |

**Группы отображения:** Конституция и гос. институты · Гражданское и коммерческое · Уголовное · Административное и публичное право · Экономика, налоги и финансы · Труд и социальное обеспечение · Судопроизводство

## 📦 Источник данных

Все исходные документы загружены с **[Национальной базы данных законов и нормативных актов](https://flk.npc.gov.cn/)** (国家法律法规数据库) — официальной платформы правового поиска Всекитайского собрания народных представителей. Файлы скачиваются в формате docx / doc и преобразуются в структурированные данные с помощью pipeline этого проекта.

---

## 📁 Структура каталогов

```
laws_data/
├── 📂 sources/                    # Исходные файлы (docx/doc + xlsx индекс)
├── 📂 json/                       # Структурированный JSON (по категориям, результат pipeline)
├── 📂 宪法与国家机构/             # Markdown полные тексты (по группам отображения, только is_current=1)
├── 📂 民事与商事/                 # 10 подгрупп
├── 📂 刑事/                       # 6 подгрупп
├── 📂 行政与公法/                 # Законы + регламенты по 20 темам
├── 📂 经济、税务与金融/
├── 📂 劳动与社会保障/
├── 📂 诉讼与司法程序/
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
│   │   ├── builder.py
│   │   └── display_group.py       # Таблица маппинга групп отображения
│   └── db_to_md/                  # Этап 3: DB → Markdown
└── 🗄️  law_content.db             # База данных SQLite (~150MB)
```

---

## 🗄️ Структура базы данных

### 🟠 `laws` — По одной строке на закон

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Внутренний первичный ключ |
| `title` | TEXT | Полное название |
| `filename` | TEXT UNIQUE | Формат: `{название}_{YYYYMMDD}` |
| `category` | TEXT | Тип источника (法律 / 行政法规 / 司法解释 …) |
| `legal_domain` | TEXT | Академическая правовая отрасль |
| `subject_area` | TEXT | Тема административного регламента (пусто для остальных) |
| `pub_date` | TEXT | Дата опубликования `YYYY-MM-DD` |
| `effective_date` | TEXT | Дата вступления в силу `YYYY-MM-DD` |
| `promulgation_info` | TEXT | Полный текст уведомления об опубликовании |
| `issuing_org` | TEXT | Издающий орган |
| `doc_number` | TEXT | Номер документа |
| `total_articles` | INTEGER | Общее число статей |
| `full_text` | TEXT | Полный текст закона |
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

### 🟣 `display_group_map` — Маппинг групп отображения

| Поле | Тип | Описание |
|------|-----|----------|
| `law_id` | INTEGER PK FK | Ссылка на `laws.id` |
| `display_group` | TEXT | Группа верхнего уровня (7 значений) |
| `display_subgroup` | TEXT | Подгруппа второго уровня (третий уровень через `/`) |

Не зависит от `legal_domain` — обновляется повторным запуском `display_group.py`.

---

### 🔴 `article_references` — Межстатейные ссылки

| Поле | Тип | Описание |
|------|-----|----------|
| `from_node_id` | INTEGER FK | Ссылающийся узел |
| `from_law_id` | INTEGER FK | Ссылающийся закон |
| `from_article_num` | INTEGER | Номер ссылающейся статьи |
| `to_node_id` | INTEGER FK | Цитируемый узел |
| `to_law_id` | INTEGER FK | Цитируемый закон |
| `to_article_num` | INTEGER | Номер цитируемой статьи |
| `ref_type` | TEXT | `cross_law` / `self_ref` |
| `resolved` | INTEGER | 1 = разрешено до конкретной статьи |
| `raw_text` | TEXT | Исходный текст ссылки |

---

## 🔗 article_references.json — Граф ссылок

Охватывает только законы с `is_current=1`. **4 994 ссылки** (2 986 межзаконных, 2 008 самоссылок), разрешено 98,0%.

---

## 📝 Гиперссылки и маркеры цитирования в Markdown

В каждом Markdown-файле:

- **Якоря статей**: каждая статья имеет якорь `<a id="art-N">`, адресуемый через `filename.md#art-N`
- **Исходящие ссылки**: упоминания других законов автоматически преобразуются в кликабельные межфайловые ссылки
- **Входящие маркеры**: статьи, на которые ссылаются другие законы, получают надстрочные цифры `[1]` `[2]` …; при наведении отображается закон-источник; клик переходит к статье-источнику

---

## ⚡ Типичные запросы

```sql
-- Полное содержание закона в порядке чтения
SELECT * FROM nodes WHERE law_id = ? ORDER BY global_order;

-- Полнотекстовый поиск (любая китайская фраза, мин. 3 символа)
SELECT n.article_number, n.content, l.title
FROM nodes_fts f
JOIN nodes n ON f.rowid = n.id
JOIN laws l ON n.law_id = l.id
WHERE nodes_fts MATCH '合同解除' AND n.type = 'article';

-- Просмотр по группе отображения
SELECT l.title, l.category, dgm.display_subgroup
FROM laws l
JOIN display_group_map dgm ON l.id = dgm.law_id
WHERE dgm.display_group = '民事与商事' AND l.is_current = 1;

-- Все судебные толкования Верховного суда
SELECT title, doc_number, pub_date FROM laws
WHERE issuing_org = '最高人民法院' AND category = '司法解释'
ORDER BY pub_date DESC;
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
python3 -m json_to_db.display_group
python3 -m db_to_md.renderer
python3 extract_references.py

python3 verify_db.py
```

После обновления исходных файлов достаточно повторно запустить `pipeline.py` — ручное вмешательство не требуется.
