#!/usr/bin/env python3
"""
将最高人民法院公报文档（指导案例、裁判文书、司法文件）翻译成英文，
结果写回 json_en_gongbao/{source}/{id}.json。

用法：
  export DEEPSEEK_API_KEY=sk-...
  python3 scripts/translate_gongbao.py --source al          # 翻译指导案例
  python3 scripts/translate_gongbao.py --source cpwsxd     # 翻译裁判文书
  python3 scripts/translate_gongbao.py --source sfwj       # 翻译司法文件
  python3 scripts/translate_gongbao.py --source al --dry-run  # 统计
  python3 scripts/translate_gongbao.py                      # 全部
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import JSON_DIR, DB_PATH

JSON_EN_GONGBAO_DIR = JSON_DIR.parent / 'json_en_gongbao'

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL   = "deepseek-v4-flash"

SOURCE_LABELS = {
    'al':     'guiding_case',
    'cpwsxd': 'judgment',
    'sfwj':   'judicial_doc',
}


def build_system_prompt() -> str:
    return """You are a professional legal translator specializing in Chinese case law from the Supreme People's Court Gazette of China.

TRANSLATION RULES:

1. CASE NAMES: Format as "Plaintiff v. Defendant — [case type]"
   - "慈溪市博某塑料制品有限公司诉永康市联某工贸有限公司" → "Cixi BoMou Plastic Products Co., Ltd. v. Yongkang LianMou Industry & Trade Co., Ltd. — dispute over infringement of utility model patent"
   - "指导性案例XXX号：黄某辉、陈某等8人非法捕捞水产品刑事附带民事公益诉讼案" → "Guiding Case No. XXX: Huang Mouhui, Chen Mou, et al. (8 persons) — criminal附带 civil public interest litigation for illegal fishing of aquatic products"
   - "刘京胜诉搜狐爱特信信息技术（北京）有限公司侵犯著作纠纷案" → "Liu Jingsheng v. Sohu Aitexin Information Technology (Beijing) Co., Ltd. — copyright infringement dispute"

2. GUIDE CASE PREFIX: "指导性案例XXX号" → "Guiding Case No. XXX"

3. CASE PARTIES (appellate):
   - "上诉人" → "Appellant"
   - "被上诉人" → "Appellee" (or "Respondent" if against government)
   - "原审原告/被告" → "Plaintiff/Defendant at First Instance"
   - "公诉机关" → "Procuratorial Authority"
   - "辩护人" → "Defense Counsel"
   - "委托代理人" → "Agent ad litem"

4. SECTION HEADINGS (fixed translations):
   - "关键词" → "Keywords"
   - "裁判要点" → "Ruling Gist"
   - "基本案情" → "Basic Facts"
   - "裁判结果" → "Judgment"
   - "裁判理由" → "Reasoning"
    - "【裁判摘要】" (with brackets) → "Ruling Summary"
    - "原告诉称" → "Plaintiff's Allegations"
    - "被告辩称" → "Defendant's Defense"
    - "经审理查明" → "Facts Found by the Court"
    - "本院认为" → "Opinion of the Court"
    - "公诉机关指控" → "Prosecutor's Charges"
    - "上述事实，有...等证据证实" → "The above facts are confirmed by the following evidence: ..."

5. PERSON NAMES:
   - Full names (刘京胜) → Pinyin romanization: "Liu Jingsheng"
   - Redacted names (黄某辉, 陈某) → DO NOT transliterate "某" as "Mou".
     Instead, use standard English anonymous party convention:
     "黄某辉" → surname only: "Huang"
     "陈某" → surname only: "Chen"
     "黄某辉、陈某等8人" → "Huang, Chen, and six others"
     To distinguish multiple parties with the same surname: use "Huang A", "Huang B"

6. DATES:
   - "2023年10月20日" → "October 20, 2023"
   - "2020年10月底至2021年4月13日" → "from late October 2020 to April 13, 2021"
   - "2015年8月5日凌晨2时许" → "at approximately 2:00 a.m. on August 5, 2015"
   - "2000年10月" → "October 2000"
   - Convert all Chinese dates to standard English month-day-year format

7. MONEY & NUMBERS:
   - "211 000元" (with space) → "RMB 211,000" or "211,000 yuan"
   - "一万余斤" → "over 10,000 jin" (add footnote: 1 jin = 0.5 kg)
   - "十万元" → "RMB 100,000"
   - "8人" → "8 persons"
   - Preserve Chinese units of measurement (jin, mu, etc.) with English unit conversion in parentheses on first use

8. LEGAL CITATIONS:
   - 《中华人民共和国民法典》 → "Civil Code of the PRC"
   - 《中华人民共和国刑法》 → "Criminal Law of the PRC"
   - 《中华人民共和国商业银行法》 → "Commercial Banking Law of the PRC"
   - Standard format: "《Law Name》" → English title without brackets in text

9. COURT NAMES:
   - "最高人民法院" → "Supreme People's Court"
   - "北京市高级人民法院" → "Beijing High People's Court"
   - "江苏省南京市鼓楼区人民法院" → "Gulou District People's Court of Nanjing, Jiangsu Province"
   - Format: [District/Intermediate/High] People's Court of [City/Jurisdiction]

10. COMPANY & ORGANIZATION NAMES:
    - On first use: full translated name
    - On subsequent references: abbreviated form (e.g., "搜狐爱特信信息技术（北京）有限公司" → first: "Sohu Aitexin Information Technology (Beijing) Co., Ltd.", then: "Sohu")
    - Preserve registered trademarks and brand names in their original English form
    - Company branches: "××分公司" → ", ×× Branch" (e.g., "中国铁通集团有限公司南京分公司" → "China Tietong Group Co., Ltd., Nanjing Branch")
    - Hong Kong/Macau entities: "香港美艺金属制品厂" → "Hong Kong Mei Yi Metal Products Factory"
    - Foreign companies with bilingual names "瑞克麦斯热那亚航运公司（Rickmers Genoa Schiffahrtsgesellschaft mbH & Cie. KG）" → use the English in parentheses as the primary name on first mention, then abbreviate
    - Brand names already in Latin script (e.g., TEENIEWEENIE, E.LAND LTD) → preserve verbatim, do NOT romanize or translate

11. FOREIGN PATENT & DOCUMENT REFERENCES:
    - "GB1361763号英国专利" → "UK Patent No. GB1361763"
    - "昭59—14156号日本特许出愿公告" → "Japanese Patent Application Laid-Open No. Sho 59-14156"
    - Format: translate country, keep number, convert document type to standard English patent term

13. EVIDENCE & WITNESSES:
    - "xxx等证人的证言" → "testimony of witnesses including xxx"
    - "公诉机关向法庭提交了以下证据" → "The prosecutorial authority submitted the following evidence to the court:"
    - Preserve numbered evidence lists as given

14. LITIGANT IDENTIFIERS:
    - "原告：刘京胜，男，44岁，山东省胶南县人，中国国际广播电台西班牙语部翻译" → "Plaintiff: Liu Jingsheng, male, 44 years old, a translator at the Spanish Department of China Radio International"
    - Include all identifying details (gender, age, occupation, address) as given

15. SPECIALIZED LEGAL TERMS:
    - "光船承租人" → "bareboat charterer"
    - "反向工程" → "reverse engineering"
    - "特别提款权" → "Special Drawing Rights (SDRs)"
    - "海事赔偿责任限制" → "limitation of liability for maritime claims"
    - "马绍尔群岛籍" (vessel flag) → "Marshall Islands flag"
    - "本领域普通技术人员" → "a person of ordinary skill in the art" (patent law standard)
    - "恶意串通" → "malicious collusion"

16. DOCUMENT STRUCTURE:
    - Preserve all paragraph breaks
    - Use only English punctuation (no Chinese  ， 。 “ ” 、)
    - Convert "一、" "（一）" numbering to "1." "(1)" in English
    - Keep bullet points (●, ◆) and list markers
    - Patent claims: preserve nested numbering (1. / 2.根据权利要求1所述的...) as "1. / 2. The arm structure according to claim 1, wherein..." in standard patent English

16. SPECIAL NUMBERS & IDENTIFIERS:
    - Card numbers: "6222 XXXX XXXX XXXX 828" → keep as-is (it's already redacted)
    - Case numbers: keep as-is
    - URLs: preserve exactly (remove spaces: "www. yifan.net" not "www. yifan. net")

17. KNOWN WORKS:
    - 《唐吉诃德》 → "Don Quixote" (internationally known work, use standard English title)
    - Other known literary/legal works: use standard English translations

18. GENERAL STYLE:
    - Formal, precise legal English
    - Use 'shall' for obligations, 'may' for permissions, 'must' for requirements
    - Neutral tone — preserve the original document's legal authority
    - If the document has no structured sections, translate naturally as a coherent legal text
    - NEVER add commentary or explanation outside the translation"""


def api_call(messages: list, system: str) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY not set")
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "max_tokens": 32768,
        "messages": [{"role": "system", "content": system}] + messages,
    }).encode()
    req = urllib.request.Request(
        DEEPSEEK_API_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = resp.read()
        data = json.loads(body)
        if "choices" not in data or not data["choices"]:
            raise ValueError(f"API returned no choices: {data.get('error', body[:200])}")
        return data["choices"][0]["message"]["content"]


def load_en_file(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def save_en_file(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def get_docs(source: str = '') -> list:
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    if source:
        rows = conn.execute(
            "SELECT id, source, title, case_number, ruling_gist, full_text, keywords, issue, year, doc_number "
            "FROM gongbao_docs WHERE source=? ORDER BY id", (source,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, source, title, case_number, ruling_gist, full_text, keywords, issue, year, doc_number "
            "FROM gongbao_docs ORDER BY source, id"
        ).fetchall()
    conn.close()
    return rows


def is_fully_translated(en_data: dict) -> bool:
    if not en_data.get('title_en', '').strip():
        return False
    if not en_data.get('full_text_en', '').strip():
        return False
    return True


def split_text(text: str, max_chars: int = 6000) -> list:
    """将长文本按段落分割成不超过 max_chars 的块。"""
    paragraphs = text.split('\n')
    chunks = []
    current = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len + 1 > max_chars:
            chunks.append('\n'.join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += para_len + 1
    if current:
        chunks.append('\n'.join(current))
    return chunks


def translate_document(doc_id: int, title: str, full_text: str, ruling_gist: str,
                       keywords: str, system_prompt: str) -> dict:
    result = {}
    # title
    if title:
        prompt = "Translate this Chinese legal document title into English. Return only the translation:"
        result['title_en'] = api_call([{"role": "user", "content": f"{prompt}\n\n{title}"}], system_prompt).strip()
    else:
        result['title_en'] = ''

    # ruling_gist + keywords (short, one shot)
    meta_parts = []
    if ruling_gist:
        meta_parts.append(f"## Ruling Gist / 裁判要旨\n{ruling_gist}")
    if keywords:
        meta_parts.append(f"## Keywords\n{keywords}")
    if meta_parts:
        prompt = ("Translate the following into English. Return a JSON object:\n"
                  '- "ruling_gist_en": translated ruling gist (or "" if empty)\n'
                  '- "keywords_en": translated keywords (semicolon-separated, or "" if empty)\n\n'
                  + "\n\n".join(meta_parts))
        raw = api_call([{"role": "user", "content": prompt}], system_prompt)
        meta = _extract_json(raw, {"ruling_gist_en": "", "keywords_en": ""})
        result['ruling_gist_en'] = meta.get('ruling_gist_en', '')
        result['keywords_en'] = meta.get('keywords_en', '')
    else:
        result['ruling_gist_en'] = ''
        result['keywords_en'] = ''

    # full_text: 动态分块翻译
    if full_text:
        chunks = split_text(full_text, 6000)
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            is_single = len(chunks) == 1
            prompt = "Translate the following Chinese legal text into English. "
            if is_single:
                prompt += "Return only the translation."
            else:
                prompt += f"This is part {i+1}/{len(chunks)} of the document. Return only the translation of this part."
            translated = api_call([{"role": "user", "content": f"{prompt}\n\n{chunk}"}], system_prompt).strip()
            translated_chunks.append(translated)
        result['full_text_en'] = '\n\n'.join(translated_chunks)
    else:
        result['full_text_en'] = ''

    return result


def _extract_json(raw: str, default: dict) -> dict:
    s = raw.find("{")
    e = raw.rfind("}") + 1
    if s < 0 or e <= s:
        return default
    try:
        return json.loads(raw[s:e])
    except json.JSONDecodeError:
        candidate = raw[s:] + "}" if not raw.rstrip().endswith("}") else raw[s:]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return default


def main():
    parser = argparse.ArgumentParser(description='翻译公报文档到 json_en_gongbao/')
    parser.add_argument('--source', type=str, default='',
                        choices=['al', 'cpwsxd', 'sfwj', ''],
                        help='文档来源: al=指导案例, cpwsxd=裁判文书, sfwj=司法文件')
    parser.add_argument('--workers', type=int, default=4, help='并行线程数')
    parser.add_argument('--max-docs', type=int, default=0, help='最多翻译 N 篇（0=不限）')
    parser.add_argument('--offset', type=int, default=0, help='跳过前 N 篇')
    parser.add_argument('--dry-run', action='store_true', help='统计待翻译量')
    args = parser.parse_args()

    if not os.environ.get("DEEPSEEK_API_KEY") and not args.dry_run:
        print("ERROR: 请设置 DEEPSEEK_API_KEY", file=sys.stderr)
        sys.exit(1)

    docs = get_docs(args.source)
    label = SOURCE_LABELS.get(args.source, 'all') if args.source else 'all'

    if args.offset > 0:
        docs = docs[args.offset:]
    if args.max_docs > 0:
        docs = docs[:args.max_docs]

    # ── dry run ──
    if args.dry_run:
        need = 0
        total_chars = 0
        for doc_id, source, title, case_number, ruling_gist, full_text, keywords, issue, year, doc_number in docs:
            en_path = JSON_EN_GONGBAO_DIR / source / f'{doc_id}.json'
            en_data = load_en_file(en_path)
            if not is_fully_translated(en_data):
                need += 1
                total_chars += len(full_text or '')
        print(f"文档总数：{len(docs)} 篇（来源={label}）")
        print(f"  已完整翻译：{len(docs) - need} 篇")
        print(f"  待翻译：{need} 篇")
        print(f"  总字符数：{total_chars:,}")
        return

    system = build_system_prompt()
    pending = [(d[0], d[2], d[4], d[5], d[6]) for d in docs
               if not is_fully_translated(load_en_file(JSON_EN_GONGBAO_DIR / d[1] / f'{d[0]}.json'))]

    print(f"待翻译：{len(pending)} 篇（来源={label}）")

    def translate_one(row):
        doc_id, title, ruling_gist, full_text, keywords = row
        for attempt in range(5):
            try:
                t0 = time.time()
                result = translate_document(doc_id, title or '', full_text or '',
                                            ruling_gist or '', keywords or '', system)
                elapsed = time.time() - t0
                return doc_id, result, elapsed, None
            except Exception as exc:
                if attempt == 4:
                    return doc_id, None, 0, str(exc)
                wait = (2 ** attempt) + random.uniform(0, 1)
                print(f"  [{doc_id}] {exc}, {wait:.0f}s 后重试 ({attempt+1}/5)")
                time.sleep(wait)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(translate_one, r): r for r in pending}
        for fut in as_completed(futures):
            doc_id, result, elapsed, error = fut.result()
            source = None
            for d in docs:
                if d[0] == doc_id:
                    source = d[1]
                    break
            if error or result is None:
                print(f"  [{doc_id}] 失败：{error}")
            else:
                en_path = JSON_EN_GONGBAO_DIR / source / f'{doc_id}.json'
                en_data = load_en_file(en_path)
                en_data['title_en'] = result.get('title_en', '')
                en_data['ruling_gist_en'] = result.get('ruling_gist_en', '')
                en_data['keywords_en'] = result.get('keywords_en', '')
                en_data['full_text_en'] = result.get('full_text_en', '')
                save_en_file(en_path, en_data)
                done += 1
                if done % 20 == 0:
                    print(f"  完成：{done}/{len(pending)}（最近 {elapsed:.0f}s）")

    print(f"\n完成：{done}/{len(pending)} 篇")


if __name__ == "__main__":
    main()
