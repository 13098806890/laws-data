#!/usr/bin/env python3
"""
合并《最高人民法院公报》司法解释连载拆分文件为单一完整文件。

背景：公报将部分长司法解释分两期连载（如 199803/199804），导入数据库时
被拆成两个 law_id，导致 is_current 只能标记一半。本脚本将中文源 JSON
和 json_en 翻译各自合并为单一文件，保留 id 大者的文件名与 law_id。

用法：
  python3 scripts/merge_gongbao_serial.py --dry-run    # 预览
  python3 scripts/merge_gongbao_serial.py              # 执行合并
"""

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
CN_DIR = BASE_DIR / '最高人民法院公报' / '司法解释'
EN_DIR = BASE_DIR / 'json_en' / '司法解释'
BACKUP_DIR = BASE_DIR / 'logs' / 'gongbao_merge_backup'

# (主文件前缀, 续篇文件前缀, 标题)  — 保留 id 大者（续篇）
PAIRS = [
    ('199803_最高人民法院关于执行《中华人民共和国刑事诉讼法》若干问题的解释',
     '199804_最高人民法院关于执行《中华人民共和国刑事诉讼法》若干问题的解释'),
    ('201306_最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释',
     '201307_最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释（续）'),
    ('201505_最高人民法院关于适用《中华人民共和国民事诉讼法》的解释',
     '201506_最高人民法院关于适用《中华人民共和国民事诉讼法》的解释（续）'),
    ('202207_最高人民法院关于修改《最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释》的决定',
     '202208_最高人民法院关于修改《最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释》的决定（续）'),
]

# 续篇开头的头部块（标题/法释号/公告/（接上期）等），到正文开始
HEADER_CUT = re.compile(
    r'^(?:.*?(?:最高人民法院|最高人民法院　最高人民检察院|中华人民共和国最高人民法院).*?'
    r'(?:法释[〔\[][0-9]{4}[〕\]]\s*[0-9]+号).*?'
    r'(?:（接上期）|（接上期）|接上期)?)',
    flags=re.DOTALL,
)


def cut_header(content: str) -> str:
    """剥掉续篇开头的重复头部（标题、法释号、（接上期）等），保留正文。"""
    # 找到第一个以“X、”或“第X章”或“第X部分”开头的行/段落
    for m in re.finditer(r'\n?\s*(?:[一二三四五六七八九十]+、|[第][一二三四五六七八九十百千]+[章部分])', content):
        # 只接受出现在法释号之后的
        idx = content.find('号')
        if m.start() < idx + 2:
            continue
        return content[m.start():].lstrip('\n')
    return content


def cut_header_2015(content: str) -> str:
    """2015 民诉解释续篇：头部含公告文本，从章节标题处切开。"""
    for m in re.finditer(r'\n?\s*(?:[一二三四五六七八九十]+、|[第][一二三四五六七八九十百千]+[章部分])', content):
        idx = content.find('法释〔2015〕5号')
        if idx >= 0 and m.start() < idx + 2:
            continue
        return content[m.start():].lstrip('\n')
    return content


def normalize_article_no(s: str) -> Optional[int]:
    """把'第X条'转为整数；无法解析返回 None。"""
    m = re.match(r'第([零一二三四五六七八九十百千\d]+)条', s.strip())
    if not m:
        return None
    raw = m.group(1)
    if raw.isdigit():
        return int(raw)
    _C = {'零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
          '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000}
    total = tmp = 0
    for ch in raw:
        v = _C.get(ch, 0)
        if v >= 10:
            total += (tmp or 1) * v
            tmp = 0
        else:
            tmp = v
    return total + tmp


def merge_cn(main_path: Path, cont_path: Path) -> dict:
    """合并中文 JSON。主文件保留原字段，续篇正文拼接到主文件 content 后。"""
    main = json.loads(main_path.read_text(encoding='utf-8'))
    cont = json.loads(cont_path.read_text(encoding='utf-8'))
    cont_content = cont.get('content', '')

    # 剥头部
    if '（接上期）' in cont_content or '（接上期）' in cont_content:
        body = cut_header(cont_content)
    else:
        body = cut_header_2015(cont_content)
    if not body or len(body) < len(cont_content) // 3:
        body = cont_content  # 切失败则原样拼接

    merged = dict(main)
    merged['content'] = main.get('content', '').rstrip() + '\n\n' + body
    merged['issue'] = main.get('issue') or cont.get('issue')
    merged['url'] = main.get('url') or cont.get('url')
    return merged


def merge_en(main_path: Path, cont_path: Path) -> dict:
    """合并 json_en 翻译。主文件字段保留，续篇 articles 追加。"""
    main = json.loads(main_path.read_text(encoding='utf-8'))
    cont = json.loads(cont_path.read_text(encoding='utf-8'))
    articles = list(main.get('articles', []))
    cont_articles = list(cont.get('articles', []))
    seen = set()
    out = []
    for a in articles + cont_articles:
        n = normalize_article_no(a.get('article_number', ''))
        key = a.get('article_number', '').strip() if n is None else f'int:{n}'
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    merged = dict(main)
    merged['articles'] = out
    return merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只预览不写文件')
    args = ap.parse_args()

    if not args.dry_run:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    report = []
    for main_prefix, cont_prefix in PAIRS:
        main_cn = next(CN_DIR.glob(main_prefix + '*.json'), None)
        cont_cn = next(CN_DIR.glob(cont_prefix + '*.json'), None)
        main_en = next(EN_DIR.glob(main_prefix + '*.json'), None) if EN_DIR.exists() else None
        cont_en = next(EN_DIR.glob(cont_prefix + '*.json'), None) if EN_DIR.exists() else None

        if main_cn is None or cont_cn is None:
            print(f'  ⚠ 缺文件: {main_prefix} / {cont_prefix}')
            continue

        target = cont_cn  # 保留 id 大者（续篇）的文件名
        en_target = cont_en if cont_en else main_en
        mcn = merge_cn(main_cn, cont_cn)
        men = merge_en(main_en, cont_en) if (main_en and cont_en) else None

        if args.dry_run:
            en_info = '\n  英文: 缺失（跳过）'
            if men and en_target:
                main_arts = len(json.loads(main_en.read_text(encoding='utf-8')).get('articles', [])) if main_en else 0
                cont_arts = len(json.loads(cont_en.read_text(encoding='utf-8')).get('articles', [])) if cont_en else 0
                en_info = f'\n  英文: articles {main_arts}+{cont_arts} → {len(men["articles"])}'
            report.append(f'{cont_prefix}\n'
                          f'  中文: {len(main_cn.read_text(encoding="utf-8"))} → {len(json.dumps(mcn, ensure_ascii=False))} chars'
                          + en_info)
            continue

        # 备份原文件
        ts = datetime.now().strftime('%Y%m%d%H%M%S')
        for p in (main_cn, cont_cn, main_en, cont_en):
            if p and p.exists():
                bak = BACKUP_DIR / f'{ts}__{p.name}'
                shutil.copy2(p, bak)

        # 写入合并结果（到续篇文件名）
        cont_cn.write_text(json.dumps(mcn, ensure_ascii=False, indent=2), encoding='utf-8')
        if en_target and men:
            en_target.write_text(json.dumps(men, ensure_ascii=False, indent=2), encoding='utf-8')
        # 删除主文件（内容已并入续篇）
        main_cn.unlink()
        if main_en and main_en.exists() and (cont_en is None or main_en == main_en):
            pass
        if main_en and main_en.exists() and main_en != en_target:
            main_en.unlink()
        report.append(f'{cont_prefix}: 合并完成')

    print('\n'.join(report))
    if not args.dry_run:
        print(f'\n备份目录: {BACKUP_DIR}')
        print('下一步: 从 law_index.json 移除被合并的 id，然后重跑 pipeline')


if __name__ == '__main__':
    main()
