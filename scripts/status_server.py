#!/usr/bin/env python3
"""HTTP status server for translation progress monitoring."""

import http.server
import json
import os
import time
from pathlib import Path

JSON_EN_DIR = Path(__file__).parent.parent / 'json_en'
JSON_EN_GONGBAO_DIR = Path(__file__).parent.parent / 'json_en_gongbao'
DB_PATH = str(Path(__file__).parent.parent / 'law_content.db')

PORT = int(os.environ.get('STATUS_PORT', '8080'))
LAST_N_MINUTES = 5


def count_t5_progress():
    """只统计 T5 层级的法律（citation < 1），从 DB 读取列表。"""
    total_laws = 0
    done = 0
    total_articles = 0
    done_articles = 0
    try:
        import sqlite3
        conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
        rows = conn.execute('''
            SELECT l.id, l.filename, l.category, COUNT(r.id) as refs
            FROM laws l
            LEFT JOIN article_references r ON r.to_law_id = l.id
            WHERE l.is_current=1
            GROUP BY l.id HAVING refs < 1
        ''').fetchall()
        conn.close()
    except Exception:
        rows = []
    total_laws = len(rows)
    for law_id, filename, category, refs in rows:
        f = JSON_EN_DIR / category / f'{filename}.json'
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        articles = data.get('articles', []) or []
        total_articles += len(articles)
        has_en = sum(1 for a in articles if a.get('content_en', '').strip())
        done_articles += has_en
        if has_en == len(articles) and len(articles) > 0:
            done += 1
        elif len(articles) == 0:
            # 无文章结构的法律：full_text_en 或 stub（无中文内容）都算完成
            done += 1
    return {
        'total': total_laws,
        'done': done,
        'total_articles': total_articles,
        'done_articles': done_articles,
    }


GONGBAO_TOTALS = {}
try:
    import sqlite3
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    for row in conn.execute("SELECT source, COUNT(*) FROM gongbao_docs GROUP BY source"):
        GONGBAO_TOTALS[row[0]] = row[1]
    conn.close()
except Exception:
    pass


def count_gongbao_progress():
    done_by_source = {}
    if JSON_EN_GONGBAO_DIR.is_dir():
        for source_dir in JSON_EN_GONGBAO_DIR.iterdir():
            if not source_dir.is_dir():
                continue
            done_count = 0
            for f in source_dir.glob('*.json'):
                try:
                    data = json.loads(f.read_text(encoding='utf-8'))
                    if data.get('full_text_en', '').strip():
                        done_count += 1
                except Exception:
                    pass
            done_by_source[source_dir.name] = done_count
    total = sum(GONGBAO_TOTALS.values())
    done = sum(done_by_source.values())
    sources = {}
    for src, src_total in GONGBAO_TOTALS.items():
        sources[src] = {'total': src_total, 'done': done_by_source.get(src, 0)}
    return {'total': total, 'done': done, 'sources': sources}


def count_recent_chars(minutes=5):
    cutoff = time.time() - minutes * 60
    chars = 0
    files = 0
    for root, dirs, files_list in os.walk(JSON_EN_GONGBAO_DIR):
        for fname in files_list:
            if not fname.endswith('.json'):
                continue
            fpath = Path(root) / fname
            mtime = fpath.stat().st_mtime
            if mtime < cutoff:
                continue
            try:
                data = json.loads(fpath.read_text(encoding='utf-8'))
                ft = data.get('full_text_en', '') or ''
                chars += len(ft)
                files += 1
            except Exception:
                pass
    for root, dirs, files_list in os.walk(JSON_EN_DIR):
        for fname in files_list:
            if not fname.endswith('.json'):
                continue
            fpath = Path(root) / fname
            mtime = fpath.stat().st_mtime
            if mtime < cutoff:
                continue
            try:
                data = json.loads(fpath.read_text(encoding='utf-8'))
                for a in data.get('articles', []) or []:
                    content = a.get('title_en', '') or ''
                    chars += len(content)
                    content = a.get('content_en', '') or ''
                    chars += len(content)
                ft = data.get('full_text_en', '') or ''
                chars += len(ft)
                files += 1
            except Exception:
                pass
    return chars, files

def estimate_remaining(t5, gongbao, recent_chars, recent_seconds=300):
    speed = recent_chars / recent_seconds if recent_seconds > 0 else 0
    gc_remaining_docs = GONGBAO_TOTALS.get('al', 986) - gongbao['sources'].get('al', {}).get('done', 0)
    gc_remaining_chars = gc_remaining_docs * 4714
    t5_remaining_laws = t5['total'] - t5['done']
    t5_remaining_articles = t5['total_articles'] - t5['done_articles']
    t5_remaining_chars = t5_remaining_articles * 500
    total_remaining_chars = gc_remaining_chars + t5_remaining_chars
    eta = total_remaining_chars / speed if speed > 0 else 0
    return {
        'gc_remaining_docs': gc_remaining_docs,
        'gc_remaining_chars': gc_remaining_chars,
        't5_remaining_laws': t5_remaining_laws,
        't5_remaining_articles': t5_remaining_articles,
        'total_remaining_chars': total_remaining_chars,
        'eta_seconds': eta,
        'speed_chars_per_sec': round(speed, 1),
    }


index_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>翻译进度</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 24px; }
  h1 { font-size: 24px; margin-bottom: 20px; color: #f0f6fc; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
  .card h2 { font-size: 14px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
  .stat-row { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 0; }
  .stat-row + .stat-row { border-top: 1px solid #21262d; }
  .label { font-size: 14px; color: #c9d1d9; }
  .value { font-size: 20px; font-weight: 600; color: #f0f6fc; font-variant-numeric: tabular-nums; }
  .value.green { color: #3fb950; }
  .value.blue { color: #58a6ff; }
  .value.orange { color: #d29922; }
  .bar-bg { background: #21262d; border-radius: 4px; height: 8px; margin-top: 8px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 2s ease; }
  .bar-fill.green { background: linear-gradient(90deg, #2ea043, #3fb950); }
  .bar-fill.blue { background: linear-gradient(90deg, #1f6feb, #58a6ff); }
  .footer { text-align: center; color: #484f58; font-size: 12px; margin-top: 24px; }
  .recent { font-size: 32px; font-weight: 700; }
  .recent.green { color: #3fb950; }
  .updated { font-size: 12px; color: #484f58; text-align: right; margin-top: 4px; }
  @media (prefers-color-scheme: light) {
    body { background: #ffffff; color: #24292f; }
    h1 { color: #0969da; }
    .card { background: #f6f8fa; border-color: #d0d7de; }
    .card h2 { color: #57606a; }
    .label { color: #24292f; }
    .value { color: #24292f; }
    .stat-row + .stat-row { border-color: #d0d7de; }
    .bar-bg { background: #d0d7de; }
    .footer { color: #8c959f; }
    .updated { color: #8c959f; }
  }
</style>
</head>
<body>
<h1>翻译进度监控</h1>
<div class="grid">
  <div class="card">
    <h2>T5 法律翻译</h2>
    <div class="stat-row">
      <span class="label">进度</span>
      <span class="value" id="t5-pct">--</span>
    </div>
    <div class="bar-bg">
      <div class="bar-fill green" id="t5-bar" style="width:0%"></div>
    </div>
    <div class="stat-row">
      <span class="label">完成</span>
      <span class="value green" id="t5-done">--</span>
    </div>
    <div class="stat-row">
      <span class="label">条文</span>
      <span class="value blue" id="t5-articles">--</span>
    </div>
  </div>
  <div class="card">
    <h2>指导案例翻译</h2>
    <div class="stat-row">
      <span class="label">进度</span>
      <span class="value" id="gc-pct">--</span>
    </div>
    <div class="bar-bg">
      <div class="bar-fill blue" id="gc-bar" style="width:0%"></div>
    </div>
    <div class="stat-row">
      <span class="label">完成</span>
      <span class="value green" id="gc-done">--</span>
    </div>
    <div class="stat-row">
      <span class="label">待翻译</span>
      <span class="value orange" id="gc-pending">--</span>
    </div>
    <div class="stat-row">
      <span class="label">剩余字符</span>
      <span class="value orange" id="gc-remaining-chars">--</span>
    </div>
  </div>
  <div class="card">
    <h2>近5分钟翻译量</h2>
    <div class="stat-row">
      <span class="label">字符数</span>
      <span class="value recent green" id="recent-chars">--</span>
    </div>
    <div class="stat-row">
      <span class="label">文件数</span>
      <span class="value blue" id="recent-files">--</span>
    </div>
    <div class="stat-row">
      <span class="label">速率</span>
      <span class="value orange" id="recent-rate">--</span>
    </div>
    <div class="stat-row">
      <span class="label">预计剩余</span>
      <span class="value" id="eta-display">--</span>
    </div>
  </div>
</div>
<div class="updated" id="updated">加载中...</div>
<div class="footer">5分钟自动刷新</div>
<script>
function fmt(n) { return n.toLocaleString('zh-CN'); }
function update() {
  fetch('/api/status').then(r => r.json()).then(d => {
    const t5 = d.t5;
    const t5pct = t5.total > 0 ? (t5.done / t5.total * 100) : 0;
    document.getElementById('t5-pct').textContent = t5pct.toFixed(1) + '%';
    document.getElementById('t5-bar').style.width = t5pct + '%';
    document.getElementById('t5-done').textContent = fmt(t5.done) + ' / ' + fmt(t5.total) + ' 部';
    document.getElementById('t5-articles').textContent = fmt(t5.done_articles) + ' / ' + fmt(t5.total_articles) + ' 条';

    const gc = d.gongbao;
    const gcpct = gc.total > 0 ? (gc.done / gc.total * 100) : 0;
    document.getElementById('gc-pct').textContent = gcpct.toFixed(1) + '%';
    document.getElementById('gc-bar').style.width = gcpct + '%';
    document.getElementById('gc-done').textContent = fmt(gc.done) + ' / ' + fmt(gc.total) + ' 篇';
    document.getElementById('gc-pending').textContent = fmt(gc.total - gc.done) + ' 篇';
    const eta = d.eta;
    document.getElementById('gc-remaining-chars').textContent = fmt(eta.gc_remaining_chars) + ' 字';

    document.getElementById('recent-chars').textContent = fmt(d.recent_chars) + ' 字';
    document.getElementById('recent-files').textContent = d.recent_files + ' 篇';
    const rate = d.recent_chars / 300;
    document.getElementById('recent-rate').textContent = rate.toFixed(0) + ' 字/秒';
    const etaSec = eta.eta_seconds;
    if (etaSec > 0) {
      const hours = Math.floor(etaSec / 3600);
      const mins = Math.floor((etaSec % 3600) / 60);
      document.getElementById('eta-display').textContent = hours + 'h ' + mins + 'm';
    } else {
      document.getElementById('eta-display').textContent = '计算中...';
    }

    document.getElementById('updated').textContent = '更新于 ' + new Date(d.timestamp * 1000).toLocaleTimeString('zh-CN');
  }).catch(e => {
    document.getElementById('updated').textContent = '连接失败: ' + e.message;
  });
}
update();
setInterval(update, 300000);
</script>
</body>
</html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            t5 = count_t5_progress()
            gc = count_gongbao_progress()
            recent_chars, recent_files = count_recent_chars(LAST_N_MINUTES)
            eta = estimate_remaining(t5, gc, recent_chars, LAST_N_MINUTES * 60)
            data = {
                't5': t5,
                'gongbao': gc,
                'recent_chars': recent_chars,
                'recent_files': recent_files,
                'eta': eta,
                'timestamp': int(time.time()),
            }
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(index_html.encode())

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
    print(f'Status server at http://localhost:{PORT}')
    server.serve_forever()
