"""
Pipeline state persistence.
Each listing run has a state.json in its workspace directory.
State is the source of truth for which stages have completed and what their outputs were.
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path


class EtsyPipelineStage(str, Enum):
    NICHE_RESEARCH     = "niche_research"
    STORE_SUGGESTION   = "store_suggestion"
    PRODUCT_DESIGN     = "product_design"
    MOCKUP_GENERATION  = "mockup_generation"
    LISTING_GENERATION = "listing_generation"
    LISTING_UPLOAD     = "listing_upload"
    PERFORMANCE_SYNC   = "performance_sync"


class StageStatus(str, Enum):
    PENDING           = "pending"
    RUNNING           = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED          = "approved"
    REJECTED          = "rejected"
    COMPLETED         = "completed"
    FAILED            = "failed"


@dataclass
class StageRecord:
    stage: EtsyPipelineStage
    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    cost_usd: float = 0.0
    error: str | None = None
    outputs: dict = field(default_factory=dict)


@dataclass
class ListingState:
    listing_id: str
    store_slug: str
    created_at: str
    updated_at: str
    stages: dict = field(default_factory=dict)  # stage name -> StageRecord dict
    metadata: dict = field(default_factory=dict)  # title, product_type, niche_report_id, etc.
    total_cost_usd: float = 0.0

    @classmethod
    def create(cls, store_slug: str, metadata: dict | None = None) -> "ListingState":
        now = _now()
        listing_id = f"lst_{datetime.now(timezone.utc).strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        return cls(
            listing_id=listing_id,
            store_slug=store_slug,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )

    def get_stage(self, stage: EtsyPipelineStage) -> StageRecord:
        if stage.value not in self.stages:
            self.stages[stage.value] = asdict(StageRecord(stage=stage))
        record_dict = self.stages[stage.value]
        return StageRecord(
            stage=EtsyPipelineStage(record_dict["stage"]),
            status=StageStatus(record_dict["status"]),
            started_at=record_dict.get("started_at"),
            completed_at=record_dict.get("completed_at"),
            cost_usd=record_dict.get("cost_usd", 0.0),
            error=record_dict.get("error"),
            outputs=record_dict.get("outputs", {}),
        )

    def update_stage(self, stage: EtsyPipelineStage, **kwargs) -> None:
        if stage.value not in self.stages:
            self.stages[stage.value] = asdict(StageRecord(stage=stage))
        self.stages[stage.value].update(kwargs)
        if "cost_usd" in kwargs:
            self.total_cost_usd = sum(s.get("cost_usd", 0.0) for s in self.stages.values())
        self.updated_at = _now()

    def mark_stage_started(self, stage: EtsyPipelineStage) -> None:
        self.update_stage(stage, status=StageStatus.RUNNING.value, started_at=_now())

    def mark_stage_completed(self, stage: EtsyPipelineStage, outputs: dict, cost_usd: float = 0.0) -> None:
        self.update_stage(
            stage,
            status=StageStatus.COMPLETED.value,
            completed_at=_now(),
            outputs=outputs,
            cost_usd=cost_usd,
        )

    def mark_stage_failed(self, stage: EtsyPipelineStage, error: str) -> None:
        self.update_stage(stage, status=StageStatus.FAILED.value, error=error, completed_at=_now())

    def mark_stage_awaiting_approval(self, stage: EtsyPipelineStage) -> None:
        self.update_stage(stage, status=StageStatus.AWAITING_APPROVAL.value)

    def is_stage_complete(self, stage: EtsyPipelineStage) -> bool:
        return self.get_stage(stage).status == StageStatus.COMPLETED


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateManager:
    """Read/write ListingState to workspace directory."""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir

    def _state_path(self, store_slug: str, listing_id: str) -> Path:
        return self.workspace_dir / store_slug / listing_id / "state.json"

    def save(self, state: ListingState) -> None:
        path = self._state_path(state.store_slug, state.listing_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

    def load(self, store_slug: str, listing_id: str) -> ListingState:
        path = self._state_path(store_slug, listing_id)
        if not path.exists():
            raise FileNotFoundError(f"No state found for {store_slug}/{listing_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ListingState(**data)

    def exists(self, store_slug: str, listing_id: str) -> bool:
        return self._state_path(store_slug, listing_id).exists()

    def list_listings(self, store_slug: str) -> list[str]:
        store_dir = self.workspace_dir / store_slug
        if not store_dir.exists():
            return []
        return [
            d.name for d in store_dir.iterdir()
            if d.is_dir() and not d.name.startswith("_") and (d / "state.json").exists()
        ]
