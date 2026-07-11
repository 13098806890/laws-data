#!/usr/bin/env python3
"""HTTP status server for translate_to_en.py monitoring."""

import http.server
import json
import os
import re
import time
from collections import deque
from pathlib import Path

JSON_EN_DIR = Path(__file__).parent.parent / 'json_en'
DB_PATH = str(Path(__file__).parent.parent / 'law_content.db')
LOG_PATH = '/tmp/translation.log'
PORT = int(os.environ.get('STATUS_PORT', '8080'))

# Track recent completions for speed calculation
_recent_timestamps: deque = deque(maxlen=200)

def read_log():
    """Parse translate_to_en.py log for current state."""
    if not os.path.exists(LOG_PATH):
        return {'phase': None, 'title_progress': None, 'article_progress': None, 'recent_lines': []}

    try:
        with open(LOG_PATH) as f:
            lines = f.readlines()
    except Exception:
        return {'phase': None, 'title_progress': None, 'article_progress': None, 'recent_lines': []}

    state = {
        'phase': None,
        'title_progress': None,
        'article_progress': None,
        'total_laws': None,
        'current_law': None,
        'current_threads': [],
        'recent_lines': lines[-20:],
        'errors': [],
    }

    for line in lines:
        line = line.rstrip()

        # Phase detection
        m = re.search(r'待翻译标题：(\d+) 个', line)
        if m:
            state['phase'] = 'titles'
            state['title_total'] = int(m.group(1))

        m = re.search(r'待翻译法律：(\d+) 部', line)
        if m:
            state['article_total_laws'] = int(m.group(1))

        # Title progress: "标题：550/752"
        m = re.search(r'标题：(\d+)/(\d+)', line)
        if m:
            state['title_done'] = int(m.group(1))
            state['title_total'] = int(m.group(2))
            state['phase'] = 'titles'

        # Phase 2 started
        if '待翻译法律：' in line:
            state['phase'] = 'articles'

        # Article progress: "[5/13] Law Name（N条待翻译..."
        m = re.search(r'\[(\d+)/(\d+)\]\s+(.*)（(\d+) 条待翻译', line)
        if m:
            state['phase'] = 'articles'
            state['article_done'] = int(m.group(1))
            state['article_total_laws'] = int(m.group(2))
            state['current_law'] = m.group(3).strip()[:60]
            state['current_articles'] = int(m.group(4))
            _recent_timestamps.append(time.time())

        # Parse law detail: "引用 X 部法律，Y 个术语注入"
        m = re.search(r'引用 (\d+) 部法律，(\d+) 个术语注入', line)
        if m:
            state['ref_laws'] = int(m.group(1))
            state['glossary_terms'] = int(m.group(2))

        # Batch start: "批次 1/3 完成（Xs，Y条）"
        m = re.search(r'批次 (\d+)/(\d+) 完成（(\d+)s，(\d+)条）', line)
        if m:
            state['current_batch'] = f'{m.group(1)}/{m.group(2)}'
            state['batch_seconds'] = int(m.group(3))
            state['batch_articles'] = int(m.group(4))
            _recent_timestamps.append(time.time())

        # Law completed: "已写回 filename.json"
        if '已写回' in line:
            state['last_completed'] = state.get('current_law', '')

        # Batch error
        m = re.search(r'批次 (\d+)/(\d+) 失败（已重试\d+次）', line)
        if m:
            state['errors'].append(line[-80:])

        # API retry
        if '重试' in line and '批次' not in line:
            state['errors'].append(line[-80:])

    # Infer pending article count
    if state.get('article_total_laws') and state.get('article_done'):
        state['article_pending_laws'] = state['article_total_laws'] - state['article_done']
    else:
        state['article_pending_laws'] = None

    return state


def count_json_en_progress():
    """Count total json_en/司法解释/ files with content_en."""
    sfjs_dir = JSON_EN_DIR / '司法解释'
    if not sfjs_dir.exists():
        return {'files': 0, 'with_content': 0, 'without_content': 0}

    total = 0
    with_content = 0
    without_content = 0
    for f in sfjs_dir.glob('*.json'):
        total += 1
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            arts = d.get('articles', [])
            has = any(a.get('content_en', '').strip() for a in arts)
            if has:
                with_content += 1
            else:
                without_content += 1
        except Exception:
            without_content += 1
    return {'files': total, 'with_content': with_content, 'without_content': without_content}


def calc_speed(window=120):
    """Calculate translation speed (laws/min) from recent completions."""
    now = time.time()
    cutoff = now - window
    recent = [t for t in _recent_timestamps if t > cutoff]
    if len(recent) < 2:
        return 0
    return len(recent) / (window / 60)


def count_overall():
    """Count total translation progress across all 司法解释（FLK + gongbao）。"""
    sfjs_dir = JSON_EN_DIR / '司法解释'
    if not sfjs_dir.exists():
        return {'total': 0, 'done': 0, 'articles_done': 0, 'articles_total': 0}

    total = 0
    done = 0
    articles_done = 0
    articles_total = 0
    for f in sfjs_dir.glob('*.json'):
        total += 1
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            arts = d.get('articles', [])
            if not arts:
                continue
            articles_total += len(arts)
            has_en = sum(1 for a in arts if a.get('content_en', '').strip())
            articles_done += has_en
            if has_en == len(arts):
                done += 1
        except Exception:
            pass

    # Total laws to translate: all flk 司法解释 + all gongbao 司法解释
    try:
        import sqlite3
        conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
        total_laws = conn.execute(
            "SELECT COUNT(*) FROM laws WHERE category='司法解释' AND is_current=1"
        ).fetchone()[0]
        conn.close()
    except Exception:
        total_laws = total

    pending = total_laws - done
    return {
        'total_laws': total_laws,
        'done': done,
        'pending': max(0, pending),
        'articles_done': articles_done,
        'articles_total': articles_total,
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
  h2 { font-size: 14px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
  .stat-row { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 0; }
  .stat-row + .stat-row { border-top: 1px solid #21262d; }
  .label { font-size: 14px; color: #c9d1d9; }
  .value { font-size: 20px; font-weight: 600; color: #f0f6fc; font-variant-numeric: tabular-nums; }
  .value.green { color: #3fb950; }
  .value.blue { color: #58a6ff; }
  .value.orange { color: #d29922; }
  .value.red { color: #f85149; }
  .bar-bg { background: #21262d; border-radius: 4px; height: 8px; margin-top: 8px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 2s ease; }
  .bar-fill.green { background: linear-gradient(90deg, #2ea043, #3fb950); }
  .bar-fill.blue { background: linear-gradient(90deg, #1f6feb, #58a6ff); }
  .footer { text-align: center; color: #484f58; font-size: 12px; margin-top: 24px; }
  .updated { font-size: 12px; color: #484f58; text-align: right; margin-top: 4px; }
  .log-box { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12px; line-height: 1.5; max-height: 300px; overflow-y: auto; margin-bottom: 24px; }
  .log-box .err { color: #f85149; }
  .log-box .ok { color: #3fb950; }
  .log-box .info { color: #8b949e; }
  @media (prefers-color-scheme: light) {
    body { background: #ffffff; color: #24292f; }
    h1 { color: #0969da; }
    h2 { color: #57606a; }
    .card { background: #f6f8fa; border-color: #d0d7de; }
    .label { color: #24292f; }
    .value { color: #24292f; }
    .stat-row + .stat-row { border-color: #d0d7de; }
    .bar-bg { background: #d0d7de; }
    .footer { color: #8c959f; }
    .updated { color: #8c959f; }
    .log-box { background: #f6f8fa; border-color: #d0d7de; }
    .log-box .err { color: #cf222e; }
    .log-box .ok { color: #116329; }
    .log-box .info { color: #656d76; }
  }
</style>
</head>
<body>
<h1>翻译进度监控</h1>
<div class="grid">
  <div class="card">
    <h2>当前阶段</h2>
    <div class="stat-row">
      <span class="label">阶段</span>
      <span class="value" id="phase">--</span>
    </div>
    <div class="stat-row">
      <span class="label">正在翻译</span>
      <span class="value blue" id="current-law" style="font-size:13px;">--</span>
    </div>
    <div class="stat-row">
      <span class="label">批次进度</span>
      <span class="value" id="batch-progress" style="font-size:16px;">--</span>
    </div>
    <div class="stat-row">
      <span class="label">引用/术语</span>
      <span class="value orange" id="ref-terms" style="font-size:14px;">--</span>
    </div>
    <div class="stat-row">
      <span class="label">速率</span>
      <span class="value orange" id="speed">--</span>
    </div>
    <div class="stat-row">
      <span class="label">上一步完成</span>
      <span class="value" id="last-completed" style="font-size:13px;color:#8b949e;">--</span>
    </div>
  </div>
  <div class="card">
    <h2>总体进度（司法解释）</h2>
    <div class="stat-row">
      <span class="label">总进度</span>
      <span class="value" id="overall-pct">--</span>
    </div>
    <div class="bar-bg">
      <div class="bar-fill blue" id="overall-bar" style="width:0%"></div>
    </div>
    <div class="stat-row">
      <span class="label">已完成</span>
      <span class="value green" id="overall-done">--</span>
    </div>
    <div class="stat-row">
      <span class="label">待翻译</span>
      <span class="value orange" id="overall-pending">--</span>
    </div>
    <div class="stat-row">
      <span class="label">条文进度</span>
      <span class="value blue" id="overall-articles">--</span>
    </div>
  </div>
  <div class="card">
    <h2 id="progress-title">当前阶段进度</h2>
    <div class="stat-row">
      <span class="label">进度</span>
      <span class="value" id="pct">--</span>
    </div>
    <div class="bar-bg">
      <div class="bar-fill green" id="bar" style="width:0%"></div>
    </div>
    <div class="stat-row">
      <span class="label">已完成</span>
      <span class="value green" id="done">--</span>
    </div>
    <div class="stat-row">
      <span class="label">待处理</span>
      <span class="value orange" id="pending">--</span>
    </div>
    <div class="stat-row">
      <span class="label">json_en 文件数</span>
      <span class="value blue" id="files-total">--</span>
    </div>
    <div class="stat-row">
      <span class="label">含翻译内容</span>
      <span class="value green" id="files-with">--</span>
    </div>
  </div>
</div>

<h2>实时日志</h2>
<div class="log-box" id="log">
  <div class="info">等待数据...</div>
</div>

<div class="updated" id="updated">加载中...</div>
<div class="footer">5秒自动刷新</div>

<script>
function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function fmt(n) { return n.toLocaleString('zh-CN'); }

function update() {
  fetch('/api/status').then(r => r.json()).then(d => {
    const log = d.log;
    const phase = log.phase;
    const isTitles = phase === 'titles';

    // Phase
    document.getElementById('phase').textContent = isTitles ? '📝 标题翻译' : phase === 'articles' ? '📄 条文翻译' : '⏳ 等待中';
    document.getElementById('current-law').textContent = log.current_law || '--';
    document.getElementById('batch-progress').textContent = log.current_batch ? '批次 ' + log.current_batch + '（' + (log.batch_articles||'?') + ' 条，' + (log.batch_seconds||'?') + 's）' : '--';
    document.getElementById('ref-terms').textContent = (log.ref_laws != null ? log.ref_laws + ' 部法律' : '--') + ' / ' + (log.glossary_terms != null ? log.glossary_terms + ' 个术语' : '--');
    document.getElementById('last-completed').textContent = log.last_completed || '--';

    // Speed
    const speed = d.speed.toFixed(1);
    document.getElementById('speed').textContent = speed + ' 部/分';

    // Progress
    if (isTitles) {
      const done = log.title_done || 0;
      const total = log.title_total || 1;
      const pct = (done / total * 100);
      document.getElementById('progress-title').textContent = '标题翻译';
      document.getElementById('pct').textContent = pct.toFixed(1) + '%';
      document.getElementById('bar').style.width = pct + '%';
      document.getElementById('done').textContent = fmt(done) + ' / ' + fmt(total);
      document.getElementById('pending').textContent = fmt(total - done);
    } else if (phase === 'articles') {
      const done = log.article_done || 0;
      const total = log.article_total_laws || 1;
      const pct = (done / total * 100);
      document.getElementById('progress-title').textContent = '条文翻译（按法律数）';
      document.getElementById('pct').textContent = pct.toFixed(1) + '%';
      document.getElementById('bar').style.width = pct + '%';
      document.getElementById('done').textContent = fmt(done) + ' / ' + fmt(total);
      document.getElementById('pending').textContent = fmt(total - done);
    } else {
      document.getElementById('progress-title').textContent = '等待开始...';
      document.getElementById('pct').textContent = '--';
      document.getElementById('bar').style.width = '0%';
      document.getElementById('done').textContent = '--';
      document.getElementById('pending').textContent = '--';
    }

    // Overall
    const ov = d.overall;
    const ovPct = ov.total_laws > 0 ? (ov.done / ov.total_laws * 100) : 0;
    document.getElementById('overall-pct').textContent = ovPct.toFixed(1) + '%';
    document.getElementById('overall-bar').style.width = ovPct + '%';
    document.getElementById('overall-done').textContent = fmt(ov.done) + ' / ' + fmt(ov.total_laws) + ' 部';
    document.getElementById('overall-pending').textContent = fmt(ov.pending) + ' 部';
    document.getElementById('overall-articles').textContent = fmt(ov.articles_done) + ' / ' + fmt(ov.articles_total) + ' 条';

    // Files
    const files = d.files;
    document.getElementById('files-total').textContent = fmt(files.files);
    document.getElementById('files-with').textContent = fmt(files.with_content);

    // Log
    const logEl = document.getElementById('log');
    logEl.innerHTML = log.recent_lines.map(line => {
      const cls = line.includes('失败') || line.includes('重试') ? 'err'
                : line.includes('完成') || line.includes('✓') ? 'ok'
                : 'info';
      return '<div class="' + cls + '">' + escapeHtml(line) + '</div>';
    }).join('');
    logEl.scrollTop = logEl.scrollHeight;

    document.getElementById('updated').textContent = '更新于 ' + new Date(d.timestamp * 1000).toLocaleTimeString('zh-CN');
  }).catch(e => {
    document.getElementById('updated').textContent = '连接失败: ' + e.message;
  });
}

update();
setInterval(update, 5000);
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
            log = read_log()
            files = count_json_en_progress()
            overall = count_overall()
            speed = calc_speed()
            data = {
                'log': log,
                'files': files,
                'overall': overall,
                'speed': speed,
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
