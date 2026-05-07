from ...core.models import SubExpert

_CRIMINAL_CHAPTER_PROPERTY   = 22116
_CRIMINAL_CHAPTER_PERSON     = 22084
_CRIMINAL_CHAPTER_ECONOMY    = 22083
_CRIMINAL_CHAPTER_CORRUPTION = 22247
_CRIMINAL_CHAPTER_DERELICTION = 22263

CRIME_PROPERTY_EXPERT = SubExpert(
    name="财产犯罪专家",
    domain="盗窃、诈骗、抢劫、敲诈勒索、侵占",
    required_info=[
        ("犯罪行为", "具体行为是什么（盗窃/诈骗/抢劫/敲诈/侵占）？",
                     r"盗窃|诈骗|抢劫|抢夺|敲诈勒索|侵占|挪用|骗取"),
        ("涉案金额", "涉及金额是多少？",
                     r"\d+\s*(?:万|元|块|百|千|亿)"),
        ("主观状态", "行为人是否有犯罪故意（主观故意还是过失）？",
                     r"故意|明知|蓄意|有意|过失|不知道|不清楚"),
        ("是否既遂", "犯罪行为是否完成（既遂/未遂/中止）？",
                     r"既遂|未遂|中止|未成功|被抓|被发现"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_PROPERTY],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["盗窃罪", "诈骗罪", "抢劫罪", "数额较大", "数额巨大"],
    answer_template=(
        "你是财产犯罪刑法细分专家。基于以下法条，分析：\n"
        "1. 行为构成何种犯罪（罪名及构成要件分析）\n"
        "2. 法定刑幅度（量刑区间）\n"
        "3. 数额认定标准（较大/巨大/特别巨大）\n"
        "4. 从重/从轻/减轻情节\n"
        "明确引用刑法条文和相关司法解释。"
    ),
)

CRIME_PERSON_EXPERT = SubExpert(
    name="人身伤害专家",
    domain="故意伤害、故意杀人、强奸、绑架、非法拘禁",
    required_info=[
        ("犯罪行为",   "具体行为是什么（故意伤害/故意杀人/强奸/绑架/非法拘禁）？",
                       r"故意伤害|故意杀人|强奸|绑架|拘禁|殴打|人身自由|强制"),
        ("伤害程度",   "受害人伤情如何（轻伤/重伤/死亡/轻微伤）？",
                       r"轻伤|重伤|死亡|轻微伤|残疾|鉴定|司法鉴定"),
        ("行为人年龄", "行为人是否成年？",
                       r"\d+岁|未成年|成年|刑事责任年龄"),
        ("是否自首",   "行为人是否有自首或立功表现？",
                       r"自首|投案|立功|坦白|如实供述"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_PERSON],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["故意伤害罪", "故意杀人罪", "刑事附带民事", "伤残等级"],
    answer_template=(
        "你是人身伤害刑法细分专家。基于以下法条，分析：\n"
        "1. 罪名认定（故意伤害/故意杀人/其他侵犯人身罪）\n"
        "2. 法定刑（轻伤/重伤/死亡对应量刑）\n"
        "3. 刑事附带民事赔偿范围\n"
        "4. 自首/立功的量刑影响\n"
        "引用刑法条文，说明刑事追诉标准。"
    ),
)

CRIME_ECONOMY_EXPERT = SubExpert(
    name="经济犯罪专家",
    domain="合同诈骗、生产销售伪劣商品、走私、破坏市场秩序",
    required_info=[
        ("犯罪类型", "属于哪类经济犯罪（合同诈骗/销售假冒伪劣/走私/非法经营/洗钱）？",
                     r"合同诈骗|假冒伪劣|走私|非法经营|洗钱|虚假广告|串通投标"),
        ("涉案金额", "涉案金额是多少？",
                     r"\d+\s*(?:万|元|块|百|千|亿)"),
        ("主体身份", "行为主体是个人还是单位（公司）？",
                     r"个人|单位犯罪|公司|企业|法定代表人|直接责任人"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_ECONOMY],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["合同诈骗", "生产销售伪劣", "非法经营", "单位犯罪"],
    answer_template=(
        "你是经济犯罪刑法细分专家。基于以下法条，分析：\n"
        "1. 经济犯罪的罪名及构成要件\n"
        "2. 单位犯罪与自然人犯罪的区别处理\n"
        "3. 量刑标准（数额/情节）\n"
        "4. 退赔对量刑的影响\n"
        "引用刑法条文和相关司法解释。"
    ),
)

CRIME_CORRUPTION_EXPERT = SubExpert(
    name="腐败职务犯罪专家",
    domain="贪污贿赂、渎职、滥用职权、玩忽职守",
    required_info=[
        ("犯罪类型", "是哪类职务犯罪（贪污/受贿/行贿/挪用公款/滥用职权/玩忽职守）？",
                     r"贪污|受贿|行贿|挪用公款|滥用职权|玩忽职守|失职"),
        ("主体身份", "行为人是什么身份（国家工作人员/公司人员/国有企业人员）？",
                     r"国家工作人员|公务员|国有企业|事业单位|村委会|公司|官员"),
        ("涉案金额", "涉案金额（贪污/受贿/挪用金额）？",
                     r"\d+\s*(?:万|元|块|百|千|亿)"),
    ],
    law_titles=["中华人民共和国刑法"],
    chapter_ids_hint=[_CRIMINAL_CHAPTER_CORRUPTION, _CRIMINAL_CHAPTER_DERELICTION],
    fts_domains=["刑法"],
    fts_categories=["法律", "司法解释"],
    fts_keywords_extra=["贪污罪", "受贿罪", "挪用公款", "渎职罪", "量刑标准"],
    answer_template=(
        "你是腐败职务犯罪刑法细分专家。基于以下法条，分析：\n"
        "1. 罪名认定（贪污/受贿/渎职等）及主体要件\n"
        "2. 量刑档次（3万/20万/300万等数额标准）\n"
        "3. 主动退赃和认罪认罚的量刑影响\n"
        "4. 监察调查与刑事诉讼的衔接\n"
        "明确引用刑法条文及最高院司法解释。"
    ),
)

ALL_CRIMINAL_EXPERTS = [
    CRIME_PROPERTY_EXPERT,
    CRIME_PERSON_EXPERT,
    CRIME_ECONOMY_EXPERT,
    CRIME_CORRUPTION_EXPERT,
]
