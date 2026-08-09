#!/usr/bin/env python3
"""
law_id 单一权威注册表。

背景：历史上 law_id 有多个来源（json 内嵌、json_en 内嵌、law_index.json、blocklist），
blocklist（source_override_blocklist.json）把部分司法解释从 flk 源改指到 gongbao 源后，
旧 id 引用失效，导致翻译无法匹配、验证误报。

原则：law_id 的权威值只由本模块解析，任何脚本（builder / import_en / validate_en /
一次性修复脚本）都通过这里取值，禁止各自硬编码规则。

权威解析顺序（对一个 json_en / 公报文件）：
  1. 文件名命中 source_override_blocklist.json 的 gongbao_file → 用 blocklist 的 laws_id
  2. 否则用文件内嵌的 law_id（若在 law_index.json 中存在）
  3. 否则返回 None（孤儿）
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
BLOCKLIST_PATH = BASE_DIR / "scripts" / "source_override_blocklist.json"
LAW_INDEX_PATH = BASE_DIR / "law_index.json"

_entries = None
_index = None


def _load_entries():  # -> list[dict]
    global _entries
    if _entries is None:
        try:
            data = json.loads(BLOCKLIST_PATH.read_text(encoding="utf-8"))
            _entries = data if isinstance(data, list) else []
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            _entries = []
    return _entries


def load_index():  # -> list[dict]
    global _index
    if _index is None:
        try:
            data = json.loads(LAW_INDEX_PATH.read_text(encoding="utf-8"))
            _index = data if isinstance(data, list) else []
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            _index = []
    return _index


def blocklist_ids() -> set[int]:
    """所有被 blocklist 覆盖（flk 源跳过、gongbao 源接管）的 law_id。"""
    return {e["laws_id"] for e in _load_entries() if isinstance(e, dict) and isinstance(e.get("laws_id"), int)}


def gongbao_file_to_law_id() -> dict[str, int]:
    """gongbao_file 文件名 → 权威 law_id。"""
    return {e["gongbao_file"]: e["laws_id"] for e in _load_entries()
            if isinstance(e, dict) and e.get("gongbao_file") and isinstance(e.get("laws_id"), int)}


def law_index_ids() -> set[int]:
    return {e["law_id"] for e in load_index() if isinstance(e, dict) and isinstance(e.get("law_id"), int)}


def law_index_id_to_title() -> dict[int, str]:
    """law_index 中 law_id → 标题（用于按标题重定向被 blocklist 取代的旧 id）。"""
    return {e["law_id"]: e["title"] for e in load_index()
            if isinstance(e, dict) and isinstance(e.get("law_id"), int) and e.get("title")}


def _blocklist_title_to_id() -> dict[str, int]:
    """blocklist 标题 → 权威 law_id（被 blocklist 覆盖的 flk 源用同一标题重定向）。"""
    return {e["title"]: e["laws_id"] for e in _load_entries()
            if isinstance(e, dict) and e.get("title") and isinstance(e.get("laws_id"), int)}


def resolve_law_id(filename: str, embedded_law_id):
    """解析一个文件的权威 law_id。

    Args:
        filename: 文件名（含 .json 后缀），优先匹配 blocklist 的 gongbao_file。
        embedded_law_id: 文件内嵌的 law_id（可为 None）。

    Returns:
        权威 law_id；解析不到（孤儿）返回 None。

    解析顺序：
      1. 文件名命中 blocklist gongbao_file → 用 blocklist 的 laws_id
         （gongbao 源文件无内嵌 id；flk 风格文件名不会命中）
      2. 内嵌 id 在 law_index 中存在 → 保留
      3. 否则返回 None（孤儿）

    注意：不再按标题重定向。blocklist 的 laws_id 与 flk 源内嵌 id 必须
    一致（source_override_blocklist.json 已修正），按标题匹配会把
    同名不同版本（如 2001 版 vs 2019 修正版）的翻译错误指向新 id。
    """
    override = gongbao_file_to_law_id().get(filename)
    if override is not None:
        return override
    if embedded_law_id is not None and embedded_law_id in law_index_ids():
        return embedded_law_id
    return None
