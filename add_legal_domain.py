import os
import re
import json
import glob

# ── 一、从 Laws 仓库读取 title -> dept 映射 ──────────────────────────────
DEPT_DIRS = [
    '宪法', '宪法相关法', '民法商法', '民法典',
    '行政法', '经济法', '社会法', '刑法', '诉讼与非诉讼程序法',
]
LAWS_BASE = '/Users/doxie/Github/Laws'

title_to_dept: dict[str, str] = {}

for dept in DEPT_DIRS:
    dept_path = os.path.join(LAWS_BASE, dept)
    if not os.path.isdir(dept_path):
        continue
    for fname in os.listdir(dept_path):
        if not fname.endswith('.md') or fname.startswith('_'):
            continue
        raw = re.sub(r'\(\d{4}-\d{2}-\d{2}\)', '', fname[:-3]).strip()
        # 存原始标题和去前缀版本，同时去除空白后的版本
        for variant in [raw, raw.replace('中华人民共和国', '').strip()]:
            title_to_dept[re.sub(r'\s+', '', variant)] = dept


# ── 二、手工补充（Laws仓库里没有、或标题截断的条目）──────────────────────
MANUAL: dict[str, str] = {
    # 民法典整体
    '中华人民共和国民法典': '民法典',
    # 宪法相关法 - 人大决议/解释
    '全国人民代表大会常务委员会关于《中华人民共和国刑事诉讼法》第二百九十二条的解释': '宪法相关法',
    '全国人民代表大会常务委员会关于《中华人民共和国刑事诉讼法》第二百五十四条第五款、第二百五十七条第二款的解释': '宪法相关法',
    '全国人民代表大会常务委员会关于《中华人民共和国香港特别行政区基本法》第十三条第一款和第十九条的解释': '宪法相关法',
    '全国人民代表大会常务委员会关于《中华人民共和国香港特别行政区基本法》': '宪法相关法',
    '全国人民代表大会常务委员会关于在沿海港口城市设立海事法院的决定': '宪法相关法',
    '全国人民代表大会常务委员会关于中国人民解放军现役士兵衔级制度的决定': '宪法相关法',
    '全国人民代表大会常务委员会关于加强中央预算审查监督的决定': '经济法',
    '全国人民代表大会常务委员会关于惩治骗购外汇、逃汇和非法买卖外汇犯罪的决定': '经济法',
    '全国人民代表大会常务委员会关于批准中央军事委员会《关于授予军队离休干部中国人民解放军功勋荣誉章的规定》的决定': '宪法相关法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于职工探亲待遇的规定》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于安置老弱病残干部的暂行办法》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于老干部离职休养的暂行规定》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准《国务院关于工人退休、退职的暂行办法》的决议': '社会法',
    '第五届全国人民代表大会常务委员会关于批准广东省经济特区条例的决议': '经济法',
    # 新法/未收录
    '中华人民共和国突发公共卫生事件应对法': '社会法',
    '中华人民共和国国家发展规划法': '经济法',
    '中华人民共和国民营经济促进法': '经济法',
    '中华人民共和国法治宣传教育法': '宪法相关法',
    '中华人民共和国原子能法': '经济法',
    '中华人民共和国国家公园法': '社会法',
}
# 统一清洗后存入
for raw_title, dept in MANUAL.items():
    title_to_dept[re.sub(r'\s+', '', raw_title)] = dept
    title_to_dept[re.sub(r'\s+', '', raw_title.replace('中华人民共和国', ''))] = dept


# ── 三、关键词规则（用于行政法规/司法解释/监察法规兜底） ─────────────────
# 按优先级排列，第一个命中的为准
KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ('刑法',          ['刑法', '刑事', '犯罪', '罪名', '量刑', '追诉', '减刑', '假释', '执行死刑',
                       '定罪', '定性', '逮捕', '起诉', '在押', '盗窃', '贪污', '挪用', '渎职',
                       '妨害公务', '虐待', '非法经营', '走私', '毒品', '枪支质押', '累犯',
                       '借贷', '嫖宿幼女']),
    ('诉讼与非诉讼程序法', ['诉讼', '仲裁', '调解', '证据', '执行', '管辖', '审判程序', '司法鉴定', '公证', '法律援助',
                       '检察委员会', '立案', '侦查', '移送', '批准逮捕', '法律监督']),
    ('宪法相关法',    ['人民代表大会', '选举', '国家机构', '立法', '国防', '军队', '武装', '国旗', '国徽', '国歌',
                       '监察', '监察官', '特别行政区', '自治', '外交', '领海', '国界', '勋章']),
    ('民法商法',      ['民法', '合同', '物权', '婚姻', '继承', '侵权', '知识产权', '专利', '商标', '著作权',
                       '公司', '企业破产', '票据', '保险', '信托', '证券', '期货', '海商', '拍卖',
                       '不动产登记', '商业银行', '外商投资']),
    ('经济法',        ['税', '财政', '预算', '审计', '会计', '金融', '银行', '证券', '价格', '反垄断',
                       '反不正当竞争', '统计', '计量', '标准化', '招标', '政府采购', '国有资产',
                       '对外贸易', '海关', '出口', '进口', '外汇', '能源', '矿产', '资源', '农业',
                       '渔业', '林业', '草原', '水利', '交通', '铁路', '公路', '航道', '港口', '邮政',
                       '电力', '煤炭', '石油', '环境保护税', '车船税', '耕地占用税', '烟叶税']),
    ('社会法',        ['劳动', '工会', '社会保险', '社会保障', '教育', '医疗', '卫生', '食品安全',
                       '药品', '环境', '生态', '自然保护', '野生动物', '文物', '文化', '体育',
                       '残疾人', '妇女', '未成年人', '老年人', '归侨', '慈善', '红十字', '献血',
                       '消防', '安全生产', '职业病', '禁毒', '精神卫生', '传染病', '疫苗',
                       '动物防疫', '粮食', '湿地', '水土保持', '防洪', '防震', '气象', '测绘']),
    ('行政法',        ['行政', '公务员', '警察', '海关', '出入境', '国家秘密', '档案', '网络安全',
                       '数据安全', '个人信息', '密码', '广播', '出版', '新闻', '土地管理', '城乡规划',
                       '建设', '房地产', '道路交通', '枪支', '爆炸物', '危险品',
                       '口岸', '国家机关工作人员', '义务植树', '群众性活动', '无证无照',
                       '奥林匹克', '世界博览会', '基金会', '个体工商户', '海底电缆', '航空器权利',
                       '计算机信息网络', '非机动船舶', '集会游行示威', '高级专家退休',
                       '公报', '公告', '反外国制裁', '军服', '技术产业开发', '摊派',
                       '航空运输', '专业技术职务', '居住证', '年节', '放假',
                       '收养子女', '无线电']),
]


def clean(s: str) -> str:
    return re.sub(r'\s+', '', s)


def get_dept_by_keyword(title: str, content_keywords: list[str]) -> str | None:
    combined = title + ' ' + ' '.join(content_keywords)
    for dept, keywords in KEYWORD_RULES:
        if any(kw in combined for kw in keywords):
            return dept
    return None


def extract_content_keywords(data: dict) -> list[str]:
    """从promulgation_info和前几条正文里提取关键词辅助判断"""
    texts = [data.get('promulgation_info', '')]
    for ch in data.get('chapters', [])[:2]:
        for art in ch.get('articles', [])[:3]:
            texts.append(art.get('content', ''))
    return texts


def get_legal_domain(data: dict, filename: str = '') -> str | None:
    title_raw = data.get('title', '').strip()
    title_key = clean(title_raw)
    title_short = clean(title_raw.replace('中华人民共和国', ''))

    # 1. Laws仓库精确映射
    for key in [title_key, title_short]:
        if key in title_to_dept:
            return title_to_dept[key]

    # 2. 关键词规则（title + 正文 + 文件名，文件名兜底title截断的情况）
    extra = extract_content_keywords(data)
    result = get_dept_by_keyword(title_raw + ' ' + filename, extra)
    return result


# ── 四、写入所有JSON ──────────────────────────────────────────────────────
def process_all():
    paths = [p for p in glob.glob('/Users/doxie/laws_data/json/**/*.json', recursive=True)
             if 'index' not in p]

    stats = {'写入': 0, '跳过(已有)': 0, '未匹配': 0}
    unmatched = []

    for path in paths:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)

        if 'legal_domain' in data:
            stats['跳过(已有)'] += 1
            continue

        filename = os.path.basename(path)
        dept = get_legal_domain(data, filename)
        if dept:
            # 插入在 category 之后
            new_data = {}
            for k, v in data.items():
                new_data[k] = v
                if k == 'category':
                    new_data['legal_domain'] = dept
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)
            stats['写入'] += 1
        else:
            stats['未匹配'] += 1
            unmatched.append(('/'.join(path.split('/')[-2:]), data.get('title', '')[:40]))

    print(f"总文件: {len(paths)}")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if unmatched:
        print(f"\n未能匹配的文件（{len(unmatched)}个）:")
        for f, t in unmatched[:30]:
            print(f"  [{f}] {t}")
        if len(unmatched) > 30:
            print(f"  ...（共{len(unmatched)}个）")


if __name__ == '__main__':
    process_all()
