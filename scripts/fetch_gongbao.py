#!/usr/bin/env python3
"""
最高人民法院公报通用抓取脚本
==============================
支持五个栏目，每个栏目保存到独立目录，每条记录保存为 JSON 文件。

栏目：
  al      指导性案例      → 最高人民法院公报/指导案例/
  sfjs    司法解释        → 最高人民法院公报/司法解释/
  cpwsxd  裁判文书        → 最高人民法院公报/裁判文书/
  flxd    法律法规        → 最高人民法院公报/法律法规/
  sfwj    司法文件        → 最高人民法院公报/司法文件/

JSON 结构：
{
  "title":          str,
  "issue":          str,   // "2026年03期"
  "year":           int,
  "issue_num":      int,
  "url":            str,
  "doc_number":     str,   // 发文字号，可能为空
  "pub_date":       str,   // YYYY-MM-DD，可能为空
  "effective_date": str,   // YYYY-MM-DD，可能为空
  "content":        str    // 全文纯文本
}

用法：
  cd path/to/laws_data
  python3 scripts/fetch_gongbao.py                      # 抓取所有栏目
  python3 scripts/fetch_gongbao.py --target al          # 只抓指导性案例
  python3 scripts/fetch_gongbao.py --target sfjs        # 只抓司法解释
  python3 scripts/fetch_gongbao.py --page 1             # 只抓第1页（调试）
  python3 scripts/fetch_gongbao.py --skip-existing      # 断点续抓
"""

import argparse
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "http://gongbao.court.gov.cn"
BASE_DIR = Path(__file__).parent.parent

# ── 栏目配置 ──────────────────────────────────────────────────────────────────
TARGETS = {
    "al": {
        "name":   "指导性案例",
        "serial": "al",
        "outdir": BASE_DIR / "最高人民法院公报" / "指导案例",
    },
    "sfjs": {
        "name":   "司法解释",
        "serial": "sfjs",
        "outdir": BASE_DIR / "最高人民法院公报" / "司法解释",
    },
    "cpwsxd": {
        "name":   "裁判文书",
        "serial": "cpwsxd",
        "outdir": BASE_DIR / "最高人民法院公报" / "裁判文书",
    },
    "flxd": {
        "name":   "法律法规",
        "serial": "flxd",
        "outdir": BASE_DIR / "最高人民法院公报" / "法律法规",
    },
    "sfwj": {
        "name":   "司法文件",
        "serial": "sfwj",
        "outdir": BASE_DIR / "最高人民法院公报" / "司法文件",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate",
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
                # decompress gzip if needed
                if raw[:2] == b'\x1f\x8b':
                    raw = gzip.decompress(raw)
                try:
                    return raw.decode("utf-8")
                except UnicodeDecodeError:
                    return raw.decode("gbk", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"    重试 ({attempt+1}/{retries}): {e}")
            time.sleep(delay)


def fetch_list_page(serial: str, page: int) -> str:
    list_url = f"{BASE_URL}/ArticleList.html?serial_no={serial}"
    list_headers = {
        **HEADERS,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": list_url,
    }
    data = urllib.parse.urlencode({"page": str(page)}).encode()
    return fetch(list_url, data=data, headers=list_headers)


# ── 列表页解析 ────────────────────────────────────────────────────────────────

_LI_RE = re.compile(
    r'<a href="(/Details/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>\s*<lable>([^<]+)</lable>',
    re.DOTALL,
)
_LAST_PAGE_RE = re.compile(r'page=(\d+)">末页')


def parse_list_page(html: str) -> tuple[list[dict], int]:
    items = []
    for m in _LI_RE.finditer(html):
        items.append({
            "url":   BASE_URL + m.group(1).strip(),
            "title": m.group(2).strip(),
            "issue": m.group(3).strip(),
        })
    last_page = 1
    m = _LAST_PAGE_RE.search(html)
    if m:
        last_page = int(m.group(1))
    return items, last_page


# ── 详情页解析 ────────────────────────────────────────────────────────────────

class _HtmlToText(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in    = False
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


_DOC_NUM_RE = re.compile(
    r'(?:法释|法\[|法函|法发|法办|法行|发改|国发|国办发|国办函)'
    r'[〔\[]?\d{4}[〕\]]?\d+号'
)
_PUB_DATE_RE  = re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日')
_EFF_DATE_RE  = re.compile(r'自(\d{4})年(\d{1,2})月(\d{1,2})日起(?:施行|实施|执行)')


def _fmt(y, m, d) -> str:
    return f"{y}-{int(m):02d}-{int(d):02d}"


def parse_detail(html: str, item: dict) -> dict:
    parser = _HtmlToText()
    parser.feed(html)
    content = parser.get_text()

    issue   = item.get("issue", "")
    year_m  = re.match(r'(\d{4})年(\d+)期', issue)
    year      = int(year_m.group(1)) if year_m else None
    issue_num = int(year_m.group(2)) if year_m else None

    doc_num = ""
    m = _DOC_NUM_RE.search(content)
    if m:
        doc_num = m.group(0)

    pub_date = ""
    for m in _PUB_DATE_RE.finditer(content):
        pub_date = _fmt(m.group(1), m.group(2), m.group(3))
        break

    eff_date = ""
    m = _EFF_DATE_RE.search(content)
    if m:
        eff_date = _fmt(m.group(1), m.group(2), m.group(3))

    return {
        "title":          item["title"],
        "issue":          issue,
        "year":           year,
        "issue_num":      issue_num,
        "url":            item["url"],
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
    prefix = f"{m.group(1)}{int(m.group(2)):02d}" if m else "000000"
    safe   = _ILLEGAL.sub("_", item["title"])[:80].strip()
    return f"{prefix}_{safe}.json"


# ── 单栏目抓取 ────────────────────────────────────────────────────────────────

def fetch_target(cfg: dict, only_page: int = None, skip_existing: bool = False):
    serial  = cfg["serial"]
    name    = cfg["name"]
    out_dir = cfg["outdir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"栏目：{name}（{serial}）→ {out_dir.name}/")
    print(f"{'='*60}")

    print("抓取列表页 1 ...")
    first_html  = fetch_list_page(serial, 1)
    items, last = parse_list_page(first_html)
    print(f"共 {last} 页")

    all_items: list[dict] = []

    if only_page:
        if only_page == 1:
            all_items = items
        else:
            print(f"抓取列表页 {only_page} ...")
            all_items, _ = parse_list_page(fetch_list_page(serial, only_page))
    else:
        all_items.extend(items)
        for pg in range(2, last + 1):
            print(f"抓取列表页 {pg}/{last} ...")
            try:
                page_items, _ = parse_list_page(fetch_list_page(serial, pg))
                all_items.extend(page_items)
            except Exception as e:
                print(f"  ✗ 第 {pg} 页失败: {e}")
            time.sleep(0.3)

    print(f"\n共收集 {len(all_items)} 条，开始抓取详情...\n")

    ok = skipped = failed = 0

    for i, item in enumerate(all_items, 1):
        filename = make_filename(item)
        out_path = out_dir / filename

        if skip_existing and out_path.exists() and out_path.stat().st_size > 50:
            skipped += 1
            continue

        try:
            detail_html = fetch(item["url"])
            data = parse_detail(detail_html, item)
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

    print(f"\n{name} 完成：{ok} 成功，{skipped} 跳过，{failed} 失败")
    return ok, failed


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="最高人民法院公报通用抓取")
    parser.add_argument("--target", choices=list(TARGETS.keys()),
                        help="只抓指定栏目（默认全部）")
    parser.add_argument("--page", type=int, metavar="N",
                        help="只抓第 N 页（调试）")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳过已存在文件（断点续抓）")
    args = parser.parse_args()

    targets = [TARGETS[args.target]] if args.target else list(TARGETS.values())

    total_ok = total_fail = 0
    for cfg in targets:
        ok, fail = fetch_target(cfg, only_page=args.page,
                                skip_existing=args.skip_existing)
        total_ok   += ok
        total_fail += fail

    print(f"\n{'='*60}")
    print(f"全部完成：{total_ok} 成功，{total_fail} 失败")


if __name__ == "__main__":
    main()
