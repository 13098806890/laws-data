import re


def title_from_stem(stem: str) -> str:
    raw = re.sub(r'_\d{8}$', '', stem)
    t = re.sub(r'[ \t]+', ' ', raw).strip()
    # 规范化机构名称间的空格为顿号
    t = re.sub(r'最高人民法院 +最高人民检察院', '最高人民法院、最高人民检察院', t)
    t = re.sub(r'最高人民检察院 +最高人民法院', '最高人民检察院、最高人民法院', t)
    t = re.sub(r'最高人民法院 +公安部', '最高人民法院、公安部', t)
    t = re.sub(r'最高人民检察院 +公安部', '最高人民检察院、公安部', t)
    return t


def pub_date_from_stem(stem: str):
    """从文件名 '中华人民共和国XXX法_20201017' 中提取日期。返回 str 或 None。"""
    m = re.search(r'_(\d{8})$', stem)
    if m:
        d = m.group(1)
        return f'{d[:4]}-{d[4:6]}-{d[6:]}'
    return None
