# 英文翻译重译方案

## 问题总结

**核心问题**：中文条文中的换行符在翻译过程中丢失，导致多段落文本被合并成一段。

### 受影响范围

| 指标 | 数量 | 百分比 |
|------|------|--------|
| **总条文数** | 58,683 | 100% |
| **含多段落的条文**（中文原文有换行） | 27,724 | 47.2% |
| **受影响的法律** | 1,536 | - |
| **已翻译的法律** | 33 | - |
| **已翻译的条文** | 2,299 | - |
| **疑似需重译的条文**（长度>200且无换行） | 1,868 | 81.3% |

### 修复内容

已修改三个脚本：

1. **`translate_to_en.py`** 
   - ✅ `clean_punctuation` 函数现在保留换行符
   - ✅ 系统提示词要求保留段落结构
   - ✅ 批量翻译提示词强调换行符重要性

2. **`add_en_to_md.py`**
   - ✅ 将换行符转换为 Markdown 硬换行（`  \n`）

3. **`test_bilingual_fix.py`**
   - ✅ 新增测试脚本验证修复效果

## 重译方案

### 方案一：完全重译（推荐）

**适用场景**：确保所有翻译质量一致，已翻译数量较少（33部法律）

**优点**：
- 所有翻译都使用新的规则，质量统一
- 解决所有换行符问题
- 可以同时修正其他翻译问题

**成本估算**：
```
已翻译条文：2,299 条
按 Haiku 4.5 计算（$0.80 / MTok input, $4.00 / MTok output）：
  输入 tokens：约 2.3M tokens（每条文约 1000 tokens）
  输出 tokens：约 1.2M tokens（每条文约 500 tokens）
  
估算成本：
  输入：2.3M × $0.80 = $1.84
  输出：1.2M × $4.00 = $4.80
  总计：约 $6.64
```

**执行步骤**：
```bash
# 1. 备份现有翻译
cp -r json_en json_en.backup_$(date +%Y%m%d)

# 2. 删除已有翻译（保留文件结构，清空 content_en）
python3 scripts/clear_translations.py

# 3. 重新翻译（可分批进行）
# 先翻译重要法律
python3 scripts/translate_to_en.py --filter 民法典
python3 scripts/translate_to_en.py --filter 刑法
python3 scripts/translate_to_en.py --filter 民事诉讼法

# 然后全量翻译
python3 scripts/translate_to_en.py

# 4. 重新插入到 Markdown
python3 scripts/add_en_to_md.py
```

---

### 方案二：选择性重译

**适用场景**：只重译确实有问题的条文

**优点**：
- 成本更低
- 保留已经正确的翻译

**缺点**：
- 需要识别哪些条文有问题
- 翻译规则不完全统一

**执行步骤**：
```bash
# 1. 生成需要重译的条文列表
python3 scripts/identify_problematic_translations.py

# 2. 只重译这些条文
python3 scripts/retranslate_selective.py

# 3. 重新插入到 Markdown
python3 scripts/add_en_to_md.py
```

---

### 方案三：增量重译

**适用场景**：预算有限，优先处理高优先级法律

**执行步骤**：

**阶段一：核心法律（11部）**
```bash
# 民法典 + 10部核心法律（已在之前的批次中）
python3 scripts/retranslate.py --filter 民法典
python3 scripts/retranslate.py --filter 刑法
python3 scripts/retranslate.py --filter 民事诉讼法
python3 scripts/retranslate.py --filter 刑事诉讼法
python3 scripts/retranslate.py --filter 行政诉讼法
python3 scripts/retranslate.py --filter 公司法
python3 scripts/retranslate.py --filter 合同法
python3 scripts/retranslate.py --filter 劳动法
python3 scripts/retranslate.py --filter 婚姻法
python3 scripts/retranslate.py --filter 继承法
```

**阶段二：司法解释（疑似需重译最多）**
```bash
# 按批次处理司法解释
python3 scripts/retranslate_by_category.py --category 司法解释
```

**阶段三：剩余法律**
```bash
# 全量重译
python3 scripts/translate_to_en.py
```

---

## 建议

**我的推荐：方案一（完全重译）**

理由：
1. **成本可控**：约 $6.64，预算可接受
2. **质量统一**：所有翻译使用相同规则
3. **一次性解决**：避免后续反复调整
4. **已翻译数量少**：33部法律，重译成本远低于后期修复成本

**执行时间建议**：
- 可以在一个会话内完成（估计 30-60 分钟）
- 使用批量翻译（每批 20 条），提高效率
- 失败自动重试，可恢复

**风险控制**：
- ✅ 已备份现有翻译
- ✅ 有 `--dry-run` 模式预览
- ✅ 增量翻译，中断可恢复
- ✅ 有测试脚本验证质量

---

## 验证步骤

重译完成后，运行验证：

```bash
# 1. 运行测试脚本
python3 scripts/test_bilingual_fix.py

# 2. 检查具体法律
python3 -c "
import json
from pathlib import Path

# 检查民法典第34条
data = json.load(open('json_en/法律/中华人民共和国民法典_20200528.json'))
for art in data['articles']:
    if art['article_number'] == '第三十四条':
        en = art.get('content_en', '')
        print('第34条段落数：', en.count('\n') + 1)
        print('前100字符：', en[:100])
        break
"

# 3. 生成质量报告
python3 scripts/verify_translations.py
```

---

## 需要创建的脚本

为了支持上述方案，需要创建以下脚本：

1. **`clear_translations.py`** — 清空已有翻译（保留结构）
2. **`identify_problematic_translations.py`** — 识别有问题的翻译
3. **`retranslate_selective.py`** — 选择性重译
4. **`retranslate_by_category.py`** — 按分类重译
5. **`verify_translations.py`** — 验证翻译质量

需要我创建这些脚本吗？
