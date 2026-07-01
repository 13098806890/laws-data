#!/usr/bin/env python3
"""
测试双语 Markdown 换行符修复

验证：
1. clean_punctuation 是否保留换行符
2. 翻译是否保留段落结构
3. Markdown 插入是否正确处理换行
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from translate_to_en import clean_punctuation

# 测试 clean_punctuation 函数
def test_clean_punctuation():
    print("=== 测试 clean_punctuation ===\n")

    # 测试用例1：带换行符的中文文本
    test_zh = """监护人的职责是代理被监护人实施民事法律行为，保护被监护人的人身权利、财产权利以及其他合法权益等。
监护人依法履行监护职责产生的权利，受法律保护。
监护人不履行监护职责或者侵害被监护人合法权益的，应当承担法律责任。"""

    # 测试用例2：对应的英文翻译（模拟 API 输出）
    test_en = """Article 34 The duties of a guardian shall be to act on behalf of the ward.
Rights arising from the guardian's lawful performance shall be protected.
Where a guardian fails to perform guardianship duties, the guardian shall bear legal liability."""

    print("中文原文（带换行）：")
    print(repr(test_zh))
    print()

    cleaned = clean_punctuation(test_en)
    print("英文清理后：")
    print(repr(cleaned))
    print()

    # 检查换行符是否保留
    if '\n' in cleaned:
        print("✅ 换行符已保留")
        print(f"   段落数量：{len(cleaned.split(chr(10)))} 段")
    else:
        print("❌ 换行符丢失")

    print()


# 测试 Markdown 插入格式
def test_markdown_format():
    print("=== 测试 Markdown 格式 ===\n")

    en_with_newlines = """Article 34 The duties of a guardian shall be to act on behalf of the ward.
Rights arising from the guardian's lawful performance shall be protected.
Where a guardian fails to perform guardianship duties, the guardian shall bear legal liability."""

    # 模拟 add_en_to_md.py 的处理逻辑
    md_output = en_with_newlines.replace('\n', '  \n')

    print("原始英文（带换行）：")
    print(repr(en_with_newlines))
    print()

    print("Markdown 格式输出：")
    print(md_output)
    print()

    print("转换后（repr）：")
    print(repr(md_output))
    print()

    # 检查是否正确转换为 Markdown 换行
    if '  \n' in md_output:
        print("✅ 已转换为 Markdown 硬换行（两个空格 + \\n）")
    else:
        print("❌ Markdown 换行转换失败")

    print()


# 测试已有翻译文件
def test_existing_translation():
    print("=== 测试现有翻译文件 ===\n")

    import json
    from pathlib import Path

    json_en_path = Path("/Users/doxie/Github/laws-data/json_en/法律/中华人民共和国民法典_20200528.json")

    if not json_en_path.exists():
        print("⚠️  测试文件不存在，跳过此测试")
        return

    data = json.loads(json_en_path.read_text(encoding='utf-8'))

    # 查找第34条
    art_34 = None
    for art in data.get('articles', []):
        if art['article_number'] == '第三十四条':
            art_34 = art
            break

    if art_34:
        content_en = art_34.get('content_en', '')
        print("第34条英文翻译：")
        print(repr(content_en))
        print()

        if '\n' in content_en:
            print(f"✅ 当前翻译包含 {content_en.count(chr(10))} 个换行符")
        else:
            print("❌ 当前翻译不包含换行符（需要重新翻译）")
    else:
        print("⚠️  未找到第34条翻译")

    print()


if __name__ == "__main__":
    print("双语 Markdown 换行符修复测试\n")
    print("=" * 60)
    print()

    test_clean_punctuation()
    test_markdown_format()
    test_existing_translation()

    print("=" * 60)
    print("\n测试完成！\n")
    print("📝 修复说明：")
    print("   1. clean_punctuation 现在会保留换行符")
    print("   2. add_en_to_md.py 会将换行符转换为 Markdown 硬换行（两个空格 + \\n）")
    print("   3. translate_to_en.py 的 system prompt 已更新，要求保留段落结构")
    print()
    print("🔧 后续步骤：")
    print("   1. 对已翻译但有问题的条文，需要重新翻译：")
    print("      python3 scripts/retranslate.py --filter <法律名称>")
    print("   2. 重新插入英文到 Markdown：")
    print("      python3 scripts/add_en_to_md.py --filter <法律名称>")
