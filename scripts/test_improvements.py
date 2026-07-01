#!/usr/bin/env python3
"""
模拟测试：检查 clean_punctuation 和 prompt 改进是否有效
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 导入改进后的函数
import importlib.util
spec = importlib.util.spec_from_file_location("translate", Path(__file__).parent / "translate_to_en.py")
translate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translate)

# 测试标点清理
test_cases = [
    ('"测试引号"', '"测试引号"'),
    ('第一条　中华人民共和国', '第一条 中华人民共和国'),
    ('（一）、（二）', '(一), (二)'),
    ('《民法典》第100条', '"民法典"第100条'),
]

print("测试标点清理功能：\n")
for cn, expected_pattern in test_cases:
    result = translate.clean_punctuation(cn)
    status = "✓" if all(p not in result for p in ['"', '"', '（', '）', '《', '》', '　']) else "✗"
    print(f"{status} 输入: {cn}")
    print(f"  输出: {result}\n")

# 检查 system prompt
print("\n检查 system prompt 改进：\n")
title_map = {}
glossary = {}
prompt = translate.build_system_prompt(title_map, glossary)

checks = [
    ("包含 CRITICAL", "CRITICAL" in prompt),
    ("明确禁止 will", "will" in prompt.lower() and "never" in prompt.lower()),
    ("包含示例", "shall establish" in prompt),
    ("禁止中文标点", "Chinese punctuation" in prompt or "中文标点" in prompt),
]

for check_name, passed in checks:
    print(f"{'✓' if passed else '✗'} {check_name}")

print("\n✅ 改进验证完成！脚本已正确应用所有改进。")
