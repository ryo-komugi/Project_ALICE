from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class JobStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class Job:
    """ALICE_Core が管理する共通 Job モデル (ライフサイクル・進捗・成果物追跡対応)"""
    job_id: str
    user_id: str
    input_file: Path
    workspace_dir: Path
    status: JobStatus = JobStatus.CREATED
    workflow: list[str] = field(default_factory=lambda: ["transcript"])
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    error_message: str | None = None

    # 追跡・進捗メタデータ
    current_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_metadata: dict = field(default_factory=dict)
    step_history: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    error_detail: dict | None = None

    @property
    def input_dir(self) -> Path:
        return self.workspace_dir / "input"

    @property
    def transcript_dir(self) -> Path:
        return self.workspace_dir / "transcript"

    @property
    def minutes_dir(self) -> Path:
        return self.workspace_dir / "minutes"

    @property
    def summary_dir(self) -> Path:
        return self.workspace_dir / "summary"

    @property
    def logs_dir(self) -> Path:
        return self.workspace_dir / "logs"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "status": self.status.value,
            "workflow": self.workflow,
            "input_file": str(self.input_file),
            "workspace_dir": str(self.workspace_dir),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "current_step": self.current_step,
            "input_metadata": self.input_metadata,
            "step_history": self.step_history,
            "artifacts": self.artifacts,
            "error_detail": self.error_detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Job":
        """job.json の辞書から Job オブジェクトを復元する"""
        job = cls(
            job_id=data["job_id"],
            user_id=data["user_id"],
            input_file=Path(data["input_file"]),
            workspace_dir=Path(data["workspace_dir"]),
            status=JobStatus(data.get("status", JobStatus.CREATED.value)),
            workflow=data.get("workflow", ["transcript"]),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            error_message=data.get("error_message"),
            current_step=data.get("current_step"),
            input_metadata=data.get("input_metadata", {}),
            step_history=data.get("step_history", []),
            artifacts=data.get("artifacts", []),
            error_detail=data.get("error_detail"),
        )
        return job

