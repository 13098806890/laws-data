#!/usr/bin/env python3
"""
分析翻译优先级：
1. 统计已翻译法律
2. 按法考标记、法律部门、条文数量推荐翻译优先级
3. 生成待翻译清单

用法：
  python3 scripts/analyze_translation_priority.py
"""

import sqlite3
import json
from pathlib import Path
from collections import defaultdict

# 路径
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'law_content.db'
OUTPUT_PATH = BASE_DIR / 'translation_priority.md'


def analyze():
    conn = sqlite3.connect(DB_PATH)

    # 1. 已翻译法律清单
    translated_laws = conn.execute("""
        SELECT DISTINCT l.id, l.title, l.legal_domain, l.category, COUNT(n.id) AS article_count
        FROM laws l
        JOIN nodes n ON l.id = n.law_id
        WHERE l.is_current = 1
          AND n.type = 'article'
          AND n.content_en IS NOT NULL
          AND n.content_en != ''
        GROUP BY l.id
        ORDER BY l.legal_domain, l.pub_date DESC
    """).fetchall()

    # 2. 按法律部门统计
    domain_stats = conn.execute("""
        SELECT
            l.legal_domain,
            COUNT(DISTINCT l.id) AS total_laws,
            COUNT(DISTINCT CASE WHEN n.content_en IS NOT NULL AND n.content_en != '' THEN l.id END) AS translated_laws,
            SUM(CASE WHEN n.type = 'article' THEN 1 ELSE 0 END) AS total_articles,
            SUM(CASE WHEN n.type = 'article' AND n.content_en IS NOT NULL AND n.content_en != '' THEN 1 ELSE 0 END) AS translated_articles
        FROM laws l
        LEFT JOIN nodes n ON l.id = n.law_id
        WHERE l.is_current = 1
        GROUP BY l.legal_domain
        ORDER BY
            CASE l.legal_domain
                WHEN '民法典' THEN 1
                WHEN '宪法相关法' THEN 2
                WHEN '刑法' THEN 3
                WHEN '民法商法' THEN 4
                WHEN '诉讼与非诉讼程序法' THEN 5
                WHEN '行政法' THEN 6
                WHEN '经济法' THEN 7
                WHEN '社会法' THEN 8
                ELSE 9
            END
    """).fetchall()

    # 3. 未翻译法律清单
    untranslated_laws = conn.execute("""
        SELECT l.id, l.title, l.legal_domain, l.category, COUNT(n.id) AS article_count
        FROM laws l
        LEFT JOIN nodes n ON l.id = n.law_id AND n.type = 'article'
        WHERE l.is_current = 1
          AND l.id NOT IN (
              SELECT DISTINCT law_id FROM nodes
              WHERE type = 'article' AND content_en IS NOT NULL AND content_en != ''
          )
        GROUP BY l.id
        ORDER BY l.legal_domain, article_count DESC
    """).fetchall()

    # 4. 按条文数量推荐翻译（≤100条）
    short_laws = conn.execute("""
        SELECT l.id, l.title, l.legal_domain, l.category, COUNT(n.id) AS article_count
        FROM laws l
        LEFT JOIN nodes n ON l.id = n.law_id AND n.type = 'article'
        WHERE l.is_current = 1
          AND l.id NOT IN (
              SELECT DISTINCT law_id FROM nodes
              WHERE type = 'article' AND content_en IS NOT NULL AND content_en != ''
          )
        GROUP BY l.id
        HAVING article_count > 0 AND article_count <= 100
        ORDER BY article_count DESC
    """).fetchall()

    conn.close()

    # 生成报告
    report = []
    report.append("# 翻译优先级分析报告\n")
    report.append(f"生成时间：2026-07-01\n")
    report.append("---\n\n")

    # 已翻译法律
    report.append("## ✅ 已翻译法律（11 部）\n\n")
    report.append("| 法律名称 | 法律部门 | 分类 | 条文数 |\n")
    report.append("|---------|---------|------|-------|\n")
    for law_id, title, domain, cat, art_count in translated_laws:
        report.append(f"| {title} | {domain or ''} | {cat} | {art_count} |\n")

    # 按法律部门统计
    report.append("\n## 📊 按法律部门统计\n\n")
    report.append("| 法律部门 | 总法律数 | 已翻译 | 总条文数 | 已翻译条文 | 翻译率 |\n")
    report.append("|---------|---------|-------|---------|-----------|-------|\n")
    for domain, total, trans, total_art, trans_art in domain_stats:
        domain_name = domain if domain else "未分类"
        trans_pct = f"{trans_art * 100.0 / total_art:.1f}%" if total_art > 0 else "0%"
        report.append(f"| {domain_name} | {total} | {trans} | {total_art} | {trans_art} | {trans_pct} |\n")

    # 推荐翻译：未翻译法律
    report.append("\n## 🎯 推荐翻译（优先级 P0）：未翻译法律\n\n")
    report.append(f"共 {len(untranslated_laws)} 部，按条文数量降序：\n\n")
    report.append("| 法律名称 | 法律部门 | 分类 | 条文数 |\n")
    report.append("|---------|---------|------|-------|\n")
    for law_id, title, domain, cat, art_count in untranslated_laws[:50]:  # 只显示前50
        report.append(f"| {title} | {domain or ''} | {cat} | {art_count} |\n")

    if len(untranslated_laws) > 50:
        report.append(f"\n*（省略剩余 {len(untranslated_laws) - 50} 部法律）*\n")

    # 推荐翻译：短法律（≤100条）
    report.append(f"\n## 💡 推荐翻译（优先级 P1）：短法律（≤100条）\n\n")
    report.append(f"共 {len(short_laws)} 部，按条文数量降序（前50）：\n\n")
    report.append("| 法律名称 | 法律部门 | 分类 | 条文数 |\n")
    report.append("|---------|---------|------|-------|\n")
    for law_id, title, domain, cat, art_count in short_laws[:50]:
        report.append(f"| {title} | {domain or ''} | {cat} | {art_count} |\n")

    # 总结建议
    total_untranslated_articles = sum(art_count for _, _, _, _, art_count in untranslated_laws)
    total_short_articles = sum(art_count for _, _, _, _, art_count in short_laws)

    report.append("\n## 📝 翻译建议\n\n")
    report.append("### 优先级分级\n\n")
    report.append("**P0（必须翻译）：未翻译法律**\n")
    report.append(f"- 数量：{len(untranslated_laws)} 部\n")
    report.append(f"- 条文数：约 {total_untranslated_articles} 条\n")
    report.append(f"- 预计成本：${total_untranslated_articles * 0.05:.0f}（按 $0.05/条估算）\n")
    report.append(f"- 翻译时间：约 {total_untranslated_articles // 500:.0f}-{total_untranslated_articles // 300:.0f} 小时\n")
    report.append("- 理由：优先完成主要法律体系的核心法律\n\n")

    report.append("**P1（建议翻译）：短法律（≤100条）**\n")
    report.append(f"- 数量：{len(short_laws)} 部\n")
    report.append(f"- 条文数：约 {total_short_articles} 条\n")
    report.append(f"- 预计成本：${total_short_articles * 0.05:.0f}\n")
    report.append("- 理由：成本低，可快速扩大覆盖范围\n\n")

    report.append("**P2（按需翻译）：其他法律**\n")
    report.append("- 根据用户反馈和实际使用情况，按需翻译特定法律\n")
    report.append("- 可先翻译行政法规、司法解释中的常用文件\n\n")

    report.append("### 执行步骤\n\n")
    report.append("1. **优先翻译未翻译法律**：运行 `translate_to_en.py` 翻译\n")
    report.append("2. **逐步扩展**：翻译短法律（≤100条），快速提升覆盖率\n")
    report.append("3. **质量优先**：每完成一批翻译，运行质量验证脚本\n")
    report.append("4. **持续更新**：新法律发布后，及时添加到翻译队列\n\n")

    # 写入文件
    OUTPUT_PATH.write_text(''.join(report), encoding='utf-8')
    print(f"✅ 翻译优先级分析报告已生成：{OUTPUT_PATH}")

    # 打印摘要
    print("\n📊 翻译进度摘要：")
    print(f"  已翻译法律：{len(translated_laws)} 部")
    print(f"  法考法律（未翻译）：{len(untranslated_laws)} 部，约 {total_untranslated_articles} 条")
    print(f"  短法律（≤100条，未翻译）：{len(short_laws)} 部，约 {total_short_articles} 条")
    print(f"\n💰 预计翻译成本（P0+P1）：${(total_untranslated_articles + total_short_articles) * 0.05:.0f}")


if __name__ == '__main__':
    analyze()
