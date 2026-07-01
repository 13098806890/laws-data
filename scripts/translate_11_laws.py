#!/usr/bin/env python3
"""
只翻译指定的11部法律（已清空的那些）
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 设置环境变量
os.environ['DEEPSEEK_API_KEY'] = 'sk-a1a85b320b8946439487d41d1e2c95cd'

# 要翻译的11部法律（标题关键词）
TARGET_LAWS = [
    "中华人民共和国民法典_20200528",
    "破坏公用电信设施",
    "婚姻家庭编的解释（一）_20201229",
    "时间效力的若干规定",
    "物权编的解释（一）",
    "继承编的解释（一）",
    "担保制度的解释",
    "总则编若干问题的解释",
    "合同编通则若干问题的解释",
    "侵权责任编的解释（一）",
    "婚姻家庭编的解释（二）",
]

print("准备翻译以下11部法律：\n")
for i, law in enumerate(TARGET_LAWS, 1):
    print(f"  {i}. {law}")

print("\n开始翻译...\n")

# 逐个翻译
for law in TARGET_LAWS:
    print(f"{'='*60}")
    print(f"正在翻译: {law}")
    print(f"{'='*60}")
    os.system(f'python3 scripts/translate_to_en.py --filter "{law}"')
    print()

print("\n✅ 全部完成！")
