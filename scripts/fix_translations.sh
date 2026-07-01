#!/bin/bash
# 一键修复已翻译法律的质量问题
#
# 功能：
# 1. 清空已有翻译
# 2. 使用改进后的脚本重新翻译
# 3. 验证新翻译的质量
# 4. 更新 Markdown 双语展示
#
# 用法：
#   export ANTHROPIC_API_KEY=sk-ant-...  或  export DEEPSEEK_API_KEY=sk-...
#   bash scripts/fix_translations.sh

set -e  # 遇到错误立即退出

echo "========================================="
echo "  修复已翻译法律的质量问题"
echo "========================================="
echo ""

# 检查 API 密钥
if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "错误：请设置 ANTHROPIC_API_KEY 或 DEEPSEEK_API_KEY"
    exit 1
fi

if [ -n "$DEEPSEEK_API_KEY" ]; then
    echo "✓ 使用 DeepSeek API"
else
    echo "✓ 使用 Anthropic API"
fi

echo ""
echo "步骤 1/4: 预览待重新翻译的法律"
echo "-------------------------------------"
python3 scripts/retranslate.py --dry-run
echo ""

echo "⚠️  警告：即将清空 11 部法律的英文翻译并重新翻译"
echo "预计时间：10-20 分钟"
echo "预计成本：\$2-5 (DeepSeek) 或 \$5-10 (Anthropic)"
echo ""
read -p "输入 'yes' 确认继续: " confirmation

if [ "$confirmation" != "yes" ]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "步骤 2/4: 清空已有翻译"
echo "-------------------------------------"
echo "yes" | python3 scripts/retranslate.py

echo ""
echo "步骤 3/4: 重新翻译（这可能需要10-20分钟）"
echo "-------------------------------------"
# 翻译所有已清空的法律
python3 scripts/translate_to_en.py

echo ""
echo "步骤 4/4: 验证新翻译的质量"
echo "-------------------------------------"
python3 scripts/validate_translation.py

echo ""
echo "步骤 5/4: 更新 Markdown 双语展示"
echo "-------------------------------------"
python3 scripts/add_en_to_md.py

echo ""
echo "========================================="
echo "  ✅ 完成！"
echo "========================================="
echo ""
echo "检查验证报告："
echo "  - translation_validation_report.md"
echo "  - translation_quality_summary.md"
echo ""
echo "下一步："
echo "  git add -A"
echo "  git commit -m 'fix: 修复翻译质量问题（标点+will/would）'"
echo "  git push origin main"
