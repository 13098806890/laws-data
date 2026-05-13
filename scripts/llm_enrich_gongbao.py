#!/usr/bin/env python3
"""
用 DeepSeek LLM 为公报指导案例和裁判文书批量生成结构化关键词，回写到源 JSON。

特性：
- 断点续跑：已有 keywords_meta 的文件自动跳过
- 10 并发，带重试（最多 3 次）
- 合并策略：LLM 新词 + 原有 keywords 平铺字符串合并去重
- 进度实时打印到控制台

运行：
    cd /Users/doxie/laws_data
    python3 scripts/llm_enrich_gongbao.py              # 处理 al + cpwsxd
    python3 scripts/llm_enrich_gongbao.py --force      # 强制覆盖已有 meta
    python3 scripts/llm_enrich_gongbao.py --dry-run    # 只打印，不写文件
    python3 scripts/llm_enrich_gongbao.py --source al  # 只处理指定来源
"""

import argparse
import json
import time
import urllib.request
import urllib.error
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────────────────

BASE_DIR   = Path(__file__).parent.parent
GONGBAO_DIR = BASE_DIR / '最高人民法院公报'

SOURCES = {
    'al':     GONGBAO_DIR / '指导案例',
    'cpwsxd': GONGBAO_DIR / '裁判文书',
}

MAX_WORKERS  = 10
RETRY_LIMIT  = 3
CONTENT_TRUNC = 3000   # 截取正文前 N 字发给 LLM


def _get_api_key() -> str:
    """从系统 Keychain 读取 DeepSeek API Key。"""
    try:
        key = subprocess.check_output(
            ['security', 'find-generic-password', '-s', 'deepseek_api_key', '-w'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        if key:
            return key
    except Exception:
        pass
    import os
    key = os.environ.get('DEEPSEEK_API_KEY', '')
    if key:
        return key
    raise RuntimeError('找不到 DeepSeek API Key（Keychain 或环境变量 DEEPSEEK_API_KEY）')


API_KEY = _get_api_key()

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
你是一位专业的中国法律文献标引专家，负责为人民法院公报的裁判文书和指导案例提取结构化关键词。

输出规则：
- 严格返回 JSON 对象，不含任何其他文字
- 每个维度的值必须是字符串数组（即使只有一个值）
- 不确定的维度返回空数组 []
- 不提取年份（已有单独字段）
- 不提取案例编号（已有单独字段）
- 每个维度最多 6 个值，选最核心的
- 地区只写省级（直辖市如"北京市"，省份如"广东省"）

维度说明：
{
  "法律类型": "从 [民事, 刑事, 行政, 国家赔偿, 执行] 中选，最多 1 个",
  "案件类型": "具体纠纷或案件类型，如合同纠纷、侵权责任、婚姻家庭、劳动争议、知识产权、不正当竞争等",
  "审级": "从 [一审, 二审, 再审, 申请再审] 中选适用的",
  "法院层级": "从 [最高人民法院, 高级人民法院, 中级人民法院, 基层人民法院] 中选适用的",
  "地区": "案件涉及的省级行政区，多地写多个",
  "当事人类型": "从 [自然人, 法人, 国家机关, 外资企业, 金融机构] 中选适用的",
  "法律适用": "适用的主要法律名称（不含具体条文号），如民法典、合同法、刑法、公司法",
  "争议焦点": "本案核心争议，用简洁短语，3-5 个",
  "裁判结果": "从 [支持原告, 驳回诉请, 部分支持, 发回重审, 改判, 维持原判] 中选一个",
  "案情事实": "案件核心事实标签，如房屋买卖、交通事故、股权纠纷、网络侵权等，3-5 个",
  "法律原则": "适用的法律原则，如诚实信用、公平原则、无罪推定，无则为空数组",
  "指导意义": "仅指导案例填写，如统一裁判标准、填补法律空白、明确司法尺度，其他类型返回空数组"
}\
"""


def _build_user_prompt(title: str, content: str, existing_kw: str) -> str:
    truncated = content[:CONTENT_TRUNC]
    parts = [f"标题：{title}"]
    if existing_kw:
        parts.append(f"现有关键词（供参考）：{existing_kw}")
    parts.append(f"\n正文（节选）：\n{truncated}")
    return '\n'.join(parts)


# ── LLM 调用 ──────────────────────────────────────────────────────────────────

_print_lock = threading.Lock()

def _log(msg: str):
    with _print_lock:
        print(msg, flush=True)


def _call_llm(title: str, content: str, existing_kw: str) -> dict:
    """调用 DeepSeek，返回解析后的 dict。失败抛出异常。"""
    payload = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_prompt(title, content, existing_kw)},
        ],
        "temperature": 0.1,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        resp = json.loads(r.read())

    raw = resp["choices"][0]["message"]["content"]
    meta = json.loads(raw)

    # 统一：所有值强制转为 list[str]
    normalized = {}
    for k, v in meta.items():
        if isinstance(v, list):
            normalized[k] = [str(x) for x in v if x]
        elif isinstance(v, str) and v:
            normalized[k] = [v]
        else:
            normalized[k] = []
    return normalized


def _call_with_retry(title: str, content: str, existing_kw: str) -> dict | None:
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            return _call_llm(title, content, existing_kw)
        except Exception as e:
            if attempt == RETRY_LIMIT:
                _log(f'  ✗ 失败（{attempt} 次）: {title[:40]} — {e}')
                return None
            wait = 2 ** attempt
            _log(f'  ⚠ 第 {attempt} 次失败，{wait}s 后重试: {e}')
            time.sleep(wait)
    return None


# ── 关键词合并 ────────────────────────────────────────────────────────────────

def _merge_keywords(existing_kw: str, meta: dict) -> str:
    """将 LLM meta 的所有值平铺，与原有 keywords 合并去重。"""
    # 原有关键词拆分（顿号/逗号/斜杠）
    import re
    old_terms = re.split(r'[、，,/／\s]+', existing_kw) if existing_kw else []
    old_terms = [t.strip() for t in old_terms if t.strip()]

    # LLM 新词
    new_terms: list[str] = []
    for vals in meta.values():
        new_terms.extend(v.strip() for v in vals if v.strip())

    # 合并：LLM 词优先（放前面），原有词去重补充
    seen: set[str] = set()
    merged: list[str] = []
    for t in new_terms + old_terms:
        if t not in seen:
            seen.add(t)
            merged.append(t)
    return '、'.join(merged)


# ── 单文件处理 ────────────────────────────────────────────────────────────────

def process_file(path: Path, force: bool, dry_run: bool) -> str:
    """
    返回状态字符串：'skipped' / 'ok' / 'failed' / 'dry'
    """
    d = json.loads(path.read_text(encoding='utf-8'))

    if not force and d.get('keywords_meta'):
        return 'skipped'

    title      = d.get('title', '')
    content    = d.get('content', '')
    existing_kw = d.get('keywords', '')

    meta = _call_with_retry(title, content, existing_kw)
    if meta is None:
        return 'failed'

    merged_kw = _merge_keywords(existing_kw, meta)

    if dry_run:
        _log(f'  [dry] {title[:50]}')
        _log(f'        keywords: {merged_kw[:100]}')
        return 'dry'

    d['keywords_meta'] = meta
    d['keywords']      = merged_kw
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
    return 'ok'


# ── 主流程 ────────────────────────────────────────────────────────────────────

def run(sources: list[str], force: bool, dry_run: bool):
    all_files: list[tuple[Path, str]] = []
    for src in sources:
        folder = SOURCES.get(src)
        if not folder or not folder.exists():
            _log(f'⚠ 目录不存在：{folder}')
            continue
        files = sorted(folder.glob('*.json'))
        _log(f'{src}: {len(files)} 个文件')
        all_files.extend((f, src) for f in files)

    total   = len(all_files)
    counts  = {'ok': 0, 'skipped': 0, 'failed': 0, 'dry': 0}
    done    = 0

    _log(f'\n开始处理，共 {total} 个文件，并发 {MAX_WORKERS}...\n')

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process_file, f, force, dry_run): (f, src)
                   for f, src in all_files}
        for fut in as_completed(futures):
            f, src = futures[fut]
            try:
                status = fut.result()
            except Exception as e:
                status = 'failed'
                _log(f'  ✗ 异常: {f.name} — {e}')
            counts[status] += 1
            done += 1
            if status == 'ok':
                _log(f'  ✓ [{done}/{total}] {f.stem[:60]}')
            elif status == 'failed':
                _log(f'  ✗ [{done}/{total}] {f.stem[:60]}')
            # skipped 不打印，保持输出简洁

    _log(f'\n完成: ok={counts["ok"]}  skipped={counts["skipped"]}  '
         f'failed={counts["failed"]}  dry={counts["dry"]}')
    if counts['failed']:
        _log('⚠ 有失败文件，重新运行脚本可续跑（failed 文件没有写入 keywords_meta，下次不会跳过）')


def main():
    parser = argparse.ArgumentParser(description='LLM 批量标注公报关键词')
    parser.add_argument('--source', choices=['al', 'cpwsxd', 'both'], default='both',
                        help='处理哪个来源（默认 both）')
    parser.add_argument('--force',   action='store_true', help='强制覆盖已有 keywords_meta')
    parser.add_argument('--dry-run', action='store_true', help='只打印，不写文件')
    args = parser.parse_args()

    sources = ['al', 'cpwsxd'] if args.source == 'both' else [args.source]
    run(sources, force=args.force, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
