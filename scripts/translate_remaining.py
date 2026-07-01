#!/usr/bin/env python3
"""
只翻译未完成的6部法律，使用更保守的参数
- batch_size 从 20 降到 10（减少API失败概率）
- workers 从 4 降到 2（减少并发压力）
"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 设置环境变量
os.environ['DEEPSEEK_API_KEY'] = 'sk-bbeb5679bd004552b6bd304906065d5f'

# 只翻译未完成的6部法律
TARGET_LAWS = [
    ("民法典", 20),                              # 还剩20条
    ("婚姻家庭编的解释（一）", 20),              # 还剩20条
    ("总则编若干问题的解释", 20),               # 还剩20条
    ("侵权责任编的解释（一）", 20),             # 还剩20条
    ("担保制度的解释", 60),                      # 还剩60条
    ("合同编通则若干问题的解释", 60),           # 还剩60条
]

print("=" * 70)
print("继续翻译未完成的6部法律（使用保守参数）")
print("参数：batch_size=10, workers=2")
print("=" * 70 + "\n")

for i, (law, remaining) in enumerate(TARGET_LAWS, 1):
    print(f"  {i}. {law:35} (还剩{remaining:2}条)")

print("\n" + "=" * 70)
print("开始翻译...")
print("=" * 70 + "\n")

# 逐个翻译
for i, (law, remaining) in enumerate(TARGET_LAWS, 1):
    print(f"\n{'='*70}")
    print(f"[{i}/{len(TARGET_LAWS)}] 正在翻译: {law} (还剩{remaining}条)")
    print(f"{'='*70}\n")

    # 使用更保守的参数
    cmd = f'python3 scripts/translate_to_en.py --filter "{law}" --batch-size 10 --workers 2'
    exit_code = os.system(cmd)

    if exit_code != 0:
        print(f"\n⚠️  翻译出错，退出码：{exit_code}")
        print(f"继续下一个法律...")
    else:
        print(f"\n✅ {law} 翻译完成")

print("\n" + "=" * 70)
print("✅ 批量翻译完成！")
print("=" * 70)
