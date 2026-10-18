import re
from typing import Any, Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


def _clean_str_list(v: Any) -> List[str]:
    if not isinstance(v, list):
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []
    cleaned = []
    for item in v:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
        elif isinstance(item, dict):
            # In case LLM outputs dict items inside a string list
            vals = [str(val).strip() for val in item.values() if val is not None and str(val).strip()]
            if vals:
                cleaned.append(" / ".join(vals))
    return cleaned


class Topic(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(default="無題の論点", description="議題タイトル")
    issue: str = Field(default="", description="問題や課題")
    confirmed_facts: List[str] = Field(default_factory=list, description="確認された事実")
    participant_statements: List[str] = Field(default_factory=list, description="本人の説明・認識")
    interviewer_statements: List[str] = Field(default_factory=list, description="相手側の指摘・評価")
    evolution_and_resolution: str = Field(default="", description="進展と着地点")
    agreed_points: List[str] = Field(default_factory=list, description="合意事項")

    @field_validator("confirmed_facts", "participant_statements", "interviewer_statements", "agreed_points", mode="before")
    @classmethod
    def validate_str_lists(cls, v: Any) -> List[str]:
        return _clean_str_list(v)

    @field_validator("title", "issue", "evolution_and_resolution", mode="before")
    @classmethod
    def validate_str_fields(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""


class TimelineSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    start_time: str = Field(default="", description="セクション開始時刻 (mm:ss または hh:mm:ss)")
    end_time: str = Field(default="", description="セクション終了時刻 (mm:ss または hh:mm:ss)")
    section_title: str = Field(default="無題のセクション", description="セクション・議題の見出し")
    interviewer_inquiry: str = Field(default="", description="面談側・進行役の問いかけ・指摘・要求")
    participant_initial_statement: str = Field(default="", description="対象者・参加者の回答・説明・意見")
    contradictions_and_evidence: List[str] = Field(default_factory=list, description="指摘された矛盾点・客観的事実（該当がある場合のみ）")
    uncovered_facts_confession: List[str] = Field(default_factory=list, description="議論や確認により新たに判明した事実・実態（該当がある場合のみ）")
    agreed_rules_and_decisions: List[str] = Field(default_factory=list, description="確定した方針・ルール・運用・合意事項")

    @model_validator(mode="before")
    @classmethod
    def normalize_corrupted_keys(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = {}
        known_keys = {
            "start_time",
            "end_time",
            "section_title",
            "interviewer_inquiry",
            "participant_initial_statement",
            "contradictions_and_evidence",
            "uncovered_facts_confession",
            "agreed_rules_and_decisions",
        }
        for k, v in data.items():
            clean_k = re.sub(r"[^a-z_]", "", str(k).lower())
            if clean_k in known_keys:
                normalized[clean_k] = v
            elif "agreed" in clean_k and "decision" in clean_k:
                normalized["agreed_rules_and_decisions"] = v
            elif "contradiction" in clean_k or "evidence" in clean_k:
                normalized["contradictions_and_evidence"] = v
            elif "uncovered" in clean_k or "confession" in clean_k:
                normalized["uncovered_facts_confession"] = v
            else:
                normalized[k] = v
        return normalized

    @field_validator("contradictions_and_evidence", "uncovered_facts_confession", "agreed_rules_and_decisions", mode="before")
    @classmethod
    def validate_str_lists(cls, v: Any) -> List[str]:
        return _clean_str_list(v)

    @field_validator("start_time", "end_time", "section_title", "interviewer_inquiry", "participant_initial_statement", mode="before")
    @classmethod
    def validate_str_fields(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""


class SpeakerAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    speaker_label: str = Field(default="UNKNOWN", description="話者ラベル")
    estimated_role: str = Field(default="不明", description="推定役割")
    basis: str = Field(default="", description="推定根拠")

    @field_validator("speaker_label", "estimated_role", "basis", mode="before")
    @classmethod
    def validate_str_fields(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""


class ConversationOverview(BaseModel):
    model_config = ConfigDict(extra="allow")

    purpose: str = Field(default="", description="会話目的")
    background: str = Field(default="", description="背景コンテキスト")

    @field_validator("purpose", "background", mode="before")
    @classmethod
    def validate_str_fields(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""


class NextAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    actor: str = Field(default="関係者", description="担当者")
    action: str = Field(default="", description="アクション内容")
    deadline_or_condition: str = Field(default="", description="期限や条件")

    @field_validator("actor", "action", "deadline_or_condition", mode="before")
    @classmethod
    def validate_str_fields(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""


class ConclusionsAndActions(BaseModel):
    model_config = ConfigDict(extra="allow")

    decisions: List[str] = Field(default_factory=list, description="決定事項")
    next_actions: List[NextAction] = Field(default_factory=list, description="アクション項目")

    @field_validator("decisions", mode="before")
    @classmethod
    def validate_decisions(cls, v: Any) -> List[str]:
        return _clean_str_list(v)

    @field_validator("next_actions", mode="before")
    @classmethod
    def validate_next_actions(cls, v: Any) -> List[Any]:
        if not isinstance(v, list):
            return []
        return [item for item in v if isinstance(item, (dict, NextAction))]


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    metadata: Dict[str, Any] = Field(default_factory=dict)
    conversation_overview: ConversationOverview = Field(default_factory=ConversationOverview)
    speakers_analysis: List[SpeakerAnalysis] = Field(default_factory=list)
    timeline_sections: List[TimelineSection] = Field(default_factory=list, description="時系列アジェンダ別の詳細構造")
    topics: List[Topic] = Field(default_factory=list, description="後方互換用トピックリスト")
    overall_common_issues: List[str] = Field(default_factory=list)
    conclusions_and_actions: ConclusionsAndActions = Field(default_factory=ConclusionsAndActions)
    uncertain_or_ambiguous_points: List[str] = Field(default_factory=list)

    @field_validator("overall_common_issues", "uncertain_or_ambiguous_points", mode="before")
    @classmethod
    def validate_str_lists(cls, v: Any) -> List[str]:
        return _clean_str_list(v)
