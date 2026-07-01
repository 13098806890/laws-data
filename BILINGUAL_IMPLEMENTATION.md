# 双语数据库与Markdown实现报告

## 📋 概述

成功实现了从 json_en 到数据库再到 Markdown 的完整双语流程，将11部法律的英文翻译整合进主系统。

## 🎯 核心成果

### 数据库扩展
- ✅ 在 `nodes` 表增加 `content_en` 字段
- ✅ 导入 2,101 条英文译文（71,633 条总数的 2.9%）
- ✅ 11 部法律完整翻译：
  - 中华人民共和国民法典（1,260条）
  - 最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（一）（91条）
  - 最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（二）（23条）
  - 最高人民法院关于适用《中华人民共和国民法典》有关担保制度的解释（71条）
  - 最高人民法院关于适用《中华人民共和国民法典》物权编的解释（一）（21条）
  - 最高人民法院关于适用《中华人民共和国民法典》继承编的解释（一）（45条）
  - 最高人民法院关于适用《中华人民共和国民法典》总则编若干问题的解释（27条）
  - 最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释（29条）
  - 最高人民法院关于适用《中华人民共和国民法典》侵权责任编的解释（一）（30条）
  - 最高人民法院关于适用《中华人民共和国民法典》时间效力的若干规定（29条）
  - 最高人民法院关于适用《中华人民共和国民法典》涉外民事关系法律适用法若干问题的解释（一）（5条）

### Markdown 双语渲染

格式示例：
```markdown
<a id="art-1"></a>第一条　为了保护民事主体的合法权益，调整民事关系，维护社会和经济秩序，适应中国特色社会主义发展要求，弘扬社会主义核心价值观，根据宪法，制定本法。

**Article 1** This Law is enacted in accordance with the Constitution of the People's Republic of China for the purposes of protecting the lawful rights and interests of civil subjects, regulating civil relations, maintaining social and economic order, meeting the requirements of the development of socialism with Chinese characteristics, and promoting the core socialist values.
```

特点：
- 中英文逐条对照
- 保留锚点链接（用于引用关系）
- 保留引用上标（被引用标记）
- 自动提取或生成 Article X 标签

## 🔧 技术实现

### 1. 数据库导入脚本（import_en_to_db.py）

```python
# 核心逻辑：
1. 添加 content_en 字段到 nodes 表
2. 从 law_content.db 读取法律映射（filename → law_id）
3. 遍历 json_en/*.json
4. 根据 article_number 匹配 nodes 记录并更新 content_en
```

处理细节：
- 跳过 type != 'article' 的节点（编/章/节不翻译）
- 容错：未匹配的法律/条文发出警告但不中断
- 性能：批量 UPDATE，每 100 条提交一次

### 2. Markdown 渲染逻辑（db_to_md/renderer.py）

修改点：
```python
# 查询时增加 content_en
nodes_rows = conn.execute(
    'SELECT type, content, article_num, content_en FROM nodes ...'
)

# 渲染条文时追加英文段落
if content_en:
    art_en_match = re.match(r'(Article \d+)', content_en)
    if art_en_match:
        # json_en 中已有 Article 前缀
        art_en_label = art_en_match.group(0)
        en_body = content_en[len(art_en_label):].strip()
        lines.append(f'**{art_en_label}** {en_body}')
    else:
        # 自己添加 Article 前缀
        lines.append(f'**Article {art_num}** {content_en}')
```

## 📊 统计数据

### 全库统计
```sql
SELECT 
  COUNT(*) AS total_articles,
  SUM(CASE WHEN content_en IS NOT NULL AND content_en != '' THEN 1 ELSE 0 END) AS has_en,
  SUM(CASE WHEN content_en IS NOT NULL AND content_en != '' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS en_pct
FROM nodes WHERE type='article';

-- 结果：71633 | 2101 | 2.93%
```

### 已翻译法律（Top 15）
| 法律名称 | 条文数 | 法律部门 |
|---------|--------|----------|
| 中华人民共和国民法典 | 1,260 | 民法典 |
| 最高人民法院关于适用《中华人民共和国民法典》婚姻家庭编的解释（一） | 91 | 民法典 |
| 中华人民共和国澳门特别行政区基本法 | 80 | 宪法相关法 |
| 最高人民法院关于适用《中华人民共和国民法典》有关担保制度的解释 | 71 | 民法典 |
| 中华人民共和国香港特别行政区基本法 | 60 | 宪法相关法 |
| 中华人民共和国宪法（2018年修正文本） | 59 | 宪法相关法 |
| 中华人民共和国价格法 | 48 | 宪法相关法 |
| 最高人民法院关于适用《中华人民共和国民法典》继承编的解释（一） | 45 | 民法典 |

## 🚀 工作流

完整流程：
```bash
# 第一阶段：JSON生成（已完成）
cd scripts
python3 -m docx_to_json.converter

# 第二阶段：数据库生成
python3 -m json_to_db.builder

# 第三阶段：英文导入（新增）
python3 import_en_to_db.py

# 第四阶段：Markdown渲染（已修改）
python3 -m db_to_md.renderer
```

或一键运行：
```bash
python3 scripts/pipeline.py  # 包含所有阶段
```

## 📁 文件结构

```
laws_data/
├── json_en/                          # 英文翻译源（只读，不纳入主库）
│   └── 司法解释/
│       ├── 中华人民共和国民法典_20200528.json
│       └── ...
├── law_content.db                    # 主数据库（含 content_en 字段）
├── scripts/
│   ├── import_en_to_db.py           # 英文导入脚本（新增）
│   └── db_to_md/
│       └── renderer.py              # Markdown渲染器（已修改）
└── 民事与商事/民法典/              # 双语 Markdown 输出
    └── 中华人民共和国民法典.md
```

## 🔍 已知问题与警告

### 导入时的警告信息
运行 `import_en_to_db.py` 时出现多条"未找到法律"警告，原因：

1. **文件名格式不匹配**：
   - json_en 中的文件名与数据库 laws.filename 不完全对应
   - 例如：司法解释标题中的空格、连字符差异

2. **数据库中不存在的法律**：
   - 部分 json_en 文件对应的法律在主库中被标记为非现行版本（is_current=0）
   - 或属于多版本法律中的旧版本

3. **影响**：
   - 这些警告不影响已匹配法律的导入
   - 当前 2,101 条成功导入，未匹配的法律暂时跳过

### 解决方案
未来可选择：
- 扩展文件名匹配逻辑（模糊匹配/正则）
- 手工维护 json_en 文件名映射表
- 或直接修正 json_en 文件名使其与数据库一致

## 🎉 成果验证

### 查看双语 Markdown

```bash
# 民法典
cat "./民事与商事/民法典/中华人民共和国民法典.md" | head -50

# 宪法
cat "./宪法与国家机构/宪法/中华人民共和国宪法（2018年修正文本）.md" | head -50
```

### 查询双语条文

```bash
sqlite3 law_content.db "
SELECT content, content_en 
FROM nodes 
WHERE law_id = (SELECT id FROM laws WHERE title = '中华人民共和国民法典') 
  AND type = 'article' 
  AND article_num = '1';
"
```

## 📝 后续工作

1. **扩展翻译覆盖**：
   - 继续翻译剩余重要法律（刑法、行政诉讼法等）
   - 优先翻译法考重点法律（is_flk=1）

2. **提升匹配率**：
   - 解决 json_en 文件名不匹配问题
   - 处理多版本法律的英文映射

3. **渲染增强**：
   - 可选：添加"显示/隐藏英文"的前端交互
   - 可选：生成纯英文版 Markdown（供国际用户）

4. **质量保障**：
   - 人工抽查双语对照准确性
   - 建立翻译术语表（确保术语一致性）

## 🔗 相关提交

- **主功能**：[273b3b71] feat: 双语数据库与Markdown实现
- **民法典**：[18b38069] feat: 民法典双语Markdown（1260条）
- **宪法相关**：[102ea4aa] feat: 宪法相关法双语Markdown（10部法律）

---
**生成时间**: 2026-07-01  
**实施者**: Claude (claude-sonnet-4.5)
