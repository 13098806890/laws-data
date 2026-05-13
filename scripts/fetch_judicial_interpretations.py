#!/usr/bin/env python3
"""
最高人民法院公报司法解释抓取脚本
==================================
来源：http://gongbao.court.gov.cn/ArticleList.html?serial_no=sfjs
输出：laws_data/公报司法解释/{YYYYMM}_{标题}.json

每个 JSON 文件结构：
{
  "title":        "最高人民法院关于……的解释",
  "issue":        "2026年03期",
  "year":         2026,
  "issue_num":    3,
  "url":          "http://gongbao.court.gov.cn/Details/xxx.html",
  "doc_number":   "法释〔2026〕2号",   // 从正文提取，可能为空
  "pub_date":     "2026-01-19",        // 从公告段落提取，可能为空
  "effective_date": "2026-02-01",      // 从公告段落提取，可能为空
  "content":      "全文纯文本"
}

用法：
  cd /Users/doxie/laws_data
  python3 scripts/fetch_judicial_interpretations.py           # 全量抓取
  python3 scripts/fetch_judicial_interpretations.py --page 1  # 只抓第1页（调试）
  python3 scripts/fetch_judicial_interpretations.py --skip-existing  # 断点续抓
"""

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_URL   = "http://gongbao.court.gov.cn"
LIST_URL   = BASE_URL + "/ArticleList.html?serial_no=sfjs"
OUT_DIR    = Path(__file__).parent.parent / "公报司法解释"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
LIST_HEADERS = {
    **HEADERS,
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": LIST_URL,
}


# ── HTTP ─────────────────────────────────────────────────────────────────────

def fetch(url: str, data: bytes = None, headers: dict = None,
          retries: int = 3, delay: float = 2.0) -> str:
    h = headers or HEADERS
    req = urllib.request.Request(url, data=data, headers=h)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("gbk", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"    重试 ({attempt+1}/{retries}): {e}")
            time.sleep(delay)


def fetch_list_page(page: int) -> str:
    data = urllib.parse.urlencode({"page": str(page)}).encode()
    return fetch(LIST_URL, data=data, headers=LIST_HEADERS)


# ── 列表页解析 ────────────────────────────────────────────────────────────────

_LI_RE = re.compile(
    r'<a href="(/Details/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>\s*<lable>([^<]+)</lable>',
    re.DOTALL,
)
_LAST_PAGE_RE = re.compile(r'page=(\d+)">末页')


def parse_list_page(html: str) -> tuple[list[dict], int]:
    items = []
    for m in _LI_RE.finditer(html):
        url   = BASE_URL + m.group(1).strip()
        title = m.group(2).strip()
        issue = m.group(3).strip()   # e.g. "2026年03期"
        items.append({"url": url, "title": title, "issue": issue})

    last_page = 1
    m = _LAST_PAGE_RE.search(html)
    if m:
        last_page = int(m.group(1))
    return items, last_page


# ── 详情页解析 ────────────────────────────────────────────────────────────────

class _HtmlToText(HTMLParser):
    """提取 #gb_content 内的纯文本，保留段落分隔。"""

    def __init__(self):
        super().__init__()
        self._in   = False
        self._depth = 0
        self._skip  = 0
        self._para  = []
        self._paras = []

    def handle_starttag(self, tag, attrs):
        if self._skip:
            self._skip += 1
            return
        attr = dict(attrs)
        if not self._in:
            if attr.get("id") == "gb_content":
                self._in    = True
                self._depth = 1
            return
        if attr.get("id") in ("elevator_item", "elevator"):
            self._skip = 1
            return
        if tag in ("script", "style", "input", "img"):
            self._skip = 1
            return
        if tag == "br":
            self._flush()
        if tag == "div":
            self._depth += 1

    def handle_endtag(self, tag):
        if self._skip:
            self._skip -= 1
            return
        if not self._in:
            return
        if tag == "p":
            self._flush()
        elif tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self._in = False

    def handle_data(self, data):
        if self._skip or not self._in:
            return
        t = data.strip()
        if t:
            self._para.append(t)

    def _flush(self):
        line = "".join(self._para).strip()
        if line:
            self._paras.append(line)
        self._para = []

    def get_text(self) -> str:
        self._flush()
        return "\n\n".join(self._paras)


# 提取发文字号，如 法释〔2026〕2号
_DOC_NUM_RE = re.compile(r'(?:法释|法\[)[〔\[]?\d{4}[〕\]]?\d+号')
# 提取公布日期
_PUB_DATE_RE = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')
# 提取施行日期 "自XXXX年XX月XX日起施行"
_EFF_DATE_RE = re.compile(r'自(\d{4})年(\d{1,2})月(\d{1,2})日起施行')


def _fmt_date(y, m, d) -> str:
    return f"{y}-{int(m):02d}-{int(d):02d}"


def parse_detail(html: str, title: str, issue: str, url: str) -> dict:
    parser = _HtmlToText()
    parser.feed(html)
    content = parser.get_text()

    # 期号拆解
    year_m = re.match(r'(\d{4})年(\d+)期', issue)
    year      = int(year_m.group(1)) if year_m else None
    issue_num = int(year_m.group(2)) if year_m else None

    # 发文字号
    doc_num = ""
    m = _DOC_NUM_RE.search(content)
    if m:
        doc_num = m.group(0)

    # 公布日期：取正文中首次出现的独立日期行（通常在公告段末）
    pub_date = ""
    for m in _PUB_DATE_RE.finditer(content):
        # 排除条文内容中的日期（通常较短行）
        pub_date = _fmt_date(m.group(1), m.group(2), m.group(3))
        break

    # 施行日期
    eff_date = ""
    m = _EFF_DATE_RE.search(content)
    if m:
        eff_date = _fmt_date(m.group(1), m.group(2), m.group(3))

    return {
        "title":          title,
        "issue":          issue,
        "year":           year,
        "issue_num":      issue_num,
        "url":            url,
        "doc_number":     doc_num,
        "pub_date":       pub_date,
        "effective_date": eff_date,
        "content":        content,
    }


# ── 文件名生成 ────────────────────────────────────────────────────────────────

_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def make_filename(item: dict) -> str:
    issue = item.get("issue", "")
    m = re.match(r'(\d{4})年(\d+)期', issue)
    if m:
        prefix = f"{m.group(1)}{int(m.group(2)):02d}"
    else:
        prefix = "000000"
    safe = _ILLEGAL.sub("_", item["title"])[:80].strip()
    return f"{prefix}_{safe}.json"


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(only_page: int = None, skip_existing: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("抓取列表页 1 ...")
    first_html      = fetch_list_page(1)
    items, last     = parse_list_page(first_html)
    print(f"共 {last} 页")

    all_items: list[dict] = []

    if only_page:
        if only_page == 1:
            all_items = items
        else:
            print(f"抓取列表页 {only_page} ...")
            all_items, _ = parse_list_page(fetch_list_page(only_page))
    else:
        all_items.extend(items)
        for pg in range(2, last + 1):
            print(f"抓取列表页 {pg}/{last} ...")
            try:
                page_items, _ = parse_list_page(fetch_list_page(pg))
                all_items.extend(page_items)
            except Exception as e:
                print(f"  ✗ 第 {pg} 页失败: {e}")
            time.sleep(0.3)

    print(f"\n共收集 {len(all_items)} 条司法解释，开始抓取详情...\n")

    ok = skipped = failed = 0

    for i, item in enumerate(all_items, 1):
        filename = make_filename(item)
        out_path = OUT_DIR / filename

        if skip_existing and out_path.exists() and out_path.stat().st_size > 50:
            skipped += 1
            continue

        try:
            detail_html = fetch(item["url"])
            data = parse_detail(detail_html, item["title"], item["issue"], item["url"])
            out_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            ok += 1
            if i % 20 == 0 or i == len(all_items):
                print(f"  [{i}/{len(all_items)}] 已完成 {ok} 个")
        except Exception as e:
            failed += 1
            print(f"  ✗ [{i}] {item['title'][:40]}: {e}")

        time.sleep(0.2)

    print(f"\n完成：{ok} 成功，{skipped} 跳过，{failed} 失败 → {OUT_DIR}")


def main():
    parser = argparse.ArgumentParser(description="最高人民法院公报司法解释抓取")
    parser.add_argument("--page", type=int, metavar="N", help="只抓第 N 页（调试）")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在文件（断点续抓）")
    args = parser.parse_args()
    run(only_page=args.page, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
