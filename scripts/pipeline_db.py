#!/usr/bin/env python3
"""
一键重建 law_content.db 数据库并验证所有内容。

流程:
  0. 从 JSON 重建 laws 表（含 legal_domain、subject_area）
  1. 从 App bundle 复制 DB 到 laws-data（可选）
  2. 重建 gongbao_docs 表（含英文列）
  3. 导入法条英文翻译 (nodes.content_en)
  4. 运行所有验证
  5. 复制回 App bundle（可选）

用法:
  python3 scripts/pipeline_db.py                          # 完整流程（从 JSON 开始）
  python3 scripts/pipeline_db.py --skip-json-rebuild      # 跳过 JSON→DB 重建，仅跑 gongbao
  python3 scripts/pipeline_db.py --skip-copy-back         # 不拷回 App
  python3 scripts/pipeline_db.py --skip-gongbao           # 跳过 gongbao 重建
  python3 scripts/pipeline_db.py --skip-import-en         # 跳过英文导入
  python3 scripts/pipeline_db.py --validate-only          # 只跑验证
"""

import argparse
import subprocess
import sys
from pathlib import Path

LAWS_DATA = Path(__file__).parent.parent
SCRIPTS   = LAWS_DATA / "scripts"
APP_BUNDLE_DB = Path("/Users/doxie/Github/LawsSearch/ChineseLawsSearch/ChineseLawsSearch/law_content.db")
LAWS_DATA_DB  = LAWS_DATA / "law_content.db"


def run(cmd: str, cwd=None) -> bool:
    desc = cmd[:80] + ("…" if len(cmd) > 80 else "")
    print(f"\n  ▶ {desc}")
    result = subprocess.run(cmd, shell=True, cwd=cwd or LAWS_DATA)
    if result.returncode != 0:
        print(f"  ✗ FAILED (exit code {result.returncode})")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="One-click DB rebuild + validation")
    parser.add_argument("--skip-json-rebuild", action="store_true", help="Skip JSON→DB rebuild")
    parser.add_argument("--skip-copy-back", action="store_true", help="Skip copying DB back to App bundle")
    parser.add_argument("--skip-gongbao", action="store_true", help="Skip gongbao table rebuild")
    parser.add_argument("--skip-import-en", action="store_true", help="Skip English translation import")
    parser.add_argument("--validate-only", action="store_true", help="Only run validation, skip all builds")
    args = parser.parse_args()

    print("=" * 60)
    print("  DB PIPELINE — 一键重建 + 验证")
    print("=" * 60)

    if args.validate_only:
        print("  仅验证模式\n")

    # ── Step 0: Rebuild from JSON (laws table, legal_domain, subject_area) ──
    if not args.skip_json_rebuild and not args.validate_only:
        print("\n── Step 0/4: JSON → DB 重建（laws + legal_domain + subject_area）──")
        if not run(f"python3 -m json_to_db.builder", cwd=SCRIPTS):
            sys.exit(1)
        if not run(f"python3 -m json_to_db.export_menu", cwd=SCRIPTS):
            sys.exit(1)

    if not LAWS_DATA_DB.exists() and not args.validate_only:
        print(f"\n⚠  {LAWS_DATA_DB.name} 不存在，从 App bundle 复制中…（仅做 gongbao 重建时需要）")
        if APP_BUNDLE_DB.exists():
            run(f"cp '{APP_BUNDLE_DB}' '{LAWS_DATA_DB}'")
            print(f"  ✅ 已复制 ({APP_BUNDLE_DB.stat().st_size / 1024 / 1024:.0f}MB)")
        else:
            print(f"  ✗ App bundle DB 不存在: {APP_BUNDLE_DB}")
            sys.exit(1)

    # ── Step 1: Rebuild gongbao tables ────────────────────────────────
    if not args.skip_gongbao and not args.validate_only:
        print("\n── Step 1/4: 重建 gongbao 表（含英文列）──")
        if not run(f"python3 '{SCRIPTS / 'build_gongbao_db.py'}' --drop"):
            sys.exit(1)

    # ── Step 2: Import English translations ───────────────────────────
    if not args.skip_import_en and not args.validate_only:
        print("\n── Step 2/4: 导入法条英文翻译 (nodes.content_en) ──")
        if not run(f"python3 '{SCRIPTS / 'import_en.py'}'"):
            print("  ⚠ 部分法律可能有缺失，继续验证…")

    # ── Step 3: Classify gongbao entries (legal_domain) ──────────────────
    if not args.skip_gongbao and not args.validate_only:
        print("\n── Step 3/4: 司法解 legal_domain 分类 ──")
        run(f"python3 '{SCRIPTS / 'classify_gongbao_domain.py'}'")

    # ── Step 4: Validate ──────────────────────────────────────────────
    print("\n── Step 4/4: 验证 ──")

    # Gongbao validation
    print("\n  ── gongbao 验证 ──")
    ok = run(f"python3 '{SCRIPTS / 'verify_gongbao_db.py'}'")

    # content_en validation
    print("\n  ── 法条英文翻译验证 ──")
    en_ok = run(f"python3 '{SCRIPTS / 'validate_en.py'}'")

    # Quick FTS check
    print("\n  ── FTS 快速检查 ──")
    run(f"""python3 -c '
import sqlite3
db = sqlite3.connect("{LAWS_DATA_DB}")
for q, min_hits in [("交通肇事", 5), ("accident", 50), ("traffic", 50)]:
    n = db.execute("SELECT COUNT(*) FROM gongbao_docs_fts WHERE gongbao_docs_fts MATCH ?", (q,)).fetchone()[0]
    icon = "✅" if n >= min_hits else "⚠"
    print(f"  {{icon}} FTS \\\"{{q}}\\\": {{n}} hits")
db.close()
' """)

    # ── Summary ───────────────────────────────────────────────────────
    issues = []
    if not ok: issues.append("gongbao 验证失败")
    if not en_ok: issues.append("法条英文翻译验证失败")

    print(f"\n{'='*60}")
    if issues:
        print(f"⚠ 完成，存在 {len(issues)} 个问题:")
        for i in issues:
            print(f"  - {i}")
        sys.exit(1)
    else:
        print("✅ 全部验证通过")

    # ── Step 4: Copy back to App bundle ───────────────────────────────
    if not args.skip_copy_back:
        print(f"\n── 复制回 App bundle ──")
        size_mb = LAWS_DATA_DB.stat().st_size / 1024 / 1024
        if run(f"cp '{LAWS_DATA_DB}' '{APP_BUNDLE_DB}'"):
            print(f"  ✅ 已复制 ({size_mb:.0f}MB)")
        else:
            print(f"  ✗ 复制失败")
            sys.exit(1)
    else:
        print(f"\n  (跳过复制回 App bundle)")

    print(f"\n✅ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
