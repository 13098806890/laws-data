#!/usr/bin/env python3
"""
把手动下载的 docx 法律文件转换为结构化 JSON
文件名格式：{标题}_{公布日期YYYYMMDD}.docx
"""

import json
import re
import subprocess
from pathlib import Path
import docx

BASE_DIR = Path("/Users/doxie/laws_data mannual")
OUTPUT_DIR = BASE_DIR / "json"

# 章节标题识别模式
CHAPTER_RE = re.compile(r'^第[一二三四五六七八九十百千]+章\s')
ARTICLE_RE = re.compile(r'^第[一二三四五六七八九十百千]+条\s')
SECTION_RE = re.compile(r'^第[一二三四五六七八九十百千]+节\s')

# 目录行识别（含大量空格或纯目录关键词，跳过）
TOC_KEYWORDS = re.compile(r'^(?:目\s*录|附\s*录|附\s*件)$')


def parse_date_from_filename(stem: str):
    """从文件名提取日期，格式 YYYYMMDD -> YYYY-MM-DD"""
    m = re.search(r'_(\d{8})$', stem)
    if m:
        d = m.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return None


def parse_title_from_filename(stem: str):
    """从文件名提取标题（去掉日期后缀）"""
    return re.sub(r'_\d{8}$', '', stem)


def is_toc_section(paragraphs, start_idx):
    """判断从 start_idx 开始是否是目录区域"""
    text = paragraphs[start_idx].text.strip()
    return bool(TOC_KEYWORDS.match(text) or text in ('目　　录', '目  录', '目录'))


def extract_content(doc_path: Path):
    """提取 docx/doc 全文，返回结构化数据"""
    if doc_path.suffix.lower() == '.doc':
        # 用 macOS textutil 转换为纯文本
        result = subprocess.run(
            ['textutil', '-convert', 'txt', '-stdout', str(doc_path)],
            capture_output=True, text=True, timeout=30
        )
        paras = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    else:
        doc = docx.Document(str(doc_path))
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

    title = ""
    promulgation_info = ""  # 通过/公布信息行
    chapters = []
    full_text_lines = []

    current_chapter = None
    current_section = None
    in_toc = False
    pending_structure = []  # 目录后、第一条前的章节标题缓冲

    for i, text in enumerate(paras):
        # 第一段通常是标题
        if not title:
            title = text
            continue

        # 第二段通常是公布/通过信息
        if not promulgation_info and re.search(r'[届次会议|通过|公布|发布|施行]', text):
            promulgation_info = text
            continue

        # 识别目录开始
        if TOC_KEYWORDS.match(text) or text in ('目　　录', '目  录', '目录'):
            in_toc = True
            continue

        # 目录区域：章节标题缓冲（可能是目录里的或正文前的），遇到第一条才确认正文开始
        if in_toc:
            if CHAPTER_RE.match(text) or SECTION_RE.match(text):
                pending_structure.append(text)
            elif ARTICLE_RE.match(text):
                # 正文开始，先处理缓冲的章节标题（取最后一批连续的）
                in_toc = False
                # 找到最后一次出现第一章/无章的起始位置（去掉目录部分的重复）
                last_ch1 = -1
                for j, s in enumerate(pending_structure):
                    if CHAPTER_RE.match(s):
                        last_ch1 = j
                        break
                # 如果pending里有章标题，取从最后一次"第一章"开始的部分
                if last_ch1 >= 0:
                    pending_structure = pending_structure[last_ch1:]
                for s in pending_structure:
                    full_text_lines.append(s)
                    if CHAPTER_RE.match(s):
                        current_chapter = {"title": s, "sections": [], "articles": []}
                        chapters.append(current_chapter)
                        current_section = None
                    elif SECTION_RE.match(s):
                        current_section = {"title": s, "articles": []}
                        if current_chapter:
                            current_chapter["sections"].append(current_section)
                pending_structure = []
                # 当前行（第一条）继续正常处理
            else:
                pending_structure = []  # 非章节行说明还在目录区，重置
            if in_toc:
                continue

        full_text_lines.append(text)

        # 章
        if CHAPTER_RE.match(text):
            current_chapter = {"title": text, "sections": [], "articles": []}
            chapters.append(current_chapter)
            current_section = None
        # 节
        elif SECTION_RE.match(text):
            current_section = {"title": text, "articles": []}
            if current_chapter:
                current_chapter["sections"].append(current_section)
        # 条
        elif ARTICLE_RE.match(text):
            article = {"title": text[:text.index('　') + 1] if '　' in text else text[:6],
                       "content": text}
            target = current_section or current_chapter
            if target:
                target["articles"].append(article)
            else:
                # 没有章（比如宪法序言等），放到 chapters 空章
                if not chapters:
                    chapters.append({"title": "正文", "sections": [], "articles": []})
                chapters[-1]["articles"].append(article)

    return {
        "title": title,
        "promulgation_info": promulgation_info,
        "full_text": "\n".join(full_text_lines),
        "chapters": chapters,
        "total_articles": sum(
            len(ch.get("articles", [])) + sum(len(s.get("articles", [])) for s in ch.get("sections", []))
            for ch in chapters
        ),
    }


def convert_file(docx_path: Path, category: str):
    stem = docx_path.stem
    pub_date = parse_date_from_filename(stem)
    title = parse_title_from_filename(stem)

    try:
        content = extract_content(docx_path)
    except Exception as e:
        print(f"  ERROR {docx_path.name}: {e}")
        return None

    record = {
        "title": content["title"] or title,
        "filename": docx_path.name,
        "category": category,
        "pub_date": pub_date,
        "promulgation_info": content["promulgation_info"],
        "total_articles": content["total_articles"],
        "chapters": content["chapters"],
        "full_text": content["full_text"],
    }
    return record


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    categories = ["法律", "司法解释", "行政法规", "宪法", "监察法规"]

    total = 0
    for cat in categories:
        cat_dir = BASE_DIR / cat
        if not cat_dir.exists():
            continue

        out_cat_dir = OUTPUT_DIR / cat
        out_cat_dir.mkdir(exist_ok=True)

        files = sorted(f for f in cat_dir.iterdir()
                       if f.suffix.lower() in ('.docx', '.doc'))
        print(f"\n=== {cat}: {len(files)} 个文件 ===")

        for f in files:
            record = convert_file(f, cat)
            if record is None:
                continue

            # 文件名用标题+日期
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', f.stem)
            out_path = out_cat_dir / f"{safe_name}.json"
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            total += 1
            print(f"  [{total}] {record['title']} ({record['pub_date']}) "
                  f"-> {record['total_articles']} 条")

    # 生成索引文件
    index = []
    for cat in categories:
        for jf in sorted((OUTPUT_DIR / cat).glob("*.json")):
            d = json.loads(jf.read_text())
            index.append({
                "title": d["title"],
                "category": d["category"],
                "pub_date": d["pub_date"],
                "total_articles": d["total_articles"],
                "file": str(jf.relative_to(OUTPUT_DIR)),
            })

    (OUTPUT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成！共转换 {total} 个文件")
    print(f"索引: {OUTPUT_DIR / 'index.json'} ({len(index)} 条)")
    print(f"输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
