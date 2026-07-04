"""
check_content_quality.py
检查 law_content.db 中条文内容的质量问题：

1. PAGE 噪音：含 PAGE、HYPERLINK 等 Word 残留
2. 小写 l 误作数字 1：如 "l月"、"l万"、"l日"、"l年"、"l％" 等
3. 其他可疑英文：排除已知合法英文后的残留
"""

import re
import sqlite3
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / 'law_content.db'

# ── 合法英文模式（不报告） ──────────────────────────────────────────────────
# 签证字母、罗马数字、化学/物理符号、拼音标注、法条引用数字等
LEGAL_PATTERNS = [
    r'[CDGJFQRS]字签证',            # 签证类别
    r'[QH]旗',                      # 国际通语旗
    r'罗马体大写字母',               # 航空条例
    r'[A-Z]字旗',
    r'(?<![A-Za-z])[IⅠ-Ⅳ](?:、|级|类|期|等)',  # 罗马/全角数字分级
    r'I、?Ⅱ、?Ⅲ、?Ⅳ',
    r'pH值?',                        # 化学符号
    r'铀-\d+|钚-\d+',               # 核材料
    r'P2P',
    r'[A-Za-z]+\d*[-－]\d+',        # 规格型号
    r'第\d+条|第\d+款',             # 阿拉伯数字法条引用（合法）
    r'[（(]\d+[)）]',               # 编号
    r'\d+[A-Za-z]+',                # 数字+单位（如 3G、5G）
    r'[a-zA-Z]+\d+[a-zA-Z]*',      # 型号
    r'汉语拼音',
    r'[A-Z]{1,3}(?=公司|集团|银行)',  # 公司简称
]
LEGAL_RE = re.compile('|'.join(LEGAL_PATTERNS))

# 完全合法的英文词（整词匹配）
LEGAL_WORDS = {'pH', 'P2P', 'DNA', 'RNA', 'GDP', 'CPI', 'GPS', 'HIV', 'ATM',
               'IT', 'TV', 'PC', 'APP', 'Wi-Fi', 'WiFi', 'IP', 'QQ', 'AI'}

# ── 检测规则 ──────────────────────────────────────────────────────────────────

def has_page_noise(content: str) -> list[str]:
    """检测 PAGE/HYPERLINK 等 Word 残留"""
    issues = []
    if re.search(r'[-－]\s*PAGE\s+\d+\s*[-－]', content):
        issues.append('PAGE噪音')
    if re.search(r'HYPERLINK', content):
        issues.append('HYPERLINK残留')
    if re.search(r'javascript:', content, re.IGNORECASE):
        issues.append('javascript:残留')
    return issues


def has_l_as_1(content: str) -> list[str]:
    """检测小写 l 误作数字 1 的情况"""
    issues = []
    # l 后面跟数量词或时间词
    patterns = [
        (r'(?<!\w)l(?=月|年|日|万|千|百|元|％|%|位|个|项|条|款)', '小写l误作1（数量/时间）'),
        (r'(?<!\w)l(?=\d)', '小写l开头接数字'),
        (r'(?<=\d)l(?!\w)', '数字后小写l'),
        (r'[(（]l－', '公式中小写l'),
        (r'－l[)）]', '公式中小写l'),
    ]
    for pat, label in patterns:
        if re.search(pat, content):
            issues.append(label)
    return issues


def suspicious_english(content: str) -> list[str]:
    """检测其余可疑英文（排除合法模式后）"""
    # 找所有英文片段
    fragments = re.findall(r'[A-Za-z][A-Za-z\d\-]*', content)
    suspicious = []
    for frag in fragments:
        if frag.upper() in LEGAL_WORDS or frag in LEGAL_WORDS:
            continue
        if LEGAL_RE.search(frag):
            continue
        # 只有单个字母的情况单独判断
        if len(frag) == 1:
            # 单字母：只有在明显错误上下文才报告
            idx = content.find(frag)
            ctx = content[max(0, idx-4):idx+5]
            if re.search(r'\d' + frag + r'[月年日万]', ctx) or re.search(frag + r'\d', ctx):
                suspicious.append(f'可疑单字母 {frag!r}')
        else:
            suspicious.append(f'可疑英文 {frag!r}')
    return list(dict.fromkeys(suspicious))  # 去重保序


def main():
    conn = sqlite3.connect(DB_PATH)

    rows = conn.execute("""
        SELECT l.title, n.article_number, n.content, n.article_num
        FROM nodes n
        JOIN laws l ON n.law_id = l.id
        WHERE n.type = 'article'
          AND (
            n.content GLOB '*[A-Za-z]*'
            OR n.content LIKE '%PAGE%'
            OR n.content LIKE '%HYPERLINK%'
          )
        ORDER BY l.title, n.article_num
    """).fetchall()

    conn.close()

    # 按问题类型分组统计
    by_type = defaultdict(list)
    total_issues = 0

    for law_title, art_num, content, _ in rows:
        issues = []
        issues += has_page_noise(content)
        issues += has_l_as_1(content)
        # susp = suspicious_english(content)
        # issues += susp

        if issues:
            total_issues += 1
            for issue in issues:
                by_type[issue].append((law_title, art_num, content))

    # ── 输出报告 ──────────────────────────────────────────────────────────────

    print(f'扫描含英文字母条文，发现 {total_issues} 处明确问题\n')

    sep = '=' * 60
    for issue_type, items in sorted(by_type.items()):
        print(sep)
        print(f'【{issue_type}】共 {len(items)} 处')
        print(sep)
        for law_title, art_num, content in items[:20]:
            # 找出问题片段的上下文
            snippet = content[:200].replace('\n', ' ')
            print(f'  《{law_title}》{art_num}')
            print(f'  {snippet}')
            print()
        if len(items) > 20:
            print(f'  ...（共 {len(items)} 处，仅显示前 20）\n')

    # ── 额外：统计所有含英文但未被标记问题的条文（仅统计数量） ──────────────
    print()
    print(sep)
    print('含英文字母但未被标记为问题的条文（按法律统计）:')
    print(sep)

    conn2 = sqlite3.connect(DB_PATH)
    rows2 = conn2.execute("""
        SELECT l.title, n.article_number, n.content
        FROM nodes n
        JOIN laws l ON n.law_id = l.id
        WHERE n.type = 'article'
          AND n.content GLOB '*[A-Za-z]*'
        ORDER BY l.title
    """).fetchall()
    conn2.close()

    law_counts = defaultdict(list)
    for law_title, art_num, content in rows2:
        issues = has_page_noise(content) + has_l_as_1(content)
        if not issues:
            # 找出英文片段
            frags = re.findall(r'[A-Za-z][A-Za-z\d\-]*', content)
            law_counts[law_title].append((art_num, frags[:5]))

    for law_title, arts in sorted(law_counts.items(), key=lambda x: -len(x[1])):
        print(f'  《{law_title}》{len(arts)} 条')
        for art_num, frags in arts[:3]:
            print(f'    {art_num}: {frags}')
        if len(arts) > 3:
            print(f'    ...')
        print()


if __name__ == '__main__':
    main()
