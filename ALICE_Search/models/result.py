"""ALICE_Search 検索結果モデル

特定モジュールに依存しない中立的な検索結果表現を提供し、
検索結果から Workspace 上の正本 Artifact へ完全に辿れるようにする。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class SearchHit:
    """単一の検索ヒット項目"""

    job_id: str
    user_id: str
    module: str
    artifact_name: str
    artifact_rel_path: str
    workspace_dir: str
    artifact_abs_path: str
    snippet: str
    rank_score: float
    created_at: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "module": self.module,
            "artifact_name": self.artifact_name,
            "artifact_rel_path": self.artifact_rel_path,
            "workspace_dir": self.workspace_dir,
            "artifact_abs_path": self.artifact_abs_path,
            "snippet": self.snippet,
            "rank_score": self.rank_score,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class SearchResult:
    """検索結果全体"""

    total: int
    query: str | None
    filters: dict
    hits: list[SearchHit] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "query": self.query,
            "filters": self.filters,
            "hits": [hit.to_dict() for hit in self.hits],
        }
