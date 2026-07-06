#!/usr/bin/env python3
"""Real-time T4 translation dashboard with SSE.
Usage:
  python3 scripts/status_server.py [--port 8080]
Open http://localhost:8080 (or http://<lan-ip>:8080 from phone)
"""

import json
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn

DB_PATH = Path(__file__).resolve().parent.parent / "law_content.db"
JSON_DIR = Path(__file__).resolve().parent.parent / "json"
JSON_EN_DIR = Path(__file__).resolve().parent.parent / "json_en"
LOG_PATH = "/tmp/t4_translation.log"
POLL_INTERVAL = 3

broadcast_queue = queue.Queue()
previous = ""

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True


def get_translate_pid():
    r = subprocess.run(
        ["pgrep", "-f", "translate_to_en.py"],
        capture_output=True, text=True, timeout=5
    )
    for p in r.stdout.strip().split():
        p = p.strip()
        if p:
            return p
    return None


def get_process_start_time(pid):
    if not pid:
        return None
    r = subprocess.run(
        ["ps", "-o", "lstart=", "-p", pid],
        capture_output=True, text=True, timeout=3
    )
    return r.stdout.strip()


def read_json_en_counts():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT id, filename, category, title FROM laws WHERE is_current=1"
    ).fetchall()
    conn.close()

    conn2 = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cited = dict(conn2.execute(
        "SELECT to_law_id, COUNT(*) FROM article_references GROUP BY to_law_id"
    ).fetchall())
    conn2.close()

    tier_bounds = {
        "T0": (50, 99999), "T1": (20, 50), "T2": (10, 20),
        "T3": (5, 10), "T4": (1, 5), "T5": (0, 1),
    }
    tiers = {t: {"total": 0, "done": 0} for t in tier_bounds}
    t4_laws_info = []

    for law_id, filename, category, title in rows:
        refs = cited.get(law_id, 0)
        for t, (lo, hi) in tier_bounds.items():
            if lo <= refs < hi:
                tiers[t]["total"] += 1
                en_path = JSON_EN_DIR / category / f"{filename}.json"
                try:
                    data = json.loads(en_path.read_text(encoding="utf-8"))
                    arts = data.get("articles", [])
                    if not arts:
                        tiers[t]["done"] += 1
                    elif all(a.get("content_en", "").strip() for a in arts):
                        tiers[t]["done"] += 1
                    elif t == "T4":
                        # Store incomplete T4 law for detail
                        missing = sum(1 for a in arts if not a.get("content_en", "").strip())
                        cn_path = JSON_DIR / category / f"{filename}.json"
                        cn_arts = 0
                        if cn_path.exists():
                            cn_data = json.loads(cn_path.read_text(encoding="utf-8"))
                            cn_arts = len([
                                1 for pt in cn_data.get("parts", [])
                                for ch in pt.get("chapters", [])
                                for sec in ch.get("sections", [])
                                for _ in sec.get("articles", [])
                            ]) or len([
                                1 for ch in cn_data.get("chapters", [])
                                for sec in ch.get("sections", [])
                                for _ in sec.get("articles", [])
                            ])
                        t4_laws_info.append({
                            "title": title,
                            "done": len(arts) - missing,
                            "total": len(arts),
                        })
                except Exception:
                    pass
                break

    return tiers, t4_laws_info


def parse_log():
    lines = []
    current_law = ""
    current_idx = 0
    current_total = 0
    current_articles = 0
    start_time = None
    try:
        text = Path(LOG_PATH).read_text(encoding="utf-8", errors="replace")
        lines = text.strip().split("\n")

        # Find first relevant line for start time
        for line in lines:
            m = re.search(r'^\[(\d+)/(\d+)\]', line)
            if m:
                start_time = lines[0]  # first log line
                break

        recent = lines[-40:]
        for line in reversed(lines):
            m = re.search(
                r'^\[(\d+)/(\d+)\]\s+(.+?)\s*（(\d+)\s*条',
                line,
            )
            if m:
                current_law = m.group(3)
                current_idx = int(m.group(1))
                current_total = int(m.group(2))
                break
        # Count articles in current law from log
        for line in reversed(lines):
            m = re.search(r'（(\d+)\s*条', line)
            if m and current_law and current_law in line:
                current_articles = int(m.group(1))
                break
    except (FileNotFoundError, OSError):
        pass
    return recent, current_law, current_idx, current_total, current_articles


def get_lan_ip():
    r = subprocess.run(
        ["ifconfig"],
        capture_output=True, text=True, timeout=3
    )
    for m in re.finditer(r'inet (\d+\.\d+\.\d+\.\d+)', r.stdout):
        ip = m.group(1)
        if not ip.startswith("127."):
            return ip
    return "unknown"


# ── HTML ──
SSE_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>T4 翻译进度</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:16px;max-width:800px;margin:auto}
h1{font-size:18px;font-weight:600;margin-bottom:12px;color:#f0f6fc}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin-bottom:10px}
.row{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;flex-shrink:0}
.dot.green{background:#3fb950;box-shadow:0 0 6px #3fb950}
.dot.red{background:#f85149;animation:pulse 1.5s infinite}
.dot.yellow{background:#d29922}
.dot.gray{background:#8b949e}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:10px;font-weight:500}
.badge.green{background:#2ea04333;color:#3fb950;border:1px solid #2ea043}
.badge.red{background:#f8514933;color:#f85149;border:1px solid #f85149}
.badge.yellow{background:#d2992233;color:#d29922;border:1px solid #d29922}
.badge.gray{background:#8b949e33;color:#8b949e;border:1px solid #8b949e}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
.stat-item .l{font-size:11px;color:#8b949e}
.stat-item .v{font-size:18px;font-weight:600;margin-top:1px}
.stat-item .v.green{color:#3fb950}
.stat-item .v.yellow{color:#d29922}
.stat-item .v.blue{color:#58a6ff}
.bar-wrap{background:#21262d;border-radius:10px;height:18px;overflow:hidden;margin:6px 0 2px}
.bar-fill{height:100%;border-radius:10px;transition:width 1s ease}
.bar-fill.t4{background:linear-gradient(90deg,#2ea043,#3fb950)}
.bar-label{font-size:11px;color:#8b949e;text-align:center;margin-bottom:10px}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px;color:#8b949e}
.info-grid span{color:#c9d1d9}
.section-title{font-size:12px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin:12px 0 6px}
.log{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 14px}
.log h2{font-size:12px;color:#8b949e;margin-bottom:6px}
.log pre{font-family:"SF Mono","Fira Code",monospace;font-size:10px;line-height:1.5;color:#8b949e;overflow-x:auto;white-space:pre-wrap;word-break:break-all;max-height:300px}
.tier-grid{display:grid;gap:4px}
.tier-item{display:flex;justify-content:space-between;font-size:12px;padding:5px 8px;background:#21262d;border-radius:6px}
.tier-item .pct{font-weight:600}
.tier-item.full .pct{color:#3fb950}
.tier-item.partial .pct{color:#d29922}
.tier-item.empty .pct{color:#8b949e}
</style>
</head>
<body>

<h1>T4 翻译进度</h1>

<div class="card">
  <div class="row">
    <span class="dot red" id="dot"></span>
    <span style="font-weight:500" id="statusLabel">连接中...</span>
    <span class="badge" id="statusBadge"></span>
  </div>
  <div class="info-grid">
    <div>PID：<span id="pidInfo">-</span></div>
    <div>启动时间：<span id="startTime">-</span></div>
    <div>当前批次：<span id="batchSize">-</span></div>
    <div>局域网：<span id="lanIp">-</span></div>
  </div>
</div>

<div class="stat-grid">
  <div class="stat-item"><div class="l">T4 完成</div><div class="v green" id="t4Done">-</div></div>
  <div class="stat-item"><div class="l">T4 剩余</div><div class="v yellow" id="t4Remain">-</div></div>
  <div class="stat-item"><div class="l">T4 总计</div><div class="v blue" id="t4Total">-</div></div>
  <div class="stat-item"><div class="l">总完成</div><div class="v blue" id="allDone">-</div></div>
</div>

<div class="bar-label" id="t4BarLabel">-</div>
<div class="bar-wrap"><div class="bar-fill t4" id="t4Bar" style="width:0%"></div></div>

<div class="card">
  <div class="row">
    <div style="font-size:13px;color:#8b949e;flex-shrink:0">正在处理</div>
    <span class="badge" id="currentPos" style="margin-left:auto">-</span>
  </div>
  <div style="font-size:15px;font-weight:500;margin:6px 0" id="currentLaw">-</div>
  <div style="font-size:11px;color:#8b949e" id="currentArticles">-</div>
</div>

<div class="section-title">各层级进度</div>
<div class="card" style="padding:10px 14px">
  <div class="tier-grid" id="tierGrid"></div>
</div>

<div class="section-title">实时日志</div>
<div class="log">
  <h2>translate_to_en.py 输出（最近 40 行）</h2>
  <pre id="logContent">等待数据...</pre>
</div>

<script>
let prevLog="";
const evt=new EventSource("/events");
evt.onmessage=e=>{
  const s=JSON.parse(e.data);
  const el=i=>document.getElementById(i);
  const dot=el("dot");

  // Task status
  if(!s.running && s.all_done){dot.className="dot green";el("statusLabel").textContent="已完成";el("statusBadge").className="badge green";el("statusBadge").textContent="全部翻译完成"}
  else if(!s.running && s.t4_done>0){dot.className="dot yellow";el("statusLabel").textContent="已终止";el("statusBadge").className="badge yellow";el("statusBadge").textContent="T4 未完成"}
  else if(!s.running){dot.className="dot gray";el("statusLabel").textContent="未启动";el("statusBadge").className="badge gray";el("statusBadge").textContent="等待开始"}
  else {dot.className="dot green";el("statusLabel").textContent="运行中";el("statusBadge").className="badge green";el("statusBadge").textContent="T4 翻译中"}

  el("pidInfo").textContent=s.pid||"-";
  el("startTime").textContent=s.start_time||"-";
  el("batchSize").textContent=s.batch_size!=null?s.batch_size+" 条/批":"-";
  el("lanIp").textContent=s.lan_ip||"-";

  el("t4Done").textContent=s.t4_done;
  el("t4Remain").textContent=s.t4_total-s.t4_done;
  el("t4Total").textContent=s.t4_total;
  el("allDone").textContent=s.all_done;

  const pct=s.t4_pct||0;
  el("t4BarLabel").textContent="T4 进度："+s.t4_done+" / "+s.t4_total+" ("+pct+"%)";
  el("t4Bar").style.width=Math.min(pct,100)+"%";

  el("currentLaw").textContent=s.current_law||"(等待中)";
  el("currentPos").textContent=s.current_idx?"["+s.current_idx+"/"+s.current_total+"]":"-";
  el("currentArticles").textContent=s.current_articles?s.current_law+" — "+s.current_articles+" 条待翻译":"";
  el("currentPos").className="badge "+(s.running?"green":"gray");

  // Tier grid
  const tl={T0:"50+ 引用",T1:"20-50",T2:"10-20",T3:"5-10",T4:"1-5",T5:"0"};
  const ts=s.tiers||{};
  el("tierGrid").innerHTML=["T0","T1","T2","T3","T4","T5"].map(t=>{
    const d=ts[t]||{done:0,total:0};
    const p=d.total?(d.done/d.total*100).toFixed(1):0;
    const cls=d.total&&d.done===d.total?"full":(d.done>0?"partial":"empty");
    return '<div class="tier-item '+cls+'"><span>'+t+" ("+tl[t]+')</span><span class="pct">'+d.done+"/"+d.total+" ("+p+"%)</span></div>"
  }).join("");

  const ls=(s.log_lines||[]).join("\n");
  if(ls!==prevLog){const lc=el("logContent");lc.textContent=ls||"(无日志)";lc.scrollTop=lc.scrollHeight;prevLog=ls}
};
evt.onerror=()=>{document.getElementById("statusLabel").textContent="断开";document.getElementById("dot").className="dot red"};
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    data = broadcast_queue.get()
                    self.wfile.write(f"data: {data}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(SSE_HTML.encode("utf-8"))

    def log_message(self, *a):
        pass


def poll_status():
    global previous
    start_time_cache = None
    lan_ip = get_lan_ip()
    while True:
        try:
            pid = get_translate_pid()
            running = pid is not None

            # Process start time
            if running:
                st = get_process_start_time(pid)
                if st:
                    start_time_cache = st

            batch_size = None
            if pid:
                r = subprocess.run(
                    ["ps", "-p", pid, "-o", "args="],
                    capture_output=True, text=True, timeout=3
                )
                m = re.search(r'--batch-size\s+(\d+)', r.stdout)
                batch_size = int(m.group(1)) if m else None

            log_lines, current_law, current_idx, current_total, current_articles = parse_log()
            tiers, t4_incomplete = read_json_en_counts()

            t4 = tiers.get("T4", {})
            t4_done = t4.get("done", 0)
            t4_total = t4.get("total", 0)

            # All tiers done count
            all_done = sum(v["done"] for v in tiers.values())

            # Determine if translation is fully complete
            fully_done = not running and t4_total > 0 and t4_done >= t4_total

            status = json.dumps({
                "running": running,
                "fully_done": fully_done,
                "pid": pid,
                "start_time": start_time_cache or "",
                "batch_size": batch_size,
                "lan_ip": lan_ip,
                "current_law": current_law,
                "current_idx": current_idx,
                "current_total": current_total,
                "current_articles": current_articles,
                "t4_done": t4_done,
                "t4_total": t4_total,
                "t4_pct": round(t4_done / t4_total * 100, 1) if t4_total else 0,
                "all_done": all_done,
                "tiers": tiers,
                "t4_incomplete": t4_incomplete,
                "log_lines": log_lines,
            }, ensure_ascii=False)

            if status != previous:
                previous = status
                broadcast_queue.put(status)

        except Exception as e:
            broadcast_queue.put(json.dumps({"error": str(e)}, ensure_ascii=False))

        time.sleep(POLL_INTERVAL)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    t = threading.Thread(target=poll_status, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Dashboard → http://localhost:{port}")
    print(f"手机访问 → http://{get_lan_ip()}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped")


if __name__ == "__main__":
    main()
