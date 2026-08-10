#!/usr/bin/env python3
"""
scripts/agents/run.py — 多层专家协作法律问答系统入口

用法：
  cd path/to/laws_data
  python3 -m scripts.agents.run
  python3 -m scripts.agents.run -q "网购假货怎么维权"
  python3 -m scripts.agents.run -q "..." --provider deepseek
"""

import argparse
import sys
from pathlib import Path

# 确保 scripts/ 在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from .core.config import PROVIDERS, PROVIDER_STATE, DEFAULT_PROVIDER
from .coordinator import run

DEMO_QUESTIONS = [
    "网购假货商家不退款，我可以要求多少赔偿？",
    "公司拖欠工资三个月，试用期被辞退怎么办？",
    "房东在租期内要求涨租并赶人，我有什么权利？",
    "邻居家狗咬伤了我，怎么索赔？",
    "公司强制要求员工加班不给加班费，如何维权？",
]


def main():
    parser = argparse.ArgumentParser(description="多层专家协作法律问答系统")
    parser.add_argument("--question", "-q", type=str, default=None)
    parser.add_argument("--provider", "-p", type=str,
                        default=DEFAULT_PROVIDER, choices=list(PROVIDERS.keys()))
    parser.add_argument("--no-interactive", action="store_true")
    parser.add_argument("--all", action="store_true", help="跑所有演示问题")
    args = parser.parse_args()

    PROVIDER_STATE["current"] = args.provider

    if args.question:
        run(args.question, interactive=not args.no_interactive)
    elif args.all:
        for q in DEMO_QUESTIONS:
            run(q, interactive=False)
            print()
    else:
        print(f"多层专家协作法律问答系统  (provider: {args.provider})")
        print("输入问题后回车，输入 'q' 退出\n")
        while True:
            try:
                q = input("❓ ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n退出")
                break
            if not q or q.lower() in ('q', 'quit', 'exit'):
                break
            run(q, interactive=True)


if __name__ == "__main__":
    main()
