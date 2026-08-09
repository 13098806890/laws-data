#!/usr/bin/env python3
"""
一次性修复：把 json_en/*.json 内嵌的 law_id 更新为权威值。

权威值由 law_id_registry 解析（blocklist 文件名优先，否则保留 law_index 中
存在的 id）。孤儿文件（无权威 id）会打印出来，由用户决定保留/删除。

用法:
  python3 scripts/fix_json_en_law_ids.py --dry-run   # 只报告不修改
  python3 scripts/fix_json_en_law_ids.py             # 实际修改
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import law_id_registry as lid

JSON_EN_DIR = Path(__file__).parent.parent / "json_en"


def main():
    parser = argparse.ArgumentParser(description="Fix law_id in json_en files to authoritative values")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't modify")
    args = parser.parse_args()

    changed = 0
    unchanged = 0
    orphans = []
    for cat_dir in sorted(JSON_EN_DIR.iterdir()):
        if not cat_dir.is_dir():
            continue
        for fpath in sorted(cat_dir.glob("*.json")):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"  ⚠ parse error: {fpath} — {e}")
                continue
            if not isinstance(data, dict) or "law_id" not in data:
                continue
            embedded = data.get("law_id")
            authoritative = lid.resolve_law_id(fpath.name, embedded)
            if authoritative is None:
                orphans.append((fpath, embedded))
                continue
            if authoritative != embedded:
                if not args.dry_run:
                    data["law_id"] = authoritative
                    fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                changed += 1
            else:
                unchanged += 1

    print(f"json_en 文件: {changed} 个 law_id 已更新" + ("（dry-run，未写盘）" if args.dry_run else ""))
    print(f"已一致: {unchanged} 个")
    if orphans:
        print(f"\n⚠ 孤儿文件（无权威 law_id）: {len(orphans)} 个")
        for fpath, embedded in orphans[:15]:
            print(f"  {fpath.relative_to(JSON_EN_DIR.parent)}  (law_id={embedded})")

    sys.exit(1 if orphans else 0)


if __name__ == "__main__":
    main()
