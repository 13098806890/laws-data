#!/usr/bin/env python3
"""Wrapper: 循环运行 translate_to_en.py --max-laws-per-run N，自动重启避免卡住。
用法：
  python3 scripts/translate_loop.py --max-per-run 50 [其他参数...]

所有额外参数透传给 translate_to_en.py。
"""

import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "translate_to_en.py"

# 透传参数，把 --max-per-run 转成 --max-laws-per-run
args = sys.argv[1:]
max_per_run = 50
filtered = []
i = 0
while i < len(args):
    if args[i] == '--max-per-run' and i + 1 < len(args):
        max_per_run = int(args[i + 1])
        i += 2
    elif args[i].startswith('--max-per-run='):
        max_per_run = int(args[i].split('=', 1)[1])
        i += 1
    else:
        filtered.append(args[i])
        i += 1

env = os.environ.copy()
run_count = 0

while True:
    run_count += 1
    print(f"\n{'='*60}")
    print(f"第 {run_count} 轮启动 — 每轮最多 {max_per_run} 部")
    print(f"{'='*60}")

    cmd = [sys.executable, '-u', str(SCRIPT)] + filtered + [
        '--max-laws-per-run', str(max_per_run)
    ]

    t0 = time.time()
    result = subprocess.run(cmd, env=env)
    elapsed = time.time() - t0
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    time_str = f"{hours}h{minutes:02d}m" if hours else f"{minutes}m"

    print(f"  进程退出码 {result.returncode}，耗时 {time_str}")

    # 检查是否全部翻译完成
    check = subprocess.run(
        [sys.executable, str(SCRIPT)] + filtered + ['--dry-run'],
        capture_output=True, text=True, env=env
    )
    print(check.stdout.strip())

    if "待翻译法律：0 部" in check.stdout or "待翻译法律：0" in check.stdout.split("共")[-1] if "共" in check.stdout else False:
        # 检查是否所有 pending 都为 0
        if "待翻译法律：0" in check.stdout or "共 0 条条文" in check.stdout:
            print("\n✅ 全部翻译完成！")
            break

    # 简要等待后继续
    time.sleep(2)

print(f"共运行 {run_count} 轮，任务结束。")
