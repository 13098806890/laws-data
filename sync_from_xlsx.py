import json
import glob
import xlrd
import re
import os

# ── 一、读取所有 xlsx，以文件名（title_YYYYMMDD）为主键建立索引 ─────────────
xlsx_index = {}  # fname_key -> {effective_date, category}

for path in glob.glob('/Users/doxie/laws_data/**/*.xlsx', recursive=True):
    wb = xlrd.open_workbook(path)
    for sheet in wb.sheets():
        for i in range(1, sheet.nrows):
            row = sheet.row_values(i)
            title = str(row[0]).strip()
            pub = str(row[1]).strip()
            eff = str(row[2]).strip()
            cat = str(row[3]).strip()
            key = f'{title}_{pub.replace("-", "")}'
            if key not in xlsx_index:
                xlsx_index[key] = {'effective_date': eff, 'category': cat}

print(f'xlsx索引条目: {len(xlsx_index)}')

# ── 二、处理所有 JSON ────────────────────────────────────────────────────
updated = skipped = no_match = 0
unmatched = []

for path in glob.glob('/Users/doxie/laws_data/json/**/*.json', recursive=True):
    if 'index' in path:
        continue

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    # 从文件名构造匹配键（去掉.json）
    fname_key = os.path.basename(path)[:-5]
    entry = xlsx_index.get(fname_key)

    if entry is None:
        no_match += 1
        unmatched.append(('/'.join(path.split('/')[-2:]), data.get('title', '')[:35]))
        continue

    changed = False

    # 更新 category
    new_cat = entry['category']
    if data.get('category') != new_cat:
        data['category'] = new_cat
        changed = True

    # 用 xlsx 的 effective_date 覆盖（xlsx 是权威来源）
    new_eff = entry['effective_date']
    if new_eff and data.get('effective_date') != new_eff:
        data['effective_date'] = new_eff
        changed = True
    elif new_eff and 'effective_date' not in data:
        data['effective_date'] = new_eff
        changed = True

    if changed:
        ordered = {}
        for k in ('title', 'filename', 'category', 'pub_date', 'effective_date',
                  'promulgation_info', 'legal_domain', 'total_articles', 'chapters'):
            if k in data:
                ordered[k] = data[k]
        for k, v in data.items():
            if k not in ordered:
                ordered[k] = v
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(ordered, f, ensure_ascii=False, indent=2)
        updated += 1
    else:
        skipped += 1

print(f'更新: {updated}')
print(f'无变化（跳过）: {skipped}')
print(f'未在xlsx中匹配: {no_match}')

if unmatched:
    print(f'\n未匹配文件（{len(unmatched)}个）:')
    for f, t in unmatched[:20]:
        print(f'  [{f}] {t!r}')
    if len(unmatched) > 20:
        print(f'  ...共{len(unmatched)}个')

