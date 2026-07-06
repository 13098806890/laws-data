#!/usr/bin/env python3
"""轻量监控服务器 — 不扫 json_en 文件，只解析日志。
用法：
  python3 scripts/status_light.py [--port 8080]
"""

import json
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn

LOOP_LOG = "/tmp/t4_loop.log"
TRANS_LOG = "/tmp/t4_translation.log"
POLL = 5
broadcast_queue = queue.Queue()
previous = ""


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True


def parse_logs():
    current_law = ""
    current_idx = 0
    current_total = 0
    run_count = 0
    last_dry_run = ""
    lines = []
    t4_done = t4_total = 0
    t4_pct = 0

    # Parse loop log for dry-run stats and run count
    try:
        text = Path(LOOP_LOG).read_text(encoding="utf-8", errors="replace")
        all_lines = text.strip().split("\n")
        lines = all_lines[-30:]
        # Find last dry-run output
        for line in reversed(all_lines):
            m = re.search(r'已完整翻译：(\d+) 部', line)
            if m:
                last_dry_run = line.strip()
                # Also extract other numbers from nearby lines
                break
        # Count runs
        for line in all_lines:
            m = re.match(r'第 (\d+) 轮启动', line)
            if m:
                run_count = int(m.group(1))
    except (FileNotFoundError, OSError):
        pass

    # Parse dry-run numbers from loop log context
    if last_dry_run:
        m = re.search(r'已完整翻译：(\d+) 部', last_dry_run)
        if m:
            t4_done = int(m.group(1))
    # Try to find total from nearby lines
    try:
        text = Path(LOOP_LOG).read_text(encoding="utf-8", errors="replace")
        # find "法律总数：458" type line
        for line in text.split("\n"):
            m = re.search(r'法律总数：(\d+) 部.*层级=T4', line)
            if m:
                t4_total = int(m.group(1))
                break
    except (FileNotFoundError, OSError):
        pass

    # If t4_total not found from loop log, try translating log
    if not t4_total:
        try:
            text = Path(TRANS_LOG).read_text(encoding="utf-8", errors="replace")
            for line in text.split("\n"):
                m = re.search(r'法律总数：(\d+) 部.*层级=T4', line)
                if m:
                    t4_total = int(m.group(1))
                    break
        except (FileNotFoundError, OSError):
            pass

    # Fallback total
    if not t4_total:
        t4_total = 458

    t4_pct = round(t4_done / t4_total * 100, 1) if t4_total else 0

    # Current law from translation log
    trans_lines = []
    try:
        text = Path(TRANS_LOG).read_text(encoding="utf-8", errors="replace")
        trans_lines = text.strip().split("\n")[-30:]
        for line in reversed(trans_lines):
            m = re.search(r'^\[(\d+)/(\d+)\]\s+(.+?)\s*（', line)
            if m:
                current_law = m.group(3)
                current_idx = int(m.group(1))
                current_total = int(m.group(2))
                break
    except (FileNotFoundError, OSError):
        pass

    # Running check
    r = subprocess.run(
        ["pgrep", "-f", "translate_to_en|translate_loop"],
        capture_output=True, text=True, timeout=5
    )
    running = bool(r.stdout.strip())

    # Batch size
    batch_size = None
    for log_file in [LOOP_LOG, TRANS_LOG]:
        try:
            text = Path(log_file).read_text(encoding="utf-8", errors="replace")
            for line in text.split("\n"):
                m = re.search(r'--batch-size\s+(\d+)', line)
                if m:
                    batch_size = int(m.group(1))
        except (FileNotFoundError, OSError):
            pass

    return {
        "running": running,
        "current_law": current_law,
        "current_idx": current_idx,
        "current_total": current_total,
        "t4_done": t4_done,
        "t4_total": t4_total,
        "t4_pct": t4_pct,
        "batch_size": batch_size,
        "run_count": run_count,
        "log_lines": lines[-20:] + trans_lines[-5:],
    }


def get_lan_ip():
    r = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=3)
    for m in re.finditer(r'inet (\d+\.\d+\.\d+\.\d+)', r.stdout):
        ip = m.group(1)
        if not ip.startswith("127."):
            return ip
    return "unknown"


def poll():
    global previous
    lan_ip = get_lan_ip()
    while True:
        try:
            s = parse_logs()
            s["lan_ip"] = lan_ip
            data = json.dumps(s, ensure_ascii=False)
            if data != previous:
                previous = data
                broadcast_queue.put(data)
        except Exception as e:
            broadcast_queue.put(json.dumps({"error": str(e)}))
        time.sleep(POLL)


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0,maximum-scale=1.0,user-scalable=no">
<title>T4 翻译</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:16px;max-width:700px;margin:auto}
h1{font-size:18px;font-weight:600;margin-bottom:12px;color:#f0f6fc}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin-bottom:10px}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;flex-shrink:0;margin-right:8px}
.dot.green{background:#3fb950;box-shadow:0 0 6px #3fb950}
.dot.red{background:#f85149;animation:pulse 1.5s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px}
.item{}
.item .l{font-size:11px;color:#8b949e}
.item .v{font-size:20px;font-weight:600}
.item .v.green{color:#3fb950}
.item .v.yellow{color:#d29922}
.item .v.blue{color:#58a6ff}
.bar-bg{background:#21262d;border-radius:10px;height:18px;overflow:hidden;margin:6px 0 2px}
.bar-fill{height:100%;border-radius:10px;transition:width 1s ease;background:linear-gradient(90deg,#2ea043,#3fb950)}
.bar-label{font-size:11px;color:#8b949e;text-align:center;margin-bottom:10px}
.info{font-size:11px;color:#8b949e;display:grid;grid-template-columns:1fr 1fr;gap:4px}
.info span{color:#c9d1d9}
.log{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px;margin-top:10px}
.log h2{font-size:12px;color:#8b949e;margin-bottom:6px}
.log pre{font-family:"SF Mono","Fira Code",monospace;font-size:10px;line-height:1.4;color:#8b949e;white-space:pre-wrap;word-break:break-all;max-height:320px}
</style>
</head>
<body>
<h1>T4 翻译进度</h1>
<div class="card">
  <div style="display:flex;align-items:center;margin-bottom:8px">
    <span class="dot red" id="dot"></span>
    <span style="font-weight:500" id="statusLabel">连接中...</span>
  </div>
  <div class="info">
    <div>轮次：<span id="runCount">-</span></div>
    <div>Batch：<span id="batchSize">-</span></div>
    <div>PID：<span id="pidInfo">-</span></div>
    <div>手机：<span id="lanIp">-</span></div>
  </div>
</div>
<div class="grid">
  <div class="item"><div class="l">已翻译</div><div class="v green" id="done">-</div></div>
  <div class="item"><div class="l">剩余</div><div class="v yellow" id="remain">-</div></div>
  <div class="item"><div class="l">总计</div><div class="v blue" id="total">-</div></div>
  <div class="item"><div class="l">进度</div><div class="v" id="pct">-</div></div>
</div>
<div class="bar-label" id="barLabel">加载中...</div>
<div class="bar-bg"><div class="bar-fill" id="bar" style="width:0%"></div></div>
<div class="card">
  <div style="font-size:12px;color:#8b949e;margin-bottom:4px">正在翻译</div>
  <div style="font-size:15px;font-weight:500;margin-bottom:4px" id="currentLaw">-</div>
  <div style="font-size:11px;color:#8b949e" id="currentPos">-</div>
</div>
<div class="log">
  <h2>日志</h2>
  <pre id="logContent">等待数据...</pre>
</div>
<script>
let prevLog="";
const evt=new EventSource("/events");
evt.onmessage=e=>{
  const s=JSON.parse(e.data);
  const el=id=>document.getElementById(id);
  el("dot").className="dot "+(s.running?"green":"red");
  el("statusLabel").textContent=s.running?"运行中":"已停止";
  el("runCount").textContent=s.run_count||"-";
  el("batchSize").textContent=s.batch_size?s.batch_size+" 条/批":"-";
  el("lanIp").textContent=s.lan_ip||"-";
  el("done").textContent=s.t4_done;
  el("remain").textContent=s.t4_total-s.t4_done;
  el("total").textContent=s.t4_total;
  el("pct").textContent=s.t4_pct+"%";
  el("barLabel").textContent="T4: "+s.t4_done+" / "+s.t4_total+" ("+s.t4_pct+"%)";
  el("bar").style.width=Math.min(s.t4_pct,100)+"%";
  el("currentLaw").textContent=s.current_law||"(等待中)";
  el("currentPos").textContent=s.current_idx?"["+s.current_idx+"/"+s.current_total+"]":"";
  const ls=(s.log_lines||[]).join("\n");
  if(ls!==prevLog){el("logContent").textContent=ls||"(无日志)";prevLog=ls}
};
evt.onerror=()=>{document.getElementById("statusLabel").textContent="断开"};
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
            self.wfile.write(HTML.encode("utf-8"))

    def log_message(self, *a):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    t = threading.Thread(target=poll, daemon=True)
    t.start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    ip = get_lan_ip()
    print(f"监控 → http://localhost:{port}")
    print(f"手机 → http://{ip}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("停止")


if __name__ == "__main__":
    main()
