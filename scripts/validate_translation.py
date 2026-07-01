#!/usr/bin/env python3
"""
自动校验英文翻译质量。

检查项：
1. 术语一致性：关键法律术语是否与 glossary 一致
2. 跨法引用：《xxx》引用是否与 title_map 一致
3. 法律文本风格：shall/may/must 的使用
4. 条文引用格式：第X条、第X款等的翻译
5. 数字和标点：中文标点是否清理干净
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR

JSON_EN_DIR = JSON_DIR.parent / 'json_en'
REFERENCES_DIR = JSON_DIR.parent / 'references'
TITLE_MAP_PATH = REFERENCES_DIR / 'law_title_en_map.json'
GLOSSARY_PATH = REFERENCES_DIR / 'legal_terms_glossary.json'


class TranslationValidator:
    def __init__(self):
        self.title_map = self.load_json(TITLE_MAP_PATH)
        self.glossary = self.load_json(GLOSSARY_PATH)
        self.issues = []

    @staticmethod
    def load_json(path):
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))
        return {}

    def check_terminology(self, content_en: str, art_num: str, law_title: str):
        """检查术语一致性"""
        issues = []

        # 关键术语检查
        key_terms = {
            '人民法院': 'People\'s Court',
            '人民检察院': 'People\'s Procuratorate',
            '最高人民法院': 'Supreme People\'s Court',
            '最高人民检察院': 'Supreme People\'s Procuratorate',
            '国务院': 'State Council',
        }

        for zh, en_expected in key_terms.items():
            if zh in content_en:  # 不应该出现中文
                issues.append({
                    'type': 'terminology',
                    'severity': 'high',
                    'law': law_title,
                    'article': art_num,
                    'issue': f'包含未翻译的中文术语: {zh}',
                })

        # 检查常见的错误翻译
        wrong_patterns = [
            (r'people court', 'People\'s Court'),  # 缺少所有格
            (r'people procuratorate', 'People\'s Procuratorate'),
            (r'Civil Code of the People\'s Republic of China', 'Civil Code'),  # 应简化
        ]

        for pattern, correct in wrong_patterns:
            if re.search(pattern, content_en, re.IGNORECASE):
                issues.append({
                    'type': 'terminology',
                    'severity': 'medium',
                    'law': law_title,
                    'article': art_num,
                    'issue': f'术语可能不规范，应使用: {correct}',
                })

        return issues

    def check_law_references(self, content_en: str, art_num: str, law_title: str):
        """检查跨法引用"""
        issues = []

        # 检查是否有未翻译的书名号
        if '《' in content_en or '》' in content_en:
            issues.append({
                'type': 'reference',
                'severity': 'high',
                'law': law_title,
                'article': art_num,
                'issue': '包含未翻译的书名号《》',
            })

        # 检查常见法律名称是否一致
        common_laws = {
            'Criminal Law': ['刑法', 'criminal law'],
            'Civil Code': ['民法典', 'civil code'],
            'Civil Procedure Law': ['民事诉讼法'],
        }

        # 提取英文法律引用
        law_refs = re.findall(r'(?:the\s+)?([A-Z][A-Za-z\s]+(?:Law|Code|Regulation))', content_en)
        for ref in law_refs:
            ref_normalized = ref.strip()
            # 检查是否在常见法律列表中
            found = False
            for standard_name, variants in common_laws.items():
                if ref_normalized.lower() in [v.lower() for v in variants]:
                    if ref_normalized != standard_name:
                        issues.append({
                            'type': 'reference',
                            'severity': 'low',
                            'law': law_title,
                            'article': art_num,
                            'issue': f'法律引用不一致: "{ref_normalized}" 应为 "{standard_name}"',
                        })
                    found = True
                    break

        return issues

    def check_legal_style(self, content_en: str, art_num: str, law_title: str):
        """检查法律文本风格"""
        issues = []

        # 检查是否使用了法律助动词
        has_shall = 'shall' in content_en.lower()
        has_may = 'may' in content_en.lower()
        has_must = 'must' in content_en.lower()

        # 如果条文较长但没有使用法律助动词，可能有问题
        if len(content_en) > 100 and not (has_shall or has_may or has_must):
            issues.append({
                'type': 'style',
                'severity': 'low',
                'law': law_title,
                'article': art_num,
                'issue': '较长条文但未使用法律助动词（shall/may/must），请检查',
            })

        # 检查是否错误使用了 will/would
        if re.search(r'\bwill\b', content_en, re.IGNORECASE) or re.search(r'\bwould\b', content_en, re.IGNORECASE):
            issues.append({
                'type': 'style',
                'severity': 'medium',
                'law': law_title,
                'article': art_num,
                'issue': '使用了 will/would，法律英语应使用 shall/may',
            })

        return issues

    def check_article_references(self, content_en: str, art_num: str, law_title: str):
        """检查条文引用格式"""
        issues = []

        # 检查是否有中文条文引用
        cn_refs = [
            r'第[一二三四五六七八九十百千\d]+条',
            r'第[一二三四五六七八九十\d]+款',
            r'第[一二三四五六七八九十\d]+项',
        ]

        for pattern in cn_refs:
            if re.search(pattern, content_en):
                issues.append({
                    'type': 'format',
                    'severity': 'high',
                    'law': law_title,
                    'article': art_num,
                    'issue': f'包含未翻译的中文条文引用: {pattern}',
                })

        # 检查英文条文引用格式
        # 应该是 "Article X" 而不是 "article X" 或 "Art. X"
        wrong_article_refs = re.findall(r'\barticle\s+\d+', content_en)
        if wrong_article_refs:
            issues.append({
                'type': 'format',
                'severity': 'low',
                'law': law_title,
                'article': art_num,
                'issue': f'条文引用格式不规范: "{wrong_article_refs[0]}" 应为 "Article X"（大写）',
            })

        return issues

    def check_punctuation(self, content_en: str, art_num: str, law_title: str):
        """检查标点符号"""
        issues = []

        # 检查中文标点
        cn_punctuations = ['，', '。', '；', '：', '、', '（', '）', '！', '？', '"', '"']
        for punct in cn_punctuations:
            if punct in content_en:
                issues.append({
                    'type': 'punctuation',
                    'severity': 'high',
                    'law': law_title,
                    'article': art_num,
                    'issue': f'包含中文标点: {punct}',
                })

        # 检查中文空格（全角空格）
        if '　' in content_en:
            issues.append({
                'type': 'punctuation',
                'severity': 'medium',
                'law': law_title,
                'article': art_num,
                'issue': '包含全角空格',
            })

        return issues

    def validate_law(self, filename: str, category: str) -> dict:
        """验证一部法律的所有条文"""
        en_path = JSON_EN_DIR / category / f'{filename}.json'
        if not en_path.exists():
            return {'error': 'File not found'}

        try:
            en_data = json.loads(en_path.read_text(encoding='utf-8'))
        except:
            return {'error': 'Invalid JSON'}

        law_title = en_data.get('title_en', filename)
        articles = en_data.get('articles', [])

        law_issues = []
        for art in articles:
            art_num = art.get('article_number', '')
            content_en = art.get('content_en', '').strip()

            if not content_en:
                continue

            # 运行所有检查
            law_issues.extend(self.check_terminology(content_en, art_num, law_title))
            law_issues.extend(self.check_law_references(content_en, art_num, law_title))
            law_issues.extend(self.check_legal_style(content_en, art_num, law_title))
            law_issues.extend(self.check_article_references(content_en, art_num, law_title))
            law_issues.extend(self.check_punctuation(content_en, art_num, law_title))

        return {
            'law': law_title,
            'articles_count': len([a for a in articles if a.get('content_en', '').strip()]),
            'issues': law_issues,
        }


def main():
    import sqlite3
    from config import DB_PATH

    validator = TranslationValidator()

    # 获取已翻译的法律列表
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)  # 只读模式
    rows = conn.execute(
        "SELECT filename, category, title FROM laws WHERE is_current=1"
    ).fetchall()
    conn.close()

    results = []
    total_articles = 0
    total_issues = 0

    print("开始验证翻译质量...\n")

    for filename, category, title in rows:
        en_path = JSON_EN_DIR / category / f'{filename}.json'
        if not en_path.exists():
            continue

        # 检查是否有英文内容
        try:
            en_data = json.loads(en_path.read_text(encoding='utf-8'))
            articles = en_data.get('articles', [])
            has_en = any(a.get('content_en', '').strip() for a in articles)
            if not has_en:
                continue
        except:
            continue

        result = validator.validate_law(filename, category)
        if 'error' not in result:
            results.append(result)
            total_articles += result['articles_count']
            total_issues += len(result['issues'])

            if result['issues']:
                print(f"📋 {result['law']}")
                print(f"   已翻译: {result['articles_count']} 条")
                print(f"   发现问题: {len(result['issues'])} 个\n")

    # 生成报告
    report_path = JSON_EN_DIR.parent / 'translation_validation_report.md'

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 英文翻译质量验证报告\n\n")
        f.write(f"**验证时间**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**统计信息**:\n")
        f.write(f"- 已验证法律: {len(results)} 部\n")
        f.write(f"- 已翻译条文: {total_articles} 条\n")
        f.write(f"- 发现问题: {total_issues} 个\n\n")

        # 按严重程度分类
        by_severity = defaultdict(list)
        for result in results:
            for issue in result['issues']:
                by_severity[issue['severity']].append(issue)

        f.write("## 问题统计\n\n")
        f.write(f"- 🔴 高严重度: {len(by_severity['high'])} 个\n")
        f.write(f"- 🟡 中严重度: {len(by_severity['medium'])} 个\n")
        f.write(f"- 🟢 低严重度: {len(by_severity['low'])} 个\n\n")

        # 按类型分类
        by_type = defaultdict(list)
        for result in results:
            for issue in result['issues']:
                by_type[issue['type']].append(issue)

        f.write("## 问题分类\n\n")
        type_names = {
            'terminology': '术语一致性',
            'reference': '跨法引用',
            'style': '法律文本风格',
            'format': '条文引用格式',
            'punctuation': '标点符号',
        }
        for issue_type, issues in sorted(by_type.items()):
            f.write(f"- {type_names.get(issue_type, issue_type)}: {len(issues)} 个\n")

        f.write("\n---\n\n")

        # 详细问题列表
        f.write("## 详细问题列表\n\n")

        for severity in ['high', 'medium', 'low']:
            issues = by_severity[severity]
            if not issues:
                continue

            severity_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
            f.write(f"### {severity_emoji[severity]} {severity.upper()} 严重度问题\n\n")

            for issue in issues:
                f.write(f"**{issue['law']} - {issue['article']}**\n")
                f.write(f"- 类型: {type_names.get(issue['type'], issue['type'])}\n")
                f.write(f"- 问题: {issue['issue']}\n\n")

        f.write("\n---\n\n")

        # 无问题的法律
        clean_laws = [r for r in results if not r['issues']]
        if clean_laws:
            f.write("## ✅ 无问题的法律\n\n")
            for result in clean_laws:
                f.write(f"- {result['law']} ({result['articles_count']} 条)\n")

    print(f"\n✅ 验证完成！")
    print(f"\n统计:")
    print(f"  - 已验证法律: {len(results)} 部")
    print(f"  - 已翻译条文: {total_articles} 条")
    print(f"  - 发现问题: {total_issues} 个")
    print(f"    - 高严重度: {len(by_severity['high'])} 个")
    print(f"    - 中严重度: {len(by_severity['medium'])} 个")
    print(f"    - 低严重度: {len(by_severity['low'])} 个")
    print(f"\n详细报告已生成: {report_path}")


if __name__ == "__main__":
    main()
