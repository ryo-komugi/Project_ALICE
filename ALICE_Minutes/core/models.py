"""
Data models and Pydantic schemas for ALICE_Minute.
Supports Pydantic V2 with extra field tolerance for robust LLM JSON parsing.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MeetingOverview(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = Field(description="会議・打合せ・面談の件名（会話文脈から簡潔に命名）")
    purpose: str = Field(description="会議・対話の目的・趣旨")
    date_time_context: Optional[str] = Field(default=None, description="発話内で言及された日時や文脈")
    meeting_type: Optional[str] = Field(
        default="一般会議",
        description="会議の種別（例: 業務進捗定例, 1on1・面談, 役員協議, トラブル対策会議など）",
    )


class Participant(BaseModel):
    model_config = ConfigDict(extra="allow")

    speaker_label: str = Field(description="話者ラベル（例: SPEAKER_00）")
    display_name: Optional[str] = Field(
        default=None, description="特定された実名または敬称（例: 伊藤氏, 田中マネージャー）"
    )
    estimated_role: str = Field(
        description="推定される役割や肩書（例: 指導役・上司, 対象者, 進行役など）"
    )
    basis: str = Field(description="役割推定の根拠となった発言や文脈")


class KeyOpinion(BaseModel):
    model_config = ConfigDict(extra="allow")

    speaker: str = Field(description="発言者（話者名またはラベル）")
    opinion: str = Field(description="主な主張・意見・説明")
    time_anchor: Optional[str] = Field(
        default=None, description="発言の開始タイムスタンプ（例: 05:20）"
    )


class AgendaItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    agenda_title: str = Field(description="議題・討議テーマのタイトル")
    time_range: Optional[str] = Field(
        default=None, description="議論の該当時間帯（例: 00:08 - 04:24）"
    )
    discussion_summary: str = Field(
        description="議論の要約（何が論点となり、どう検討されたか）"
    )
    key_opinions: List[KeyOpinion] = Field(
        default_factory=list, description="主な発言・意見"
    )
    decisions: List[str] = Field(
        default_factory=list, description="この議題において確定した決定事項・合意内容"
    )
    rationale: Optional[str] = Field(
        default=None, description="決定に至った背景や論拠"
    )


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    task: str = Field(description="具体的なアクション・TODO内容")
    assignee: str = Field(description="担当者・責任者（誰が実行するか）")
    due_date: str = Field(
        description="完了期限（いつまでに。日付や『明日中』『来週金曜17時』など明確に）"
    )
    deliverable_or_condition: Optional[str] = Field(
        default=None, description="成果物または完了条件（提出物、システム設定、報告等）"
    )
    priority: str = Field(
        default="MEDIUM",
        description="優先度（HIGH: 至急・重大, MEDIUM: 通常, LOW: 任意・低）",
    )
    status_agreement: str = Field(
        default="合意済",
        description="合意状況（合意済: 本人が明確にコミット, 指導指示: 上司・相手からの業務命令, 宿題要確認: 持ち帰り）",
    )
    time_context: Optional[str] = Field(
        default=None, description="タスクが発生・言及されたタイムスタンプ（例: 12:45）"
    )


class PendingTopic(BaseModel):
    model_config = ConfigDict(extra="allow")

    topic: str = Field(description="保留事項・未決事項・次回持ち越しテーマ・検討中課題")
    reason: str = Field(description="保留となった理由（他部門確認待ち、見積もり未着、検証中など）")
    next_action: Optional[str] = Field(
        default=None, description="今後どのように扱うか、次回の対応"
    )
    checkpoint_date: Optional[str] = Field(
        default=None, description="確認予定期日（いつ再確認するか）"
    )


class MinuteAnalysisResult(BaseModel):
    """Stage 1 で会話全体から抽出・構造化される議事録データモデル"""
    model_config = ConfigDict(extra="allow")

    meeting_overview: MeetingOverview = Field(description="会議概要")
    participants: List[Participant] = Field(
        default_factory=list, description="出席者・話者の役割分析"
    )
    agenda_items: List[AgendaItem] = Field(
        default_factory=list, description="議題ごとの議論と決定"
    )
    action_items: List[ActionItem] = Field(
        default_factory=list, description="アクションアイテム（TODO一覧）"
    )
    confirmed_decisions: List[str] = Field(
        default_factory=list, description="会議全体で確定した重要決定事項の一覧"
    )
    pending_and_next_topics: List[PendingTopic] = Field(
        default_factory=list, description="保留・持ち越し事項"
    )
