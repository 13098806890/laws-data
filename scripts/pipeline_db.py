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
import os
import subprocess
import sys
from pathlib import Path

LAWS_DATA = Path(__file__).parent.parent
SCRIPTS   = LAWS_DATA / "scripts"
LAWS_DATA_DB  = LAWS_DATA / "law_content.db"
# App bundle 路径可被环境变量覆盖（跨 repo，默认指向本机 iOS 项目）
APP_BUNDLE_DIR = Path(os.environ.get("LAWS_APP_BUNDLE_DIR", "/Users/doxie/Github/LawsSearch/ChineseLawsSearch/ChineseLawsSearch"))
APP_BUNDLE_DB = APP_BUNDLE_DIR / "law_content.db"


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
    parser.add_argument("--skip-enhancements", action="store_true", help="Skip enhancements DB rebuild")
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
        if not run(f"python3 '{SCRIPTS / 'classify_gongbao_domain.py'}'"):
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

    # ── Step 2a: 结构节点英文标题（heading_en_map.json → nodes.content_en）──
    if not args.skip_import_en and not args.validate_only:
        print("\n── Step 2a: 写入结构节点英文标题 (heading_en_map → content_en) ──")
        import json as _json
        HEADING_MAP_PATH = LAWS_DATA / "references" / "heading_en_map.json"
        if HEADING_MAP_PATH.exists():
            heading_map = _json.loads(HEADING_MAP_PATH.read_text(encoding="utf-8"))
            # heading_en_map.json uses stable keys (law_id:type:order_index)。
            # 注意：translate_headings.py 写入时用 COALESCE(order_index,0)，这里必须保持一致，
            # 否则 order_index 为 NULL 的"正文"等节点匹配不上（此前 pipeline.py 阶段五b 的 bug）。
            import sqlite3
            conn = sqlite3.connect(str(LAWS_DATA_DB))
            updated = 0
            for key, en_text in heading_map.items():
                parts = key.split(":")
                law_id, ntype, oi = int(parts[0]), parts[1], int(parts[2])
                cur = conn.execute(
                    "UPDATE nodes SET content_en = ? WHERE law_id = ? AND type = ? AND COALESCE(order_index, 0) = ? AND (content_en IS NULL OR content_en = '')",
                    (en_text, law_id, ntype, oi)
                )
                updated += cur.rowcount
            conn.commit()
            conn.close()
            print(f"  ✅ 写入 {updated} 条结构节点英文标题 (共 {len(heading_map)} 条缓存)")
        else:
            print("  ⚠  heading_en_map.json 不存在，跳过（可先运行 translate_headings.py 生成）")

    # ── Step 2b: 导出菜单（需在 import_en 之后，保证 title_en 已写入）──
    if not args.skip_json_rebuild and not args.validate_only:
        print("\n── Step 2b: 导出菜单 (law_menu) ──")
        if not run(f"python3 -m json_to_db.export_menu", cwd=SCRIPTS):
            sys.exit(1)

    # ── Step 3.5: Rebuild enhancements (keyword_synonyms etc.) ───────────
    if not args.skip_enhancements and not args.validate_only:
        print("\n── Step 3.5/4: 重建 law_enhancements.db ──")
        if not run(f"python3 '{SCRIPTS / 'build_enhancements.py'}'"):
            print("  ⚠ 增强库重建失败，继续验证…")

    # ── Step 4: Validate ──────────────────────────────────────────────
    print("\n── Step 4/4: 验证 ──")

    # DB vs JSON 结构一致性 + 英文覆盖率
    print("\n  ── DB 一致性 + 英文覆盖率验证 ──")
    db_ok = run(f"python3 '{SCRIPTS / 'verify_db.py'}'")

    # 法律结构完整性（条文编号递增、父子结构）
    print("\n  ── 结构完整性验证 ──")
    struct_ok = run(f"python3 '{SCRIPTS / 'verify_structure.py'}'")

    # Gongbao validation
    print("\n  ── gongbao 验证 ──")
    ok = run(f"python3 '{SCRIPTS / 'verify_gongbao_db.py'}'")

    # content_en validation
    print("\n  ── 法条英文翻译验证 ──")
    en_ok = run(f"python3 '{SCRIPTS / 'validate_en.py'}'")

    # Repeal marks validation（验证公报源 repealed_by 字段是否正确应用）
    print("\n  ── 废止标记验证 ──")
    repeal_ok = run(f"python3 '{SCRIPTS / 'verify_repeal_rules.py'}'")

    # Enhancements validation
    print("\n  ── 增强库验证 ──")
    enh_ok = run(f"python3 '{SCRIPTS / 'verify_enhancements.py'}'")

    # Quick FTS check
    print("\n  ── FTS 快速检查 ──")
    fts_ok = True
    fts_out = run(f"""python3 -c '
import sqlite3
db = sqlite3.connect("{LAWS_DATA_DB}")
fails = []
for q, min_hits in [("交通肇事", 5), ("accident", 50), ("traffic", 50)]:
    n = db.execute("SELECT COUNT(*) FROM gongbao_docs_fts WHERE gongbao_docs_fts MATCH ?", (q,)).fetchone()[0]
    icon = "✅" if n >= min_hits else "⚠"
    print(f"  {{icon}} FTS \\\"{{q}}\\\": {{n}} hits")
    if n < min_hits:
        fails.append(f"FTS \\\"{{q}}\\\" 只有 {{n}} 条（需要 {{min_hits}}）")
db.close()
import sys
if fails:
    print("  ❌ FTS 命中数不足：")
    for f in fails:
        print(f"    - {{f}}")
    sys.exit(1)
' """)
    fts_ok = bool(fts_out)

    # ── Summary ───────────────────────────────────────────────────────
    issues = []
    if not db_ok: issues.append("DB 一致性/英文覆盖率验证失败")
    if not struct_ok: issues.append("结构完整性验证失败")
    if not ok: issues.append("gongbao 验证失败")
    if not en_ok: issues.append("法条英文翻译验证失败")
    if not repeal_ok: issues.append("废止规则验证失败")
    if not enh_ok: issues.append("增强库验证失败")
    if not fts_ok: issues.append("FTS 检查失败")

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
            print(f"  ✅ law_content.db 已复制 ({size_mb:.0f}MB)")
        else:
            print(f"  ✗ 复制失败")
            sys.exit(1)
        ENHANCEMENTS_DB = LAWS_DATA / "law_enhancements.db"
        APP_ENHANCEMENTS_DB = APP_BUNDLE_DB.parent / "law_enhancements.db"
        if ENHANCEMENTS_DB.exists():
            if run(f"cp '{ENHANCEMENTS_DB}' '{APP_ENHANCEMENTS_DB}'"):
                print(f"  ✅ law_enhancements.db 已复制")
            else:
                print(f"  ✗ 增强库复制失败")
                sys.exit(1)
    else:
        print(f"\n  (跳过复制回 App bundle)")

    print(f"\n✅ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
