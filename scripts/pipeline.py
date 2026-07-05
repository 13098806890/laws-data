#!/usr/bin/env python3
"""
laws-data pipeline

Usage:
  python3 scripts/pipeline.py [options]

Options:
  --docx               Force re-run docx → JSON
  --skip-index         Skip law_index generation
  --skip-db            Skip JSON → DB
  --skip-md            Skip DB → Markdown
  --skip-gongbao       Skip gazette data import
  --skip-en            Skip en_json → content_en import
  --only-refs          Only run extract_references
  --validate           Run content_en vs json_en validation after import
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
INDEX_PATH = BASE_DIR / "law_index.json"

from config import DB_PATH, SRC_DIRS, JSON_DIR
from utils import pub_date_from_stem, title_from_stem


# ── helpers ──────────────────────────────────────────────────────────────────

def _snapshot_index():
    if not INDEX_PATH.exists():
        return {}
    entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return {e["filename"]: e for e in entries}


def _snapshot_db_refs(db_path: Path):
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        total = conn.execute("SELECT COUNT(*) FROM article_references").fetchone()[0]
        resolved = conn.execute("SELECT COUNT(*) FROM article_references WHERE resolved=1").fetchone()[0]
        cross = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='cross_law'").fetchone()[0]
        self_ = conn.execute("SELECT COUNT(*) FROM article_references WHERE ref_type='self_ref'").fetchone()[0]
        conn.close()
        return {"total": total, "resolved": resolved, "cross": cross, "self": self_}
    except Exception:
        return {}


def _snapshot_db_laws(db_path: Path):
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT filename, is_current FROM laws").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _build_report(before_index, before_refs, before_current, db_path):
    lines = []
    after_index = {}
    if INDEX_PATH.exists():
        entries = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        after_index = {e["filename"]: e for e in entries}
    after_refs = _snapshot_db_refs(db_path)
    after_current = _snapshot_db_laws(db_path)

    added = [v for k, v in after_index.items() if k not in before_index]
    if added:
        lines.append(f"\n【新增法律】{len(added)} 部")
        by_domain = {}
        for e in sorted(added, key=lambda x: (x.get("legal_domain") or "其他", x.get("pub_date") or "")):
            d = e.get("legal_domain") or "其他"
            by_domain.setdefault(d, []).append(e)
        for domain, laws in sorted(by_domain.items()):
            lines.append(f"  {domain}：")
            for e in laws:
                lines.append(f'    + [{e["law_id"]}] {e["title"]}  ({e.get("pub_date","")})')
    else:
        lines.append("\n【新增法律】无")

    removed = [k for k in before_index if k not in after_index]
    if removed:
        lines.append(f"\n【移除法律】{len(removed)} 部")
        for k in removed:
            e = before_index[k]
            lines.append(f'    - [{e.get("law_id","")}] {e.get("title","")}')

    current_changes = []
    for fn, new_cur in after_current.items():
        old_cur = before_current.get(fn)
        if old_cur is not None and old_cur != new_cur:
            current_changes.append((fn, old_cur, new_cur))
    if current_changes:
        lines.append(f"\n【is_current 变化】{len(current_changes)} 条")
        for fn, old, new in sorted(current_changes):
            arrow = "1→0（旧版）" if new == 0 else "0→1（升为现行）"
            lines.append(f"  {fn}  {arrow}")
    else:
        lines.append("\n【is_current 变化】无")

    if after_refs:
        if before_refs:
            dt = after_refs["total"] - before_refs["total"]
            dr = after_refs["resolved"] - before_refs["resolved"]
            dc = after_refs["cross"] - before_refs["cross"]
            ds = after_refs["self"] - before_refs["self"]
            def _fmt(n): return f"+{n}" if n >= 0 else str(n)
            lines.append(
                f'\n【引用关系】总计 {after_refs["total"]} 条'
                f'（{_fmt(dt)}）  '
                f'跨法 {after_refs["cross"]}（{_fmt(dc)}）  '
                f'自引 {after_refs["self"]}（{_fmt(ds)}）  '
                f'已解析 {after_refs["resolved"]}（{_fmt(dr)}）'
            )
        else:
            lines.append(
                f'\n【引用关系】总计 {after_refs["total"]} 条  '
                f'跨法 {after_refs["cross"]}  自引 {after_refs["self"]}  '
                f'已解析 {after_refs["resolved"]}'
            )

    lines.append(f"\n【汇总】法律总数 {len(before_index)} → {len(after_index)}")
    return lines


def _write_log(report_lines: list[str]):
    LOG_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"pipeline_{ts}.log"
    header = [
        f"pipeline 运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
    ]
    path.write_text("\n".join(header + report_lines) + "\n", encoding="utf-8")
    print(f"\n日志已写入：{path}")


# ── change detection: content hash based ─────────────────────────────────────

import hashlib

MANIFEST_PATH = BASE_DIR / ".source_hashes.json"


def _hash_file(path: Path) -> str:
    """MD5 hash of file content."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_hash_manifest() -> dict:
    """Load previous source file hashes: {relative_path: md5_hex}."""
    if not MANIFEST_PATH.exists():
        return {}
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_hash_manifest(manifest: dict):
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _needs_docx_conversion() -> bool:
    """Check if any source docx has changed by comparing content hashes.
    Also checks for missing json outputs. Returns True if conversion needed."""
    manifest = _load_hash_manifest()
    new_manifest = {}
    changed = []
    missing = []

    for cat, src_dir in SRC_DIRS.items():
        if not src_dir.exists():
            continue
        for docx_path in sorted(src_dir.glob("*.docx")):
            rel = str(docx_path.relative_to(BASE_DIR))
            stem = docx_path.stem
            json_path = JSON_DIR / cat / f"{stem}.json"

            # Check json exists
            if not json_path.exists():
                missing.append(rel)
                continue

            # Compare hash
            current_hash = _hash_file(docx_path)
            prev_hash = manifest.get(rel)
            new_manifest[rel] = current_hash

            if prev_hash is None:
                changed.append(f"{rel} (new)")
            elif prev_hash != current_hash:
                changed.append(f"{rel} (modified)")

    _save_hash_manifest(new_manifest)

    if missing:
        print(f"  ⚠  {len(missing)} source files have no json output")
        for m in missing[:5]:
            print(f"      missing: {m}")
    if changed:
        print(f"  ⚠  {len(changed)} source files changed since last conversion:")
        for c in changed[:10]:
            print(f"      {c}")
    else:
        print(f"  ✅  No source file changes detected ({len(new_manifest)} files checked)")

    return bool(missing or changed)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="laws-data pipeline")
    parser.add_argument("--docx", action="store_true", help="Force re-run docx → JSON")
    parser.add_argument("--skip-index", action="store_true", help="Skip law_index generation")
    parser.add_argument("--skip-db", action="store_true", help="Skip JSON → DB")
    parser.add_argument("--skip-md", action="store_true", help="Skip DB → Markdown")
    parser.add_argument("--skip-gongbao", action="store_true", help="Skip gazette data import")
    parser.add_argument("--skip-en", action="store_true", help="Skip en_json → content_en import")
    parser.add_argument("--only-refs", action="store_true", help="Only run extract_references")
    parser.add_argument("--validate", action="store_true", help="Run content_en vs json_en validation")
    args = parser.parse_args()

    # ── 0. Detect if docx conversion is needed ──
    needs_docx = _needs_docx_conversion()
    if needs_docx and not args.docx:
        print("\n>>> 检测到源文件有变更，建议运行 --docx 以更新 json 文件")
        print(">>> 使用 --docx 确认执行，或确认无变更后忽略此提示\n")
    run_docx = args.docx or needs_docx
    if args.docx and not needs_docx:
        print("\n>>> --docx 已指定，但源文件无变更，跳过转换")
        run_docx = False

    if args.only_refs:
        before_refs = _snapshot_db_refs(DB_PATH)
        before_current = _snapshot_db_laws(DB_PATH)
        from extract_references import run as extract_refs
        extract_refs()
        from json_to_db.builder import load_references
        load_references()
        report = _build_report({}, before_refs, before_current, DB_PATH)
        for line in report:
            print(line)
        _write_log(report)
        return

    # Pre-run snapshots
    before_index = _snapshot_index()
    before_refs = _snapshot_db_refs(DB_PATH)
    before_current = _snapshot_db_laws(DB_PATH)

    # ── 1. docx → JSON ──
    if run_docx:
        print("\n=== 阶段一：docx → JSON ===")
        from docx_to_json.converter import run as docx_to_json
        docx_to_json()
    else:
        print("\n=== 阶段一：docx → JSON (跳过，源文件无变更) ===")

    # ── 2. law_index ──
    if not args.skip_index:
        print("\n=== 阶段二：生成 law_index ===")
        from generate_law_index import run as gen_law_index
        gen_law_index()

    # ── 2b. 安全校验：JSON law_id 与 law_index 一致 ──
    if INDEX_PATH.exists():
        index = json.loads(INDEX_PATH.read_text("utf-8"))
        idx_map = {e["filename"]: e["law_id"] for e in index}
        mismatches = []
        for p in sorted(JSON_DIR.rglob("*.json")):
            if "index" in p.name:
                continue
            data = json.loads(p.read_text("utf-8"))
            fn = p.stem
            expected = idx_map.get(fn)
            actual = data.get("law_id")
            if expected is not None and actual != expected:
                mismatches.append((fn, actual, expected))
        if mismatches:
            print("\n❌ 严重错误：以下 JSON 文件的 law_id 与 law_index.json 不一致：")
            for fn, actual, expected in mismatches:
                print(f"    {fn}: JSON 中为 {actual}，law_index 为 {expected}")
            sys.exit(1)
        print(f"  ✅ law_id 校验通过：{len(idx_map)} 条索引，0 个不匹配")
    else:
        print("  ⚠  law_index.json 不存在，跳过 law_id 校验")

    # ── 3. JSON → DB ──
    if not args.skip_db:
        print("\n=== 阶段三：JSON → DB ===")
        from json_to_db.builder import run as json_to_db
        json_to_db()
        from json_to_db.export_menu import run as export_menu
        export_menu()
        from json_to_db.export_flk_menu import run as export_flk_menu
        export_flk_menu()
        from extract_references import run as extract_refs
        extract_refs()
        from json_to_db.builder import load_references
        load_references()
    else:
        print("\n=== 阶段三：JSON → DB (跳过) ===")

    # ── 4. Gazette data ──
    if not args.skip_db and not args.skip_gongbao:
        print("\n=== 阶段四：导入公报数据 ===")
        from build_gongbao_db import run as build_gongbao
        build_gongbao(drop=True)

    # ── 5. en_json → content_en ──
    if not args.skip_db and not args.skip_en:
        print("\n=== 阶段五：导入英文翻译 (en_json → content_en) ===")
        from import_en import import_en
        import_en()
    else:
        print("\n=== 阶段五：导入英文翻译 (跳过) ===")

    # ── 6. MD export ──
    if not args.skip_md:
        print("\n=== 阶段六：DB → Markdown ===")
        from db_to_md.renderer import run as db_to_md
        db_to_md()
        from db_to_md.render_flk import run as render_flk
        render_flk()

    # ── 7. Validation ──
    if args.validate:
        print("\n=== 阶段七：验证 (content_en vs json_en) ===")
        from validate_en import validate
        validate()

    # Report
    report = _build_report(before_index, before_refs, before_current, DB_PATH)
    print("\n" + "=" * 60)
    print("变更报告")
    print("=" * 60)
    for line in report:
        print(line)
    _write_log(report)
    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
