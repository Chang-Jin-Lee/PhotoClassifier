from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path


class JobPhase(StrEnum):
    CREATED = "created"
    SCANNED = "scanned"
    MERGES_REVIEWED = "merges_reviewed"
    ANALYZING = "analyzing"
    CLASSIFICATION_REVIEW = "classification_review"
    PLAN_CONFIRMED = "plan_confirmed"
    COPYING = "copying"
    VERIFIED = "verified"


class ContributorMode(StrEnum):
    CLASSIFIED = "classified"
    UNCLASSIFIED = "unclassified"


class MediaKind(StrEnum):
    PHOTO = "사진"
    VIDEO = "동영상"


class DecisionSource(StrEnum):
    EXISTING = "existing_folder"
    AUTO = "automatic"
    USER = "user"
    DEFERRED = "deferred"


class CopyStatus(StrEnum):
    PLANNED = "planned"
    COPYING = "copying"
    VERIFIED = "verified"
    DUPLICATE = "duplicate"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    source_root: Path
    output_parent: Path
    output_root: Path
    phase: JobPhase
    created_at: datetime

    @classmethod
    def new(cls, job_id: str, source_root: Path, output_parent: Path, *, now: datetime | None = None) -> "JobRecord":
        created_at = now or datetime.now(UTC)
        local_time = created_at.astimezone()
        output_root = output_parent / f"편집자전달용_{local_time:%Y%m%d_%H%M%S}"
        return cls(job_id, source_root, output_parent, output_root, JobPhase.CREATED, created_at)


@dataclass(frozen=True, slots=True)
class MediaRecord:
    id: str
    job_id: str
    source_path: Path
    contributor: str
    contributor_mode: ContributorMode
    existing_category: str | None
    media_kind: MediaKind
    size_bytes: int
    mtime_ns: int
    captured_at: datetime | None
    sha256: str
    analysis_error: str | None = None


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    media_id: str
    category: str
    source: DecisionSource
    confidence_label: str
    score: float | None
    alternative_category: str | None


@dataclass(frozen=True, slots=True)
class ProcessingError:
    media_id: str | None
    stage: str
    source_path: Path
    summary: str
    retryable: bool
