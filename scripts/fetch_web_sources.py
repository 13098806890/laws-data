#!/usr/bin/env python3
"""
从最高人民法院网站抓取法律文本，转换为伪 docx（实为纯文本段落结构），
供 converter.py 解析。

已知来源：
  - 刑诉解释 2021: https://www.court.gov.cn/zixun/xiangqing/286491.html
  - 执行担保规定: http://gongbao.court.gov.cn/Details/8052c6020c2d7cba30c99fc450d61e.html
  - 九民纪要: https://www.court.gov.cn/zixun/xiangqing/199691.html

用法：
  python3 scripts/fetch_web_sources.py          # 抓取所有来源并输出文本文件
  python3 scripts/fetch_web_sources.py --no-fetch  # 仅用缓存（不发请求）
"""

import re
import sys
import time
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

CACHE_DIR = BASE_DIR / 'sources/_web_sources/html_cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── 来源配置 ────────────────────────────────────────────────────────────────

SOURCES = [
    {
        'name':      '最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释',
        'date':      '20210126',
        'url':       'https://www.court.gov.cn/zixun/xiangqing/286491.html',
        'cache':     'court_286491_刑诉解释2021.html',
        'parser':    'court_gov',
        'category':  '司法解释',
        'replaces':  '最高人民法院关于适用《中华人民共和国刑事诉讼法》的解释_20210126.docx',
    },
    {
        'name':      '最高人民法院关于执行担保若干问题的规定',
        'date':      '20201229',
        'url':       'http://gongbao.court.gov.cn/Details/8052c6020c2d7cba30c99fc450d61e.html',
        'cache':     'gongbao_执行担保.html',
        'parser':    'gongbao_court',
        'category':  '司法解释',
        'replaces':  '最高人民法院关于执行担保若干问题的规定_20201229.docx',
    },
    {
        'name':      '全国法院民商事审判工作会议纪要',
        'date':      '20191114',
        'url':       'https://www.court.gov.cn/zixun/xiangqing/199691.html',
        'cache':     'court_199691_九民纪要.html',
        'parser':    'court_gov',
        'category':     '司法解释',
        'replaces':     None,  # 新增，无对应 docx
        'post_process': 'numbered_articles',
    },
]


# ── HTML 抓取 ────────────────────────────────────────────────────────────────

def fetch_html(url: str, cache_path: Path, force: bool = False) -> str:
    if cache_path.exists() and not force:
        print(f'  使用缓存: {cache_path.name}')
        return cache_path.read_text(encoding='utf-8')

    print(f'  抓取: {url}')
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode('utf-8', errors='replace')
    cache_path.write_text(html, encoding='utf-8')
    time.sleep(1)
    return html


# ── HTML 解析器 ──────────────────────────────────────────────────────────────

def _clean_html(html_fragment: str) -> str:
    """去 HTML 标签，还原常见实体，规整空白。"""
    text = re.sub(r'<br\s*/?>', '\n', html_fragment, flags=re.I)
    text = re.sub(r'</p>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', '　')
    text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    text = re.sub(r'&#\d+;', '', text)
    return text


def parse_court_gov(html: str) -> list[str]:
    """解析 court.gov.cn 详情页，提取 class="txt big" 正文。"""
    m = re.search(
        r'class=["\']txt big["\']>(.*?)(?:class=["\']txt_etr["\']|class=["\']share["\'])',
        html, re.S
    )
    if not m:
        # fallback: 找 <div class="txt big"> 到 </div>
        m = re.search(r'<div[^>]*class=["\']txt big["\'][^>]*>(.*?)</div\s*>', html, re.S)
    if not m:
        raise ValueError('未找到 class="txt big" 正文区域')
    text = _clean_html(m.group(1))
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return lines


def parse_gongbao_court(html: str) -> list[str]:
    """解析 gongbao.court.gov.cn 详情页，提取 class="online_box contentH" 正文。"""
    m = re.search(
        r'class=["\']online_box contentH["\'][^>]*>(.*?)(?:class=["\'](?:footer|modal)["\'])',
        html, re.S
    )
    if not m:
        m = re.search(r'online_box contentH["\'][^>]*>(.*?)</div\s*>', html, re.S)
    if not m:
        raise ValueError('未找到 class="online_box contentH" 正文区域')
    text = _clean_html(m.group(1))
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return lines


PARSERS = {
    'court_gov':     parse_court_gov,
    'gongbao_court': parse_gongbao_court,
}


# ── 后处理器 ─────────────────────────────────────────────────────────────────

_INT_TO_CN_UNITS = [
    (1000, '千'), (900, '九百'), (800, '八百'), (700, '七百'), (600, '六百'),
    (500, '五百'), (400, '四百'), (300, '三百'), (200, '二百'), (100, '一百'),
    (90, '九十'), (80, '八十'), (70, '七十'), (60, '六十'), (50, '五十'),
    (40, '四十'), (30, '三十'), (20, '二十'), (19, '十九'), (18, '十八'),
    (17, '十七'), (16, '十六'), (15, '十五'), (14, '十四'), (13, '十三'),
    (12, '十二'), (11, '十一'), (10, '十'),
    (9, '九'), (8, '八'), (7, '七'), (6, '六'), (5, '五'),
    (4, '四'), (3, '三'), (2, '二'), (1, '一'),
]

def _int_to_cn(n: int) -> str:
    result = ''
    for v, s in _INT_TO_CN_UNITS:
        while n >= v:
            result += s
            n -= v
    return result

_NUMBERED_ART_RE = re.compile(r'^(\d+)\.(\s*【)')

def postprocess_numbered_articles(lines: list[str]) -> list[str]:
    """将 N.【标题】正文 格式转换为 第N条　【标题】正文，供 converter.py 识别。"""
    out = []
    for line in lines:
        m = _NUMBERED_ART_RE.match(line)
        if m:
            n = int(m.group(1))
            cn = _int_to_cn(n)
            rest = line[m.end(1) + 1:]  # skip the '.'
            line = f'第{cn}条　{rest.lstrip()}'
        out.append(line)
    return out


POSTPROCESSORS = {
    'numbered_articles': postprocess_numbered_articles,
}


# ── 文本文件输出 ──────────────────────────────────────────────────────────────

def lines_to_txt(lines: list[str], out_path: Path):
    """把段落列表写成 UTF-8 文本，每段一行（converter.py 可直接处理）。"""
    out_path.write_text('\n'.join(lines), encoding='utf-8')
    print(f'  文本已写入: {out_path}')


# ── 主流程 ───────────────────────────────────────────────────────────────────

def run(force_fetch: bool = False):
    for src in SOURCES:
        print(f'\n=== {src["name"]} ===')
        cache_path = CACHE_DIR / src['cache']

        html = fetch_html(src['url'], cache_path, force=force_fetch)

        parser = PARSERS[src['parser']]
        lines = parser(html)
        print(f'  解析到 {len(lines)} 段文字')

        post = src.get('post_process')
        if post and post in POSTPROCESSORS:
            lines = POSTPROCESSORS[post](lines)
            art_count = sum(1 for l in lines if l.startswith('第') and '条' in l[:6])
            print(f'  后处理({post})后：{art_count} 条条文')

        stem = f'{src["name"]}_{src["date"]}'
        out_dir = BASE_DIR / 'sources' / src['category']
        out_path = out_dir / (stem + '.txt')
        lines_to_txt(lines, out_path)

        if src['replaces']:
            print(f'  替换目标: {src["replaces"]}')

    print('\n完成。')


if __name__ == '__main__':
    force = '--force' in sys.argv
    run(force_fetch=force)
