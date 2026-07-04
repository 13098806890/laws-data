import re


def title_from_stem(stem: str) -> str:
    raw = re.sub(r'_\d{8}$', '', stem)
    return re.sub(r'[ \t]+', ' ', raw).strip()


def pub_date_from_stem(stem: str):
    """从文件名 '中华人民共和国XXX法_20201017' 中提取日期。返回 str 或 None。"""
    m = re.search(r'_(\d{8})$', stem)
    if m:
        d = m.group(1)
        return f'{d[:4]}-{d[4:6]}-{d[6:]}'
    return None
