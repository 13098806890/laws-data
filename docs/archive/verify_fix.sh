#!/bin/bash
# 快速验证双语 Markdown 修复效果

echo "🔍 双语 Markdown 换行符修复验证"
echo "================================"
echo ""

# 1. 查看民法典第34条（典型的多段落条文）
echo "1️⃣  查看民法典第34条（4段落）："
echo "---"
grep -A 10 "第三十四条" "民事与商事/民法典/中华人民共和国民法典.md" | head -12
echo ""

# 2. 统计修复效果
echo "2️⃣  修复统计："
echo "---"
python3 -c "
import json
from pathlib import Path

fixed = 0
total = 0

for cat_dir in Path('json_en').iterdir():
    if not cat_dir.is_dir():
        continue
    for json_file in cat_dir.glob('*.json'):
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            for art in data.get('articles', []):
                en = art.get('content_en', '')
                if en.strip():
                    total += 1
                    if '\n' in en:
                        fixed += 1
        except:
            pass

print(f'已翻译条文：{total:,}')
print(f'包含换行符：{fixed:,} ({fixed/total*100:.1f}%)')
"
echo ""

# 3. 检查 Git 状态
echo "3️⃣  Git 状态："
echo "---"
git log --oneline -1
echo ""
git remote get-url origin
echo ""

# 4. 提示
echo "✅ 修复完成！"
echo ""
echo "📝 查看完整文档："
echo "   - BILINGUAL_NEWLINE_FIX_SUMMARY.md"
echo "   - VERIFICATION_GUIDE.md"
echo ""
echo "🌐 在线查看："
echo "   打开 GitHub 仓库，查看任意双语 Markdown 文件"
