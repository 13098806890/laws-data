#!/usr/bin/env python3
"""
指导性案例抓取脚本
==================
从最高人民法院公报网站抓取全部指导性案例，保存为 Markdown 文件。

来源：http://gongbao.court.gov.cn/ArticleList.html?serial_no=al
输出：laws_data/指导案例/{序号}_{标题}.md

用法：
  cd /Users/doxie/laws_data
  python3 scripts/fetch_guiding_cases.py            # 全量抓取（约 986 条）
  python3 scripts/fetch_guiding_cases.py --page 1   # 只抓第 1 页（调试）
  python3 scripts/fetch_guiding_cases.py --skip-existing  # 跳过已存在文件
"""

import argparse
import re
import sys
import time
import urllib.request
import urllib.error
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "http://gongbao.court.gov.cn"
LIST_URL = BASE_URL + "/ArticleList.html?serial_no=al"
OUT_DIR  = Path(__file__).parent.parent / "指导案例"

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


# ── HTTP 工具 ─────────────────────────────────────────────────────────────────

def fetch(url: str, retries: int = 3, delay: float = 2.0,
          data: bytes = None, headers: dict = None) -> str:
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
    """用 POST 方式获取指定页的列表 HTML。"""
    import urllib.parse
    data = urllib.parse.urlencode({"page": str(page)}).encode()
    return fetch(LIST_URL, data=data, headers=LIST_HEADERS)


# ── 列表页解析 ────────────────────────────────────────────────────────────────

_LI_RE = re.compile(
    r'<li>\s*<span>\s*<a href="(/Details/[^"]+)"[^>]*>([^<]+)</a>',
    re.DOTALL,
)
_LAST_PAGE_RE = re.compile(r'page=(\d+)">末页')


def parse_list_page(html: str) -> tuple[list[tuple[str, str]], int]:
    """返回 (items, last_page)。items = [(url, title), ...]"""
    items = []
    for m in _LI_RE.finditer(html):
        url   = BASE_URL + m.group(1).strip()
        title = m.group(2).strip()
        items.append((url, title))

    last_page = 1
    m = _LAST_PAGE_RE.search(html)
    if m:
        last_page = int(m.group(1))

    return items, last_page


# ── 详情页解析 → Markdown ────────────────────────────────────────────────────

class _HtmlToMd(HTMLParser):
    """把 gb_content 里的 HTML 转换为简洁 Markdown。"""

    def __init__(self):
        super().__init__()
        self._in_content = False
        self._depth      = 0
        self._buf        = []
        self._skip_tags  = {"script", "style", "input", "a", "img"}
        self._cur_skip   = 0
        self._is_strong  = False
        self._para_buf   = []
        self._paras      = []

    def handle_starttag(self, tag, attrs):
        if self._cur_skip:
            self._cur_skip += 1
            return

        attr_dict = dict(attrs)
        if not self._in_content:
            if attr_dict.get("id") == "gb_content":
                self._in_content = True
                self._depth = 1
            return

        if attr_dict.get("id") in ("elevator_item", "elevator"):
            self._cur_skip = 1
            return

        if tag in self._skip_tags:
            self._cur_skip = 1
            return

        if tag == "strong" or tag == "b":
            self._is_strong = True
        elif tag == "br":
            self._flush_para()

    def handle_endtag(self, tag):
        if self._cur_skip:
            self._cur_skip -= 1
            return
        if not self._in_content:
            return
        if tag in ("strong", "b"):
            self._is_strong = False
        elif tag == "p":
            self._flush_para()
        elif tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                self._in_content = False

    def handle_data(self, data):
        if self._cur_skip or not self._in_content:
            return
        text = data.strip()
        if not text:
            return
        if self._is_strong:
            text = f"**{text}**"
        self._para_buf.append(text)

    def _flush_para(self):
        line = "".join(self._para_buf).strip()
        if line:
            self._paras.append(line)
        self._para_buf = []

    def get_markdown(self) -> str:
        self._flush_para()
        return "\n\n".join(self._paras)


def parse_detail(html: str, title: str) -> str:
    """返回 Markdown 字符串。"""
    parser = _HtmlToMd()
    parser.feed(html)
    md = parser.get_markdown()

    if not md.strip():
        # 后备：直接剥离 HTML 标签
        raw = re.sub(r'<[^>]+>', '', html)
        md  = "\n".join(l.strip() for l in raw.splitlines() if l.strip())

    return f"# {title}\n\n{md}\n"


# ── 文件名生成 ────────────────────────────────────────────────────────────────

_CASE_NO_RE = re.compile(r'指导性案例(\d+)号')
_BATCH_RE   = re.compile(r'第(\d+)批')
_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')


def make_filename(title: str, url: str) -> str:
    m = _CASE_NO_RE.search(title)
    if m:
        # 指导性案例 NNN 号 → 0NNN_标题.md
        num    = int(m.group(1))
        prefix = f"{num:04d}"
    else:
        mb = _BATCH_RE.search(title)
        if mb:
            # 发布通知 → batch_NN_标题.md
            prefix = f"batch_{int(mb.group(1)):02d}"
        else:
            # 其他：用 URL 末段 hash 保证唯一
            url_id = url.rstrip('/').split('/')[-1].replace('.html', '')[:16]
            prefix = f"other_{url_id}"

    safe_title = _ILLEGAL_CHARS.sub("_", title)
    safe_title = safe_title[:80].strip()
    return f"{prefix}_{safe_title}.md"


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(only_page: int = None, skip_existing: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 第 1 页：确定总页数（POST）
    print("抓取列表页 1 ...")
    first_html  = fetch_list_page(1)
    items, last = parse_list_page(first_html)
    print(f"共 {last} 页")

    if only_page:
        pages = [only_page]
        if only_page != 1:
            print(f"抓取列表页 {only_page} ...")
            page_html = fetch_list_page(only_page)
            items, _ = parse_list_page(page_html)
    else:
        pages = range(1, last + 1)

    all_items: list[tuple[str, str]] = []
    if only_page == 1 or only_page is None:
        all_items.extend(items)

    if only_page is None:
        for pg in range(2, last + 1):
            print(f"抓取列表页 {pg}/{last} ...")
            try:
                html = fetch_list_page(pg)
                page_items, _ = parse_list_page(html)
                all_items.extend(page_items)
            except Exception as e:
                print(f"  ✗ 第 {pg} 页失败: {e}")
            time.sleep(0.3)
    elif only_page != 1:
        all_items = items

    print(f"\n共收集 {len(all_items)} 条案例，开始抓取详情页...\n")

    ok = 0
    skipped = 0
    failed  = 0

    for i, (url, title) in enumerate(all_items, 1):
        filename = make_filename(title, url)
        out_path = OUT_DIR / filename

        if skip_existing and out_path.exists() and out_path.stat().st_size > 100:
            skipped += 1
            continue

        try:
            detail_html = fetch(url)
            md = parse_detail(detail_html, title)
            out_path.write_text(md, encoding="utf-8")
            ok += 1
            if i % 20 == 0 or i == len(all_items):
                print(f"  [{i}/{len(all_items)}] 已完成 {ok} 个")
        except Exception as e:
            failed += 1
            print(f"  ✗ [{i}] {title[:40]}: {e}")

        time.sleep(0.2)

    print(f"\n完成：{ok} 成功，{skipped} 跳过，{failed} 失败 → {OUT_DIR}")


def main():
    parser = argparse.ArgumentParser(description="最高人民法院指导性案例抓取")
    parser.add_argument("--page", type=int, metavar="N", help="只抓第 N 页（调试）")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的文件")
    args = parser.parse_args()
    run(only_page=args.page, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
