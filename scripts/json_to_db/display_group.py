#!/usr/bin/env python3
"""
建立 display_group_map 表：law_id → display_group + display_subgroup
用于客户端展示，与 legal_domain 解耦，可独立更新。
"""

import sqlite3
from pathlib import Path

from config import DB_PATH

# display_group 映射（legal_domain → display_group）
_DOMAIN_TO_GROUP = {
    '宪法相关法': '宪法与国家机构',
    '民法典':     '民事与商事',
    '民法商法':   '民事与商事',
    '刑法':       '刑事',
    '行政法':     '行政与公法',
    '经济法':     '经济、税务与金融',
    '社会法':     '劳动与社会保障',
    '诉讼与非诉讼程序法': '诉讼与司法程序',
}

# 民事与商事 子分组关键词（按优先级）
_CIVIL_SUBGROUPS = [
    ('民法典',           ['民法典']),
    ('合同与债权',       ['合同', '债权', '债务', '买卖', '租赁', '借款', '票据']),
    ('公司与破产',       ['公司', '企业破产', '清算', '个人独资', '合伙企业', '农民专业合作社']),
    ('知识产权',         ['知识产权', '专利', '商标', '著作权', '版权', '不正当竞争']),
    ('担保与物权',       ['担保', '物权', '抵押', '质押', '留置', '不动产登记']),
    ('婚姻、家庭与继承', ['婚姻', '家庭', '继承', '收养', '监护', '人身安全保护']),
    ('保险',             ['保险']),
    ('海事与运输',       ['海商', '海事', '运输', '航运', '船舶', '港口']),
    ('外商与涉外',       ['外商投资', '中外合资', '涉外', '外资']),
    ('证券与期货',       ['证券', '期货', '基金', '股票', '上市', '期权']),
    ('综合与程序批复',   []),  # 兜底
]

# 刑事 子分组
_CRIMINAL_SUBGROUPS = [
    ('刑法及修正案',  ['法律', '修正案']),  # 按 category
    ('法律解释',      ['法律解释']),
    ('财产犯罪',      ['盗窃', '诈骗', '抢劫', '敲诈', '挪用', '贪污', '腐败', '受贿', '行贿', '职务']),
    ('人身犯罪',      ['人身', '故意伤害', '杀人', '强奸', '猥亵', '未成年', '拐卖', '绑架']),
    ('毒品与走私',    ['毒品', '走私', '贩毒', '制毒']),
    ('综合司法解释',  []),
]

# 行政与公法 子分组
_ADMIN_SUBGROUPS = [
    ('行政法律',     ['法律']),
    ('国家赔偿',     ['国家赔偿', '行政赔偿']),
    ('行政法规',     ['行政法规']),
    ('司法解释',     ['司法解释']),
]

# 经济、税务与金融 子分组
_ECON_SUBGROUPS = [
    ('税收与财政',         ['税', '财政', '预算', '审计', '会计', '国有资产']),
    ('金融、证券与保险',   ['金融', '银行', '证券', '保险', '信托', '外汇', '货币', '期货']),
    ('贸易、竞争与市场',   ['贸易', '竞争', '市场', '反垄断', '招标', '政府采购', '对外贸易', '海关']),
    ('农业、资源与能源',   ['农业', '渔业', '林业', '矿产', '能源', '石油', '煤炭', '电力', '土地']),
    ('其他经济法规',       []),
]

# 劳动与社会保障 子分组
_LABOR_SUBGROUPS = [
    ('劳动就业',       ['劳动', '就业', '工资', '劳动合同', '劳动争议']),
    ('社会保险与福利', ['社会保险', '工伤', '失业', '养老', '医疗保险', '社会保障']),
    ('特殊群体保护',   ['残疾人', '妇女', '未成年人', '老年人', '退役军人']),
    ('司法解释',       ['司法解释']),
    ('行政法规',       ['行政法规']),
]

# 诉讼与司法程序 子分组
_PROC_SUBGROUPS = [
    ('三大诉讼法',         ['民事诉讼', '刑事诉讼', '行政诉讼', '海事诉讼', '仲裁', '调解', '仲裁法']),
    ('律师、仲裁与公证',   ['律师', '公证', '仲裁法', '法律援助']),
    ('民事程序解释',       ['民事', '执行', '拍卖', '送达', '保全', '破产清算', '简易程序', '审判监督', '陪审']),
    ('刑事程序解释',       ['刑事', '死刑', '逮捕', '起诉', '指定管辖', '羁押']),
    ('行政程序解释',       ['行政', '国家赔偿', '行政赔偿', '复议']),
    ('文书、送达与废止',   ['送达', '文书', '废止', '司法协助', '法庭规则', '巡回法庭', '互联网法院', '国际商事']),
    ('行政法规',           ['行政法规']),
]


def _match_keywords(title: str, keywords: list[str]) -> bool:
    return any(kw in title for kw in keywords)


def _civil_subgroup(law: dict) -> str:
    cat   = law['category'] or ''
    title = law['title'] or ''
    domain = law['legal_domain'] or ''
    if domain == '民法典' or '民法典' in title:
        return '民法典'
    for subgroup, keywords in _CIVIL_SUBGROUPS:
        if not keywords:
            continue
        if _match_keywords(title, keywords):
            return subgroup
    return '综合与程序批复'


def _criminal_subgroup(law: dict) -> str:
    cat   = law['category'] or ''
    title = law['title'] or ''
    if cat in ('法律', '修正案'):
        return '刑法及修正案'
    if cat == '法律解释':
        return '法律解释'
    for subgroup, keywords in _CRIMINAL_SUBGROUPS[2:]:
        if not keywords:
            continue
        if _match_keywords(title, keywords):
            return subgroup
    return '综合司法解释'


def _admin_subgroup(law: dict) -> str:
    cat   = law['category'] or ''
    title = law['title'] or ''
    if cat == '法律':
        return '行政法律'
    if cat == '行政法规':
        # 有 subject_area 时用它
        subject = law.get('subject_area') or ''
        return f'行政法规/{subject}' if subject else '行政法规'
    if '国家赔偿' in title or '行政赔偿' in title:
        return '国家赔偿'
    if cat in ('司法解释', '法律解释'):
        return '司法解释'
    return '行政法律'


def _econ_subgroup(law: dict) -> str:
    cat   = law['category'] or ''
    title = law['title'] or ''
    if cat == '行政法规':
        subject = law.get('subject_area') or ''
        return f'行政法规/{subject}' if subject else '行政法规'
    for subgroup, keywords in _ECON_SUBGROUPS:
        if not keywords:
            continue
        if _match_keywords(title, keywords):
            return subgroup
    return '其他经济法规'


def _labor_subgroup(law: dict) -> str:
    cat   = law['category'] or ''
    title = law['title'] or ''
    if cat == '行政法规':
        return '行政法规'
    if cat in ('司法解释', '法律解释'):
        return '司法解释'
    for subgroup, keywords in _LABOR_SUBGROUPS[:3]:
        if _match_keywords(title, keywords):
            return subgroup
    return '劳动就业'


def _proc_subgroup(law: dict) -> str:
    cat   = law['category'] or ''
    title = law['title'] or ''
    if cat in ('法律',):
        for subgroup, keywords in _PROC_SUBGROUPS[:2]:
            if _match_keywords(title, keywords):
                return subgroup
        return '三大诉讼法'
    if cat == '行政法规':
        return '行政法规'
    # 司法解释：按内容分
    for subgroup, keywords in _PROC_SUBGROUPS[2:6]:
        if not keywords:
            continue
        if _match_keywords(title, keywords):
            return subgroup
    return '文书、送达与废止'


def compute_display(law: dict) -> tuple[str, str]:
    """Return (display_group, display_subgroup) for a law dict."""
    domain = law['legal_domain'] or '其他'
    group  = _DOMAIN_TO_GROUP.get(domain, '其他')

    if group == '宪法与国家机构':
        cat = law['category'] or ''
        if cat == '宪法':
            subgroup = '宪法'
        elif cat == '行政法规':
            subgroup = '行政法规'
        elif cat in ('司法解释', '法律解释'):
            subgroup = '司法解释'
        else:
            subgroup = '法律及决定'
    elif group == '民事与商事':
        subgroup = _civil_subgroup(law)
    elif group == '刑事':
        subgroup = _criminal_subgroup(law)
    elif group == '行政与公法':
        subgroup = _admin_subgroup(law)
    elif group == '经济、税务与金融':
        subgroup = _econ_subgroup(law)
    elif group == '劳动与社会保障':
        subgroup = _labor_subgroup(law)
    elif group == '诉讼与司法程序':
        subgroup = _proc_subgroup(law)
    else:
        subgroup = ''

    return group, subgroup


def build_display_group_map(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys=ON')

    # 建表（幂等）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS display_group_map (
            law_id          INTEGER PRIMARY KEY REFERENCES laws(id),
            display_group   TEXT NOT NULL,
            display_subgroup TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("DELETE FROM display_group_map")

    rows = conn.execute(
        "SELECT id, title, category, legal_domain, subject_area FROM laws WHERE is_current=1"
    ).fetchall()

    batch = []
    for law_id, title, category, legal_domain, subject_area in rows:
        law = {
            'id': law_id, 'title': title, 'category': category,
            'legal_domain': legal_domain, 'subject_area': subject_area,
        }
        group, subgroup = compute_display(law)
        batch.append((law_id, group, subgroup))

    conn.executemany(
        "INSERT INTO display_group_map (law_id, display_group, display_subgroup) VALUES (?,?,?)",
        batch
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dgm_group ON display_group_map(display_group, display_subgroup)")
    conn.commit()

    # 打印统计
    summary = conn.execute(
        "SELECT display_group, display_subgroup, COUNT(*) FROM display_group_map GROUP BY display_group, display_subgroup ORDER BY display_group, display_subgroup"
    ).fetchall()
    conn.close()

    print(f'display_group_map 建立完成：{len(batch)} 条')
    cur_group = None
    for grp, sub, cnt in summary:
        if grp != cur_group:
            print(f'\n  [{grp}]')
            cur_group = grp
        print(f'    {sub or "(无子分组)"}: {cnt}')


def run():
    print('\n=== 建立 display_group_map ===')
    build_display_group_map()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
