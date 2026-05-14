#!/usr/bin/env python3
"""
直接从 laws 表计算展示分组，导出 law_menu.json。
无需中间表 display_group_map。

格式：
{
  "name": "默认分类",
  "version": "YYYY-MM-DD",
  "groups": [
    {
      "label": "民事与商事",
      "subgroups": [
        { "label": "民法典", "laws": [{"id": 101, "title": "..."}, ...] },
        ...
      ]
    },
    ...
  ]
}
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

from config import DB_PATH, MENU_PATH

# ── 展示分组映射（legal_domain → display_group）────────────────────
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

# ── 子分组关键词表 ────────────────────────────────────────────────
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
    ('综合与程序批复',   []),
]

_CRIMINAL_SUBGROUPS = [
    ('刑法及修正案', ['法律', '修正案']),
    ('法律解释',     ['法律解释']),
    ('财产犯罪',     ['盗窃', '诈骗', '抢劫', '敲诈', '挪用', '贪污', '腐败', '受贿', '行贿', '职务']),
    ('人身犯罪',     ['人身', '故意伤害', '杀人', '强奸', '猥亵', '未成年', '拐卖', '绑架']),
    ('毒品与走私',   ['毒品', '走私', '贩毒', '制毒']),
    ('综合司法解释', []),
]

_ECON_SUBGROUPS = [
    ('税收与财政',       ['税', '财政', '预算', '审计', '会计', '国有资产']),
    ('金融、证券与保险', ['金融', '银行', '证券', '保险', '信托', '外汇', '货币', '期货']),
    ('贸易、竞争与市场', ['贸易', '竞争', '市场', '反垄断', '招标', '政府采购', '对外贸易', '海关']),
    ('农业、资源与能源', ['农业', '渔业', '林业', '矿产', '能源', '石油', '煤炭', '电力', '土地']),
    ('其他经济法规',     []),
]

_LABOR_SUBGROUPS = [
    ('劳动就业',       ['劳动', '就业', '工资', '劳动合同', '劳动争议']),
    ('社会保险与福利', ['社会保险', '工伤', '失业', '养老', '医疗保险', '社会保障']),
    ('特殊群体保护',   ['残疾人', '妇女', '未成年人', '老年人', '退役军人']),
    ('司法解释',       ['司法解释']),
    ('行政法规',       ['行政法规']),
]

_PROC_SUBGROUPS = [
    ('三大诉讼法',       ['民事诉讼', '刑事诉讼', '行政诉讼', '海事诉讼', '仲裁', '调解', '仲裁法']),
    ('律师、仲裁与公证', ['律师', '公证', '仲裁法', '法律援助']),
    ('民事程序解释',     ['民事', '执行', '拍卖', '送达', '保全', '破产清算', '简易程序', '审判监督', '陪审']),
    ('刑事程序解释',     ['刑事', '死刑', '逮捕', '起诉', '指定管辖', '羁押']),
    ('行政程序解释',     ['行政', '国家赔偿', '行政赔偿', '复议']),
    ('文书、送达与废止', ['送达', '文书', '废止', '司法协助', '法庭规则', '巡回法庭', '互联网法院', '国际商事']),
    ('行政法规',         ['行政法规']),
]

# ── 顶层分组和子分组排列顺序 ──────────────────────────────────────
_GROUP_ORDER = [
    '宪法与国家机构', '民事与商事', '刑事', '行政与公法',
    '经济、税务与金融', '劳动与社会保障', '诉讼与司法程序', '其他',
]

_SUBGROUP_ORDER: dict[str, list[str]] = {
    '宪法与国家机构': ['宪法', '法律及决定', '行政法规', '司法解释'],
    '民事与商事': [
        '民法典', '合同与债权', '公司与破产', '知识产权',
        '担保与物权', '婚姻、家庭与继承', '保险',
        '海事与运输', '外商与涉外', '证券与期货', '综合与程序批复',
    ],
    '刑事': ['刑法及修正案', '法律解释', '财产犯罪', '人身犯罪', '毒品与走私', '综合司法解释'],
    '行政与公法': ['行政法律', '国家赔偿', '司法解释'],
    '经济、税务与金融': ['税收与财政', '金融、证券与保险', '贸易、竞争与市场', '农业、资源与能源', '其他经济法规'],
    '劳动与社会保障': ['劳动就业', '社会保险与福利', '特殊群体保护', '司法解释', '行政法规'],
    '诉讼与司法程序': [
        '三大诉讼法', '律师、仲裁与公证', '民事程序解释',
        '刑事程序解释', '行政程序解释', '文书、送达与废止', '行政法规',
    ],
}

_ADMIN_SUBJECT_ORDER = [
    '税务财政', '海关进出口', '金融证券', '交通运输', '能源电力',
    '生态环境', '自然资源', '土地城建', '农业农村', '卫生医药',
    '劳动就业', '社会民政', '教育科技', '信息通信', '工商市场',
    '安全应急', '公安司法', '军事国防', '行政法制', '涉外外资',
]


# ── 子分组计算逻辑 ────────────────────────────────────────────────

def _match(title: str, keywords: list[str]) -> bool:
    return any(kw in title for kw in keywords)


def _civil_subgroup(title: str, category: str, domain: str) -> str:
    if domain == '民法典' or '民法典' in title:
        return '民法典'
    for subgroup, kws in _CIVIL_SUBGROUPS:
        if kws and _match(title, kws):
            return subgroup
    return '综合与程序批复'


def _criminal_subgroup(title: str, category: str) -> str:
    if category in ('法律', '修正案'):
        return '刑法及修正案'
    if category == '法律解释':
        return '法律解释'
    for subgroup, kws in _CRIMINAL_SUBGROUPS[2:]:
        if kws and _match(title, kws):
            return subgroup
    return '综合司法解释'


def _admin_subgroup(title: str, category: str, subject_area: str) -> str:
    if category == '法律':
        return '行政法律'
    if category == '行政法规':
        return f'行政法规/{subject_area}' if subject_area else '行政法规'
    if '国家赔偿' in title or '行政赔偿' in title:
        return '国家赔偿'
    if category in ('司法解释', '法律解释'):
        return '司法解释'
    return '行政法律'


def _econ_subgroup(title: str, category: str, subject_area: str) -> str:
    if category == '行政法规':
        return f'行政法规/{subject_area}' if subject_area else '行政法规'
    for subgroup, kws in _ECON_SUBGROUPS:
        if kws and _match(title, kws):
            return subgroup
    return '其他经济法规'


def _labor_subgroup(title: str, category: str) -> str:
    if category == '行政法规':
        return '行政法规'
    if category in ('司法解释', '法律解释'):
        return '司法解释'
    for subgroup, kws in _LABOR_SUBGROUPS[:3]:
        if _match(title, kws):
            return subgroup
    return '劳动就业'


def _proc_subgroup(title: str, category: str) -> str:
    if category == '法律':
        for subgroup, kws in _PROC_SUBGROUPS[:2]:
            if _match(title, kws):
                return subgroup
        return '三大诉讼法'
    if category == '行政法规':
        return '行政法规'
    for subgroup, kws in _PROC_SUBGROUPS[2:6]:
        if kws and _match(title, kws):
            return subgroup
    return '文书、送达与废止'


def compute_display(title: str, category: str, legal_domain: str,
                    subject_area: str) -> tuple[str, str]:
    cat   = category or ''
    subj  = subject_area or ''
    group = _DOMAIN_TO_GROUP.get(legal_domain or '', '')
    if not group:
        # 按 category 兜底
        if cat in ('法律', '宪法', '修正案', '法律解释'):
            group = '宪法与国家机构'
        elif cat == '行政法规':
            group = '行政与公法'
        elif cat in ('司法解释', '监察法规'):
            group = '诉讼与司法程序'
        else:
            group = '其他'

    if group == '宪法与国家机构':
        if cat == '宪法':             subgroup = '宪法'
        elif cat == '行政法规':       subgroup = '行政法规'
        elif cat in ('司法解释', '法律解释'): subgroup = '司法解释'
        else:                         subgroup = '法律及决定'
    elif group == '民事与商事':
        subgroup = _civil_subgroup(title, cat, legal_domain or '')
    elif group == '刑事':
        subgroup = _criminal_subgroup(title, cat)
    elif group == '行政与公法':
        subgroup = _admin_subgroup(title, cat, subj)
    elif group == '经济、税务与金融':
        subgroup = _econ_subgroup(title, cat, subj)
    elif group == '劳动与社会保障':
        subgroup = _labor_subgroup(title, cat)
    elif group == '诉讼与司法程序':
        subgroup = _proc_subgroup(title, cat)
    else:
        subgroup = ''
    return group, subgroup


def _sort_subgroups(group: str, subgroups: list[str]) -> list[str]:
    order = _SUBGROUP_ORDER.get(group, [])
    known = [s for s in order if s in subgroups]
    admin = [s for s in subgroups if s.startswith('行政法规/')]
    topics = [s[len('行政法规/'):] for s in admin]
    sorted_topics = (
        [t for t in _ADMIN_SUBJECT_ORDER if t in topics]
        + sorted(t for t in topics if t not in _ADMIN_SUBJECT_ORDER)
    )
    known_admin = [f'行政法规/{t}' for t in sorted_topics]
    extra = sorted(s for s in subgroups if s not in known and s not in admin)
    return known + known_admin + extra


# ── 主函数 ────────────────────────────────────────────────────────

def export_menu(db_path: Path = DB_PATH, menu_path: Path = MENU_PATH):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """SELECT id, title, category, legal_domain, subject_area FROM laws
           WHERE is_current=1 AND (source='flk' OR (source='gongbao' AND legal_domain != ''))"""
    ).fetchall()
    conn.close()

    tree: dict[str, dict[str, list[dict]]] = {}
    for law_id, title, category, legal_domain, subject_area in rows:
        group, subgroup = compute_display(title, category, legal_domain, subject_area)
        tree.setdefault(group, {}).setdefault(subgroup, []).append(
            {'id': law_id, 'title': title}
        )

    sorted_groups = (
        [g for g in _GROUP_ORDER if g in tree]
        + sorted(g for g in tree if g not in _GROUP_ORDER)
    )
    groups_out = []
    for group in sorted_groups:
        sub_map = tree[group]
        sorted_subs = _sort_subgroups(group, list(sub_map.keys()))
        groups_out.append({
            'label': group,
            'subgroups': [
                {'label': s, 'laws': sorted(sub_map[s], key=lambda x: x['title'])}
                for s in sorted_subs
            ],
        })

    menu = {
        'name': '默认分类',
        'version': date.today().isoformat(),
        'groups': groups_out,
    }
    menu_path.write_text(json.dumps(menu, ensure_ascii=False, indent=2), encoding='utf-8')

    total = sum(len(s['laws']) for g in groups_out for s in g['subgroups'])
    print(f'law_menu.json 导出完成：{len(groups_out)} 个分组，{total} 部法律 → {menu_path}')


def run():
    print('\n=== 导出 law_menu.json ===')
    export_menu()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
