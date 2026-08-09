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

# ── 分组/子分组英文标签（英文版目录展示）────────────────────────────
_GROUP_EN = {
    '宪法与国家机构':     'Constitution & State Institutions',
    '民事与商事':         'Civil & Commercial',
    '刑事':               'Criminal',
    '行政与公法':         'Administrative & Public Law',
    '经济、税务与金融':   'Economy, Taxation & Finance',
    '劳动与社会保障':     'Labor & Social Security',
    '诉讼与司法程序':     'Litigation & Judicial Procedure',
    '其他':               'Other',
}

_SUBGROUP_EN = {
    # 宪法与国家机构
    '宪法':           'Constitution',
    '法律及决定':     'Laws & Decisions',
    '司法解释':       'Judicial Interpretations',
    # 民事与商事
    '民法典':               'Civil Code',
    '合同与债权':           'Contracts & Obligations',
    '公司与破产':           'Companies & Bankruptcy',
    '知识产权':             'Intellectual Property',
    '担保与物权':           'Security & Property Rights',
    '婚姻、家庭与继承':     'Marriage, Family & Inheritance',
    '保险':                 'Insurance',
    '海事与运输':           'Maritime & Transport',
    '外商与涉外':           'Foreign Investment & Foreign Affairs',
    '证券与期货':           'Securities & Futures',
    '综合与程序批复':       'General & Procedural Responses',
    # 刑事
    '刑法及修正案':       'Criminal Law & Amendments',
    '法律解释':           'Judicial Interpretations',
    '侵犯财产':           'Property Crimes',
    '经济犯罪':           'Economic Crimes',
    '贪污贿赂':           'Embezzlement & Bribery',
    '人身犯罪':           'Crimes Against the Person',
    '毒品与走私':         'Drugs & Smuggling',
    '妨害社会管理秩序':   'Crimes Against Social Order',
    '刑罚执行':           'Sentence Execution',
    '证据规则':           'Evidence Rules',
    '刑事诉讼程序':       'Criminal Procedure',
    '审判监督':           'Trial Supervision',
    '辩护与代理':         'Defense & Representation',
    '未成年人刑事程序':   'Juvenile Criminal Procedure',
    '检察院':             'Procuratorate',
    # 行政与公法
    '行政法律':     'Administrative Laws',
    '教育科技':     'Education & Science',
    '卫生医药':     'Health & Medicine',
    '生态环境':     'Ecology & Environment',
    '公安司法':     'Public Security & Justice',
    '社会民政':     'Social & Civil Affairs',
    '土地城建':     'Land & Urban Development',
    '自然资源':     'Natural Resources',
    '劳动就业':     'Labor & Employment',
    '税务财政':     'Taxation & Finance',
    '国家赔偿':     'State Compensation',
    '信息通信':     'Information & Communications',
    # 经济、税务与金融
    '税收与财政':         'Taxation & Public Finance',
    '金融、证券与保险':   'Finance, Securities & Insurance',
    '贸易、竞争与市场':   'Trade, Competition & Market',
    '农业、资源与能源':   'Agriculture, Resources & Energy',
    '其他经济法规':       'Other Economic Regulations',
    # 劳动与社会保障
    '社会保险与福利':   'Social Insurance & Welfare',
    '特殊群体保护':     'Protection of Special Groups',
    '行政法规':         'Administrative Regulations',
    # 诉讼与司法程序
    '民事诉讼':             'Civil Litigation',
    '刑事诉讼':             'Criminal Litigation',
    '行政诉讼':             'Administrative Litigation',
    '律师、仲裁与公证':     'Lawyers, Arbitration & Notarization',
    '文书、送达与废止':     'Documents, Service & Repeals',
}

# 行政法规子分组：主题 → 英文（"行政法规/XXX" 的 XXX 部分）
_ADMIN_TOPIC_EN = {
    '税务财政': 'Taxation & Finance',
    '海关进出口': 'Customs & Import-Export',
    '金融证券': 'Banking & Securities',
    '交通运输': 'Transportation',
    '能源电力': 'Energy & Power',
    '生态环境': 'Ecology & Environment',
    '自然资源': 'Natural Resources',
    '土地城建': 'Land & Urban Development',
    '农业农村': 'Agriculture & Rural Affairs',
    '卫生医药': 'Health & Medicine',
    '劳动就业': 'Labor & Employment',
    '社会民政': 'Social & Civil Affairs',
    '教育科技': 'Education & Science',
    '信息通信': 'Information & Communications',
    '工商市场': 'Industry, Commerce & Market',
    '安全应急': 'Safety & Emergency Response',
    '公安司法': 'Public Security & Justice',
    '军事国防': 'Military & National Defense',
    '行政法制': 'Administrative Rule of Law',
    '涉外外资': 'Foreign Affairs & Investment',
}

def subgroup_label_en(label: str) -> str:
    """计算子分组英文标签：'行政法规/XXX' → 'Administrative Regulations: XXX'"""
    if label.startswith('行政法规/'):
        topic = label[len('行政法规/'):]
        topic_en = _ADMIN_TOPIC_EN.get(topic, topic)
        return f'Administrative Regulations: {topic_en}'
    return _SUBGROUP_EN.get(label, label)


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
    ('侵犯财产',     ['盗窃','诈骗','敲诈','抢夺','抢劫','挪用','强迫借贷','拾得他人信用卡','盗用','赃物','合同诈骗','赃物估价','职务侵占','经济犯罪嫌疑']),
    ('经济犯罪',     ['非法经营','非法集资','非法放贷','知识产权','侵犯知识产权','税收','生产销售伪劣','伪劣商品','赌博','洗钱','伪造','假币','危害税收','税收征管','非法制造']),
    ('贪污贿赂',     ['受贿','行贿','贪污','职务犯罪','渎职','渎职侵权','私放在押人员','挪用','第二百二十九条']),
    ('人身犯罪',     ['非法行医','袭警','寻衅滋事','性侵','强奸','猥亵','嫖宿','未成年人犯罪','拐卖','绑架','故意伤害','杀人','人身','虐待','遗弃','非法采供血液','虐待被监管人','强制隔离戒毒']),
    ('毒品与走私',   ['毒品','走私','毒鼠强','制毒','贩毒','麻醉药品','精神药品','易制毒']),
    ('妨害社会管理秩序', ['计算机犯罪','网络犯罪','信息网络','淫秽','诽谤','开设赌场','组织考试作弊','黑社会','恶势力','虚假诉讼','扰乱法庭','破坏监管','脱逃','组织越狱','妨害国','出入境','文物犯罪','环境犯罪','黑土地','破坏公用电信','枪支','弹药','爆炸物','军用','军职','逃离部队','组织考试作弊','非法制造','买卖','运输','储存','非法采供血液','公务用枪','假币','拒不执行判决','掩饰、隐瞒','第三百一十三条']),
    ('刑罚执行',     ['减刑','假释','暂予监外执行','禁止令','缓刑','台湾地区服刑','无期徒刑','缓刑犯']),
    ('证据规则',     ['证据','电子数据','非法证据']),
    ('刑事诉讼程序',   ['管辖','程序规定','移送','集团犯罪','量刑程序','涉嫌犯罪单位','行政执法机关','公安机关']),
    ('审判监督',     ['冤假错案','申诉','文化大革命']),
    ('辩护与代理',   ['辩护人','在押犯罪嫌疑人']),
    ('未成年人刑事程序', ['未成年人刑事案件']),
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
    ('行政法规',       ['行政法规']),
]

_PROC_SUBGROUPS = [
    ('民事诉讼',       ['民事诉讼', '海事诉讼', '民事执行', '民事调解', '民事审判', '民事案件', '民事裁定', '民事诉讼证据']),
    ('刑事诉讼',       ['刑事诉讼', '死刑复核', '刑事再审', '刑事案件', '刑事裁定', '刑事诉讼证据', '刑事审判', '批捕', '逮捕', '羁押']),
    ('行政诉讼',       ['行政诉讼', '行政案件', '行政裁定', '行政赔偿', '国家赔偿', '行政执行', '行政诉讼证据', '行政复议']),
    ('律师、仲裁与公证', ['律师', '公证', '仲裁法', '法律援助', '仲裁委员会', '人民调解']),
    ('文书、送达与废止', ['送达', '文书', '废止', '司法协助', '法庭规则', '巡回法庭', '互联网法院', '国际商事法庭', '知识产权法庭']),
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
    '刑事': ['刑法及修正案', '侵犯财产', '经济犯罪', '贪污贿赂', '人身犯罪', '毒品与走私', '妨害社会管理秩序', '刑罚执行', '证据规则', '刑事诉讼程序', '审判监督', '辩护与代理', '未成年人刑事程序'],
    '行政与公法': ['行政法律', '教育科技', '卫生医药', '生态环境', '公安司法',
                   '社会民政', '土地城建', '自然资源', '劳动就业', '税务财政',
                   '国家赔偿', '司法解释'],
    '经济、税务与金融': ['税收与财政', '金融、证券与保险', '贸易、竞争与市场', '农业、资源与能源', '其他经济法规'],
    '劳动与社会保障': ['劳动就业', '社会保险与福利', '特殊群体保护', '司法解释', '行政法规'],
    '诉讼与司法程序': [
        '民事诉讼', '刑事诉讼', '行政诉讼', '律师、仲裁与公证',
        '文书、送达与废止', '行政法规',
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


def _prefixed(sub: str) -> str:
    """Add 行政法规/ prefix only if not already present"""
    if sub and not sub.startswith('行政法规/'):
        return f'行政法规/{sub}'
    return sub or '行政法规'

def _civil_subgroup(title: str, category: str, domain: str, subject_area: str) -> str:
    if domain == '民法典' or '民法典' in title:
        return '民法典'
    if category == '行政法规':
        return _prefixed(subject_area)
    for subgroup, kws in _CIVIL_SUBGROUPS:
        if kws and _match(title, kws):
            return subgroup
    return '综合与程序批复'


def _criminal_subgroup(title: str, category: str, subject_area: str) -> str:
    if category in ('法律', '修正案'):
        return '刑法及修正案'
    if category == '法律解释':
        return '刑法及修正案'
    if category == '行政法规':
        return _prefixed(subject_area)
    # 实体性刑法解释 → 刑法及修正案
    if _match(title, ['刑法修正案', '时间效力', '适用刑法', '适用修订刑法', '不再追诉', '罪名补充规定', '认真学习宣传贯彻', '罪名的补充规定']):
        return '刑法及修正案'
    for subgroup, kws in _CRIMINAL_SUBGROUPS[2:]:
        if kws and _match(title, kws):
            return subgroup
    return '检察院'


# 行政与公法中的法律 子分组（参照 subject_area 的分类逻辑）
_ADMIN_LAW_SUBGROUPS = [
    ('教育科技',       ['教育', '教师', '学位', '学校', '高等教育', '学前教育', '职业教育', '义务教育', '家庭教育', '爱国主义教育', '公共图书馆', '科学技术普及', '科学技术进步']),
    ('卫生医药',       ['卫生', '医疗', '医药', '药品', '食品安全', '传染病', '精神卫生', '疫苗', '献血', '母婴保健', '医师', '基本医疗卫生', '突发公共卫生', '红十字会', '动物防疫', '进出境动植物检疫', '农产品质量安全', '生物安全']),
    ('生态环境',       ['环境保护', '环境影响评价', '生态环境', '污染', '排污', '黑土地', '青藏高原', '长江保护', '黄河保护', '湿地保护', '海岛保护', '海洋环境', '水土保持', '野生动物', '森林法', '草原法', '水法', '国家公园', '核安全']),
    ('公安司法',       ['治安管理', '警察', '枪支', '禁毒', '监狱', '社区矫正', '国家安全', '保密', '居民身份证', '户口登记', '出入境', '护照', '集会游行示威', '网络安全', '数据安全', '密码法', '人民防空', '出境入境管理', '突发事件应对', '保守国家秘密', '律师法', '人民警察']),
    ('社会民政',       ['城市居民委员会', '村民委员会', '境外非政府组织', '归侨侨眷', '残疾人', '老年人', '未成年人', '体育法', '公共文化', '文物保护', '非物质文化遗产', '电影产业', '语言文字', '人口与计划生育', '无障碍环境']),
    ('信息通信',       ['个人信息保护', '网络安全', '数据安全', '密码法']),
    ('土地城建',       ['土地管理', '城乡规划', '房地产', '城市房地产', '测绘法']),
    ('自然资源',       ['气象法', '海域使用', '档案法', '水下文物']),
    ('劳动就业',       ['矿山安全', '特种设备', '安全生产', '危险化学品']),
    ('税务财政',       ['行政处罚', '行政许可', '行政强制', '行政复议', '国家赔偿', '公务员']),
]

def _admin_subgroup(title: str, category: str, subject_area: str) -> str:
    if category == '法律':
        for subgroup, kws in _ADMIN_LAW_SUBGROUPS:
            if _match(title, kws):
                return subgroup
        return '行政法律'
    if category == '行政法规':
        return _prefixed(subject_area)
    if '国家赔偿' in title or '行政赔偿' in title:
        return '国家赔偿'
    return '行政法律'


def _econ_subgroup(title: str, category: str, subject_area: str) -> str:
    if category == '行政法规':
        return _prefixed(subject_area)
    for subgroup, kws in _ECON_SUBGROUPS:
        if kws and _match(title, kws):
            return subgroup
    return '其他经济法规'


def _labor_subgroup(title: str, category: str, subject_area: str) -> str:
    if category == '行政法规':
        return _prefixed(subject_area)
    for subgroup, kws in _LABOR_SUBGROUPS[:3]:
        if _match(title, kws):
            return subgroup
    return '劳动就业'


def _proc_subgroup(title: str, category: str, subject_area: str) -> str:
    if category == '行政法规':
        if subject_area and not subject_area.startswith('行政法规/'):
            return f'行政法规/{subject_area}'
        return subject_area or '行政法规'
    for subgroup, kws in _PROC_SUBGROUPS:
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
        elif cat == '行政法规':       subgroup = _prefixed(subj)
        elif cat in ('司法解释', '法律解释'): subgroup = '司法解释'
        else:                         subgroup = '法律及决定'
    elif group == '民事与商事':
        subgroup = _civil_subgroup(title, cat, legal_domain or '', subj)
    elif group == '刑事':
        subgroup = _criminal_subgroup(title, cat, subj)
    elif group == '行政与公法':
        subgroup = _admin_subgroup(title, cat, subj)
    elif group == '经济、税务与金融':
        subgroup = _econ_subgroup(title, cat, subj)
    elif group == '劳动与社会保障':
        subgroup = _labor_subgroup(title, cat, subj)
    elif group == '诉讼与司法程序':
        subgroup = _proc_subgroup(title, cat, subj)
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
        """SELECT id, title, title_en, category, legal_domain, subject_area FROM laws
           WHERE is_current=1 AND (source='flk' OR (source='gongbao' AND legal_domain != ''))"""
    ).fetchall()

    tree: dict[str, dict[str, list[dict]]] = {}
    subject_updates: list[tuple[str, int]] = []  # (subgroup, law_id)
    for row in rows:
        law_id, title, title_en, category, legal_domain, subject_area = row
        group, subgroup = compute_display(title, category, legal_domain, subject_area)
        law_entry = {'id': law_id, 'title': title}
        if title_en:
            law_entry['title_en'] = title_en
        tree.setdefault(group, {}).setdefault(subgroup, []).append(law_entry)
        subject_updates.append((subgroup, law_id))

    # Write subject_area back to database
    conn.execute("UPDATE laws SET subject_area = NULL WHERE is_current = 1")
    conn.executemany("UPDATE laws SET subject_area = ? WHERE id = ? AND is_current = 1", subject_updates)
    conn.commit()

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
            'label_en': _GROUP_EN.get(group, group),
            'subgroups': [
                {'label': s, 'label_en': subgroup_label_en(s), 'laws': sorted(sub_map[s], key=lambda x: x['title'])}
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
    print(f'subject_area 已更新：{len(subject_updates)} 条记录')

    conn.close()


def run():
    print('\n=== 导出 law_menu.json ===')
    export_menu()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
