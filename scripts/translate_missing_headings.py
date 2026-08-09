#!/usr/bin/env python3
"""
补译 2022 版《刑诉解释》《民诉解释》缺失的结构节点英文标题。
翻译风格与 heading_en_map.json 已有条目保持一致（Chapter X / Section X）。
结果写回 nodes.content_en 并追加进 heading_en_map.json 缓存。
"""

import json
import sqlite3
from pathlib import Path

LAWS_DATA = Path(__file__).parent.parent
DB_PATH = LAWS_DATA / "law_content.db"
HEADING_MAP_PATH = LAWS_DATA / "references" / "heading_en_map.json"

# 缺失标题 → 英文翻译（与既有风格一致）
TRANSLATIONS = {
    # ── 2022 版《最高人民法院关于适用〈中华人民共和国刑事诉讼法〉的解释》──
    "第一章 管辖": "Chapter 1 Jurisdiction",
    "第二章 回避": "Chapter 2 Withdrawal",
    "第三章 辩护与代理": "Chapter 3 Defense and Representation",
    "第四章 证据": "Chapter 4 Evidence",
    "第一节 一般规定": "Section 1 General Provisions",
    "第二节 物证、书证的审查与认定": "Section 2 Examination and Determination of Physical and Documentary Evidence",
    "第三节 证人证言、被害人陈述的审查与认定": "Section 3 Examination and Determination of Witness Testimony and Statements of Victims",
    "第四节 被告人供述和辩解的审查与认定": "Section 4 Examination and Determination of Confessions and Defenses of the Defendant",
    "第五节 鉴定意见的审查与认定": "Section 5 Examination and Determination of Expert Opinion",
    "第六节 勘验、检查、辨认、侦查实验等笔录的审查与认定": "Section 6 Examination and Determination of Records of Inspection, Examination, Identification, and Investigative Experiment",
    "第七节 视听资料、电子数据的审查与认定": "Section 7 Examination and Determination of Audio-Visual Materials and Electronic Data",
    "第八节 技术调查、侦查证据的审查与认定": "Section 8 Examination and Determination of Evidence from Technical Investigation",
    "第九节 非法证据排除": "Section 9 Exclusion of Illegally Obtained Evidence",
    "第十节 证据的综合审查与运用": "Section 10 Comprehensive Examination and Application of Evidence",
    "第五章 强制措施": "Chapter 5 Compulsory Measures",
    "第六章 附带民事诉讼": "Chapter 6 Incidental Civil Actions",
    "第七章 期间、送达、审理期限": "Chapter 7 Time Periods, Service and Trial Duration",
    "第八章 审判组织": "Chapter 8 Trial Organization",
    "第九章 公诉案件第一审普通程序": "Chapter 9 Ordinary Procedure of First Instance for Public Prosecution Cases",
    "第一节 审查受理与庭前准备": "Section 1 Acceptance of Case Review and Pre-Trial Preparation",
    "第二节 庭前会议与庭审衔接": "Section 2 Pre-Trial Conference and Trial Connection",
    "第三节 宣布开庭与法庭调查": "Section 3 Opening of Trial and Court Investigation",
    "第四节 法庭辩论与最后陈述": "Section 4 Court Debate and Final Statements",
    "第五节 评议案件与宣告判决": "Section 5 Deliberation and Pronouncement of Judgment",
    "第六节 法庭纪律与其他规定": "Section 6 Court Discipline and Other Provisions",
    "第十章 自诉案件第一审程序": "Chapter 10 Procedure of First Instance for Private Prosecution Cases",
    "第十一章 单位犯罪案件的审理": "Chapter 11 Trial of Cases Involving Crimes Committed by Units",
    "第十二章 认罪认罚案件的审理": "Chapter 12 Trial of Cases with Admission of Guilt and Acceptance of Punishment",
    "第十三章 简易程序": "Chapter 13 Summary Procedure",
    "第十四章 速裁程序": "Chapter 14 Expedited Procedure",
    "第十五章 第二审程序": "Chapter 15 Procedure of Second Instance",
    "第十六章 在法定刑以下判处刑罚和特殊假释的核准": "Chapter 16 Approval of Sentences Below the Statutory Penalty and Special Parole",
    "第十七章 死刑复核程序": "Chapter 17 Procedure for Review of Death Sentences",
    "第十八章 涉案财物处理": "Chapter 18 Handling of Case-Related Property",
    "第十九章 审判监督程序": "Chapter 19 Procedure for Trial Supervision",
    "第二十章 涉外刑事案件的审理和刑事司法协助": "Chapter 20 Trial of Criminal Cases with Foreign Elements and Criminal Judicial Assistance",
    "第一节 涉外刑事案件的审理": "Section 1 Trial of Criminal Cases with Foreign Elements",
    "第二节 刑事司法协助": "Section 2 Criminal Judicial Assistance",
    "第二十一章 执行程序": "Chapter 21 Enforcement Procedure",
    "第一节 死刑的执行": "Section 1 Execution of Death Sentences",
    "第二节 死刑缓期执行、无期徒刑、有期徒刑、拘役的交付执行": "Section 2 Delivery for Execution of Death Sentence with Reprieve, Life Imprisonment, Fixed-Term Imprisonment and Criminal Detention",
    "第三节 管制、缓刑、剥夺政治权利的交付执行": "Section 3 Delivery for Execution of Public Surveillance, Probation and Deprivation of Political Rights",
    "第四节 刑事裁判涉财产部分和附带民事裁判的执行": "Section 4 Enforcement of Property-Related Parts of Criminal Judgments and Incidental Civil Judgments",
    "第五节 减刑、假释案件的审理": "Section 5 Trial of Cases of Commutation of Sentences and Parole",
    "第六节 缓刑、假释的撤销": "Section 6 Revocation of Probation and Parole",
    "第二十二章 未成年人刑事案件诉讼程序": "Chapter 22 Criminal Procedure for Cases Involving Minors",
    "第二节 开庭准备": "Section 2 Preparation for Court Session",
    "第三节 审判": "Section 3 Trial",
    "第四节 执行": "Section 4 Enforcement",
    "第二十三章 当事人和解的公诉案件诉讼程序": "Chapter 23 Procedure for Public Prosecution Cases with Settlement Between Parties",
    "第二十四章 缺席审判程序": "Chapter 24 Procedure for Trial in Absentia",
    "第二十五章 犯罪嫌疑人、被告人逃匿、死亡案件违法所得的没收程序": "Chapter 25 Procedure for Confiscation of Illegal Gains in Cases Where the Criminal Suspect or Defendant Escapes or Dies",
    "第二十六章 依法不负刑事责任的精神病人的强制医疗程序": "Chapter 26 Procedure for Compulsory Medical Treatment of Mentally Ill Persons Who Are Not Criminally Responsible According to Law",
    "第二十七章 附则": "Chapter 27 Supplementary Provisions",
    # ── 2022 版《最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释》──
    "一、管辖": "1. Jurisdiction",
    "二、回避": "2. Withdrawal",
    "三、诉讼参加人": "3. Participants in Proceedings",
    "四、证据": "4. Evidence",
    "五、期间和送达": "5. Time Periods and Service",
    "六、调解": "6. Mediation",
    "七、保全和先予执行": "7. Preservation and Advance Execution",
    "八、对妨害民事诉讼的强制措施": "8. Compulsory Measures Against Obstruction of Civil Proceedings",
    "九、诉讼费用": "9. Litigation Costs",
    "十、第一审普通程序": "10. Ordinary Procedure of First Instance",
    "十一、简易程序": "11. Summary Procedure",
    "十二、简易程序中的小额诉讼": "12. Small Claims in Summary Procedure",
    "十三、公益诉讼": "13. Public Interest Litigation",
    "十四、第三人撤销之诉": "14. Third-Party Revocation Action",
    "十五、执行异议之诉": "15. Action of Objection to Enforcement",
    "十六、第二审程序": "16. Procedure of Second Instance",
    "十七、特别程序": "17. Special Procedure",
    "十八、审判监督程序": "18. Procedure for Trial Supervision",
    "十九、督促程序": "19. Urgency Procedure",
    "二十、公示催告程序": "20. Procedure for Public Exhortation",
    "二十一、执行程序": "21. Enforcement Procedure",
    "二十二、涉外民事诉讼程序的特别规定": "22. Special Provisions for Civil Proceedings with Foreign Elements",
    "二十三、附则": "23. Supplementary Provisions",
}

def main():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT n.id, n.law_id, n.type, COALESCE(n.order_index, 0), n.title
        FROM nodes n JOIN laws l ON n.law_id = l.id
        WHERE n.type IN ('part','chapter','section')
          AND (n.content_en IS NULL OR n.content_en = '')
        ORDER BY n.law_id, n.id
    """).fetchall()

    updated = 0
    missing = []
    for node_id, law_id, ntype, oi, title in rows:
        en = TRANSLATIONS.get(title)
        if en is None:
            missing.append((law_id, ntype, title))
            continue
        conn.execute(
            "UPDATE nodes SET content_en = ? WHERE id = ?",
            (en, node_id)
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"已写入 {updated} 条（剩余未覆盖 {len(missing)}）")
    for m in missing:
        print("  未覆盖:", m)

    # 追加到 heading_en_map.json 缓存
    if HEADING_MAP_PATH.exists():
        heading_map = json.loads(HEADING_MAP_PATH.read_text(encoding="utf-8"))
    else:
        heading_map = {}
    conn = sqlite3.connect(str(DB_PATH))
    rows2 = conn.execute("""
        SELECT n.law_id, n.type, COALESCE(n.order_index, 0), n.title
        FROM nodes n JOIN laws l ON n.law_id = l.id
        WHERE n.type IN ('part','chapter','section')
        ORDER BY n.law_id, n.global_order
    """).fetchall()
    conn.close()
    added = 0
    for law_id, ntype, oi, title in rows2:
        en = TRANSLATIONS.get(title)
        if en is None:
            continue
        key = f"{law_id}:{ntype}:{oi}"
        if key not in heading_map:
            heading_map[key] = en
            added += 1
    HEADING_MAP_PATH.write_text(
        json.dumps(heading_map, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"heading_en_map.json 追加 {added} 条（现有 {len(heading_map)} 条）")

if __name__ == "__main__":
    main()
