#!/usr/bin/env python3
"""
从 display_group_map 导出 law_menu.json
格式：
{
  "name": "默认分类",
  "version": "YYYY-MM-DD",
  "groups": [
    {
      "label": "民事与商事",
      "subgroups": [
        { "label": "民法典", "lawIds": [101, 203, ...] },
        ...
      ]
    },
    ...
  ]
}

law_menu.json 是单一真相来源：
  - iOS 读它来渲染目录
  - db_to_md/renderer.py 读它来生成 Markdown 目录结构
"""

import json
import sqlite3
from datetime import date
from pathlib import Path

from config import DB_PATH, MENU_PATH

# 顶层分组顺序
_GROUP_ORDER = [
    '宪法与国家机构',
    '民事与商事',
    '刑事',
    '行政与公法',
    '经济、税务与金融',
    '劳动与社会保障',
    '诉讼与司法程序',
    '其他',
]

# 每个分组内 subgroup 的排列顺序（不含 行政法规/* 动态子项）
_SUBGROUP_ORDER: dict[str, list[str]] = {
    '宪法与国家机构': ['宪法', '法律及决定', '行政法规', '司法解释'],
    '民事与商事': [
        '民法典', '合同与债权', '公司与破产', '知识产权',
        '担保与物权', '婚姻、家庭与继承', '保险',
        '海事与运输', '外商与涉外', '证券与期货', '综合与程序批复',
    ],
    '刑事': ['刑法及修正案', '法律解释', '财产犯罪', '人身犯罪', '毒品与走私', '综合司法解释'],
    '行政与公法': ['行政法律', '国家赔偿', '司法解释'],  # 行政法规/* 动态追加
    '经济、税务与金融': ['税收与财政', '金融、证券与保险', '贸易、竞争与市场', '农业、资源与能源', '其他经济法规'],
    '劳动与社会保障': ['劳动就业', '社会保险与福利', '特殊群体保护', '司法解释', '行政法规'],
    '诉讼与司法程序': [
        '三大诉讼法', '律师、仲裁与公证', '民事程序解释',
        '刑事程序解释', '行政程序解释', '文书、送达与废止', '行政法规',
    ],
}

# 行政法规 主题顺序（适用于 subgroup = '行政法规/XX' 的 XX 部分）
_ADMIN_SUBJECT_ORDER = [
    '税务财政', '海关进出口', '金融证券',
    '交通运输', '能源电力',
    '生态环境', '自然资源', '土地城建',
    '农业农村', '卫生医药', '劳动就业', '社会民政',
    '教育科技', '信息通信',
    '工商市场', '安全应急',
    '公安司法', '军事国防',
    '行政法制', '涉外外资',
]


def _sort_subgroups(group: str, subgroups: list[str]) -> list[str]:
    """对某 group 下的 subgroup 列表排序。"""
    order = _SUBGROUP_ORDER.get(group, [])
    # 固定顺序部分
    known = [s for s in order if s in subgroups]
    # 行政法规/* 动态部分，按 _ADMIN_SUBJECT_ORDER 排
    admin = [s for s in subgroups if s.startswith('行政法规/')]
    admin_topics = [s[len('行政法规/'):] for s in admin]
    sorted_topics = (
        [t for t in _ADMIN_SUBJECT_ORDER if t in admin_topics]
        + sorted(t for t in admin_topics if t not in _ADMIN_SUBJECT_ORDER)
    )
    known_admin = [f'行政法规/{t}' for t in sorted_topics]
    # 其余未知的
    extra = sorted(s for s in subgroups if s not in known and s not in admin)
    return known + known_admin + extra


def export_menu(db_path: Path = DB_PATH, menu_path: Path = MENU_PATH):
    conn = sqlite3.connect(db_path)

    rows = conn.execute("""
        SELECT dgm.display_group, dgm.display_subgroup, dgm.law_id, l.title
        FROM display_group_map dgm
        JOIN laws l ON dgm.law_id = l.id
        WHERE l.is_current = 1
        ORDER BY dgm.display_group, dgm.display_subgroup, l.title
    """).fetchall()
    conn.close()

    # 聚合：group → subgroup → [(law_id, title)]
    tree: dict[str, dict[str, list[dict]]] = {}
    for group, subgroup, law_id, title in rows:
        g = group or '其他'
        s = subgroup or '（全部）'
        tree.setdefault(g, {}).setdefault(s, []).append({'id': law_id, 'title': title})

    # 按顺序组装
    groups_out = []
    sorted_groups = (
        [g for g in _GROUP_ORDER if g in tree]
        + sorted(g for g in tree if g not in _GROUP_ORDER)
    )
    for group in sorted_groups:
        sub_map = tree[group]
        sorted_subs = _sort_subgroups(group, list(sub_map.keys()))
        subgroups_out = [
            {'label': s, 'laws': tree[group][s]}
            for s in sorted_subs
        ]
        groups_out.append({'label': group, 'subgroups': subgroups_out})

    menu = {
        'name': '默认分类',
        'version': date.today().isoformat(),
        'groups': groups_out,
    }

    menu_path.write_text(
        json.dumps(menu, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    total = sum(len(s['laws']) for g in groups_out for s in g['subgroups'])
    print(f'law_menu.json 导出完成：{len(groups_out)} 个分组，{total} 部法律')
    print(f'路径：{menu_path}')


def run():
    print('\n=== 导出 law_menu.json ===')
    export_menu()


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    run()
