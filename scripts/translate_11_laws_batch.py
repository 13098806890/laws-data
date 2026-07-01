#!/usr/bin/env python3
"""
用优化后的脚本重新翻译11部法律
使用 DeepSeek API
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 设置环境变量
os.environ['DEEPSEEK_API_KEY'] = 'sk-bbeb5679bd004552b6bd304906065d5f'

# 11部法律的精确文件名（去掉日期后缀匹配）
TARGET_LAWS = [
    "中华人民共和国民法典",
    "破坏公用电信设施刑事案件",
    "婚姻家庭编的解释（一）",
    "民法典》时间效力",
    "物权编的解释（一）",
    "继承编的解释（一）",
    "担保制度的解释",
    "总则编若干问题的解释",
    "合同编通则若干问题的解释",
    "侵权责任编的解释（一）",
    "婚姻家庭编的解释（二）",
]

print("=" * 70)
print("用优化后的脚本重新翻译11部法律")
print("=" * 70)
print("\n目标法律：\n")
for i, law in enumerate(TARGET_LAWS, 1):
    print(f"  {i:2d}. {law}")

print("\n" + "=" * 70)
print("开始翻译...")
print("=" * 70 + "\n")

# 逐个翻译
for i, law in enumerate(TARGET_LAWS, 1):
    print(f"\n{'='*70}")
    print(f"[{i}/{len(TARGET_LAWS)}] 正在翻译: {law}")
    print(f"{'='*70}\n")

    # 执行翻译
    cmd = f'python3 scripts/translate_to_en.py --filter "{law}" --batch-size 20 --workers 4'
    exit_code = os.system(cmd)

    if exit_code != 0:
        print(f"\n⚠️  翻译出错，退出码：{exit_code}")
        response = input("继续下一个？(y/n): ")
        if response.lower() != 'y':
            print("用户中止")
            sys.exit(1)
    else:
        print(f"\n✅ {law} 翻译完成")

print("\n" + "=" * 70)
print("✅ 全部完成！")
print("=" * 70)
