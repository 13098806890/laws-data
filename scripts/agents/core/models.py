from dataclasses import dataclass


@dataclass
class SubExpert:
    """细分专家定义"""
    name: str
    domain: str
    # required_info: list of (field_name, question_text, extraction_hint_regex)
    required_info: list[tuple[str, str, str]]
    law_titles: list[str]
    chapter_ids_hint: list[int]
    fts_domains: list[str]
    fts_categories: list[str]
    fts_keywords_extra: list[str]
    answer_template: str


@dataclass
class ExpertGroup:
    """专家组定义"""
    name: str
    description: str
    sub_experts: list[SubExpert]
    routing_keywords: list[str]
