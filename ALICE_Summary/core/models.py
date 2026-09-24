from typing import Any, Optional, List, Dict
from pydantic import BaseModel, Field, ConfigDict


class Topic(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(default="無題の論点", description="議題タイトル")
    issue: str = Field(default="", description="問題や課題")
    confirmed_facts: List[str] = Field(default_factory=list, description="確認された事実")
    participant_statements: List[str] = Field(default_factory=list, description="本人の説明・認識")
    interviewer_statements: List[str] = Field(default_factory=list, description="相手側の指摘・評価")
    evolution_and_resolution: str = Field(default="", description="進展と着地点")
    agreed_points: List[str] = Field(default_factory=list, description="合意事項")


class TimelineSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    start_time: str = Field(default="", description="セクション開始時刻 (mm:ss または hh:mm:ss)")
    end_time: str = Field(default="", description="セクション終了時刻 (mm:ss または hh:mm:ss)")
    section_title: str = Field(default="無題のセクション", description="セクション・議題の見出し")
    interviewer_inquiry: str = Field(default="", description="面談側・進行役の問いかけ・指摘・要求")
    participant_initial_statement: str = Field(default="", description="対象者・参加者の初期回答・主張・弁明")
    contradictions_and_evidence: List[str] = Field(default_factory=list, description="指摘された矛盾点・現場からの目撃報告や客観事実")
    uncovered_facts_confession: List[str] = Field(default_factory=list, description="追及により段階的に判明・後出し自白した生々しい実態")
    agreed_rules_and_decisions: List[str] = Field(default_factory=list, description="確定した新ルール・運用・合意事項")


class SpeakerAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    speaker_label: str = Field(default="UNKNOWN", description="話者ラベル")
    estimated_role: str = Field(default="不明", description="推定役割")
    basis: str = Field(default="", description="推定根拠")


class ConversationOverview(BaseModel):
    model_config = ConfigDict(extra="allow")

    purpose: str = Field(default="", description="会話目的")
    background: str = Field(default="", description="背景コンテキスト")


class NextAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    actor: str = Field(default="関係者", description="担当者")
    action: str = Field(default="", description="アクション内容")
    deadline_or_condition: str = Field(default="", description="期限や条件")


class ConclusionsAndActions(BaseModel):
    model_config = ConfigDict(extra="allow")

    decisions: List[str] = Field(default_factory=list, description="決定事項")
    next_actions: List[NextAction] = Field(default_factory=list, description="アクション項目")


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
