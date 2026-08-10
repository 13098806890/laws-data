# 翻译脚本改进总结

## 📝 改进内容（2026-07-01）

### 1. ✅ 增强 System Prompt

**原有 Prompt**：
```
Rules:
- Use 'shall' for obligations, 'may' for permissions, 'must' for requirements
```

**改进后 Prompt**：
```
CRITICAL - Legal Language Rules:
- Use 'shall' for obligations and requirements (NEVER use 'will')
- Use 'may' for permissions and rights (NEVER use 'would')
- Use 'must' for absolute requirements
- NEVER use 'will' or 'would' - these are FORBIDDEN in legal English

Additional Rules:
- Use only English punctuation (NEVER use Chinese punctuation like " " ， 。)

Examples of CORRECT usage:
- ✓ 'shall establish' (NOT 'will establish')
- ✓ 'may appoint' (NOT 'can appoint' or 'would appoint')
```

**改进点**：
- 明确禁止 `will`/`would`，使用大写 CRITICAL 和 NEVER 强调
- 添加具体示例（正确 vs 错误）
- 明确禁止中文标点

---

### 2. ✅ 添加自动标点清理

新增 `clean_punctuation()` 函数：

```python
def clean_punctuation(text: str) -> str:
    """清理中文标点符号，替换为英文标点"""
    replacements = {
        '"': '"', '"': '"',  # 中文引号 → 英文引号
        ''': "'", ''': "'",  # 中文单引号 → 英文单引号
        '，': ',', '。': '.',  # 中文逗号/句号
        '；': ';', '：': ':',  # 中文分号/冒号
        '（': '(', '）': ')',  # 中文括号
        '《': '"', '》': '"',  # 书名号 → 引号
        '、': ', ',           # 顿号 → 逗号+空格
        '　': ' ',            # 全角空格 → 半角空格
    }
    for zh_punct, en_punct in replacements.items():
        text = text.replace(zh_punct, en_punct)
    return ' '.join(text.split())  # 清理多余空格
```

**应用位置**：
- `translate_title()` - 翻译标题后清理
- `translate_articles_batch()` - 翻译条文后清理

---

### 3. ✅ 新增工具脚本

#### `retranslate.py` - 重新翻译工具

```bash
# 预览待重新翻译的法律
python3 scripts/retranslate.py --dry-run

# 清空所有已翻译法律的英文内容
python3 scripts/retranslate.py

# 只清空特定法律
python3 scripts/retranslate.py --filter 民法典
```

**功能**：
- 扫描所有已翻译的法律
- 交互式确认（需输入 `yes`）
- 清空 `content_en` 字段，保留结构
- 为重新翻译做准备

#### `fix_translations.sh` - 一键修复脚本

```bash
export DEEPSEEK_API_KEY=sk-...  # 或 ANTHROPIC_API_KEY
bash scripts/fix_translations.sh
```

**流程**：
1. 预览待重新翻译的法律
2. 清空已有翻译
3. 使用改进后的脚本重新翻译
4. 验证新翻译的质量
5. 更新 Markdown 双语展示

**安全性**：
- 交互式确认，防止误操作
- 显示预计时间和成本
- 自动检查 API 密钥

---

## 📊 预期改进效果

### 修复前（当前状态）

| 问题类别 | 数量 | 严重度 |
|---------|------|--------|
| 中文标点符号 | 32 | 🔴 高 |
| will/would 用法 | 68 | 🟡 中 |
| 缺少法律助动词 | 86 | 🟢 低 |
| **总计** | **186** | |

### 修复后（预期）

| 问题类别 | 预期数量 | 改进 |
|---------|---------|------|
| 中文标点符号 | **0** | ✅ 100% 修复（自动清理） |
| will/would 用法 | **≤10** | ✅ ~85% 改进（强化 prompt） |
| 缺少法律助动词 | **≤20** | ✅ ~75% 改进（示例引导） |
| **总计** | **≤30** | **83% 减少** |

**质量提升**：4/5 → **4.5/5** ⭐⭐⭐⭐☆

---

## 🎯 使用方法

### 方案A：立即修复现有翻译（推荐）

```bash
# 1. 设置 API 密钥（推荐使用 DeepSeek，成本低）
export DEEPSEEK_API_KEY=sk-...

# 2. 运行一键修复脚本
bash scripts/fix_translations.sh

# 3. 检查验证报告
cat translation_quality_summary.md

# 4. 提交改进
git add -A
git commit -m "fix: 修复翻译质量问题（标点+will/would）"
git push origin main
```

**预计成本**：
- DeepSeek：~$2-3
- Anthropic Haiku 4.5：~$5-10

**预计时间**：10-20 分钟

---

### 方案B：只修复脚本，不重新翻译

如果你想先验证改进效果，可以只翻译一部法律测试：

```bash
# 1. 清空一个短法律
python3 scripts/retranslate.py --filter "婚姻家庭编的解释（二）"

# 2. 重新翻译测试
python3 scripts/translate_to_en.py --filter "婚姻家庭编的解释（二）"

# 3. 验证结果
python3 scripts/validate_translation.py

# 4. 检查是否有改进
grep "婚姻家庭编的解释（二）" translation_validation_report.md
```

如果效果满意，再运行方案A修复所有法律。

---

## 📋 测试清单

修复后，请检查：

- [ ] 所有中文标点都已替换为英文标点
- [ ] 不再出现 `will`/`would` 用法（或大幅减少）
- [ ] 法律助动词使用更规范
- [ ] Markdown 双语展示正常更新
- [ ] 验证报告显示问题数量大幅下降

---

## 🔄 后续建议

### 短期（完成 Pilot 翻译前）

1. ✅ 修复现有11部翻译
2. 补充翻译剩余4部 Pilot（中等×2、大法×2）
3. 人工抽查关键条文
4. 调整术语表（如需）

### 中期（全量翻译前）

5. 补充术语表到300-500条
6. 对民法典前100条进行详细人工审核
7. 确认翻译质量达到4.5/5标准
8. 准备全量翻译（1,518部）

### 长期（全量翻译后）

9. 开发更完善的一致性检查工具
10. 检查跨文件术语一致性
11. 建立翻译质量监控机制

---

## 💡 改进亮点

1. **自动化**：标点清理完全自动化，无需人工干预
2. **安全性**：交互式确认，防止误操作
3. **可追溯**：详细的验证报告，问题一目了然
4. **可重复**：一键脚本，随时可以重新运行
5. **成本控制**：支持 DeepSeek，成本降低50%以上

---

## 📚 相关文件

- `scripts/translate_to_en.py` - 改进后的翻译脚本
- `scripts/retranslate.py` - 重新翻译工具
- `scripts/fix_translations.sh` - 一键修复脚本
- `scripts/validate_translation.py` - 质量验证工具
- `translation_quality_summary.md` - 质量总结报告
- `translation_validation_report.md` - 详细问题列表
