import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .domain import ContributorMode, JobRecord, MediaKind, MediaRecord
from .hashing import sha256_file
from .media.metadata import read_capture_time, run_ffprobe

_PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv"}
_MEDIA_FOLDER_NAMES = {MediaKind.PHOTO.value, MediaKind.VIDEO.value}


@dataclass(frozen=True, slots=True)
class ContributorSummary:
    name: str
    mode: ContributorMode
    file_count: int


@dataclass(frozen=True, slots=True)
class ScanResult:
    media: list[MediaRecord]
    contributors: list[ContributorSummary]
    ignored_files: tuple[Path, ...]

    @property
    def ignored_count(self) -> int:
        return len(self.ignored_files)


class ProbeRunner(Protocol):
    def __call__(self, path: Path) -> Mapping[str, Any]: ...


def scan_source(
    job: JobRecord,
    mode_overrides: Mapping[str, ContributorMode],
    *,
    ffprobe_runner: ProbeRunner = run_ffprobe,
) -> ScanResult:
    source_root = job.source_root.resolve()
    paths = sorted(path.resolve() for path in source_root.rglob("*") if path.is_file())
    supported_paths = [path for path in paths if _media_kind(path) is not None]
    ignored_files = tuple(path for path in paths if _media_kind(path) is None)
    contributor_modes = _contributor_modes(source_root, supported_paths, mode_overrides)
    media = [_media_record(job, source_root, path, contributor_modes, ffprobe_runner) for path in supported_paths]
    counts = {name: 0 for name in contributor_modes}
    for record in media:
        counts[record.contributor] += 1
    contributors = [ContributorSummary(name, mode, counts[name]) for name, mode in sorted(contributor_modes.items())]
    return ScanResult(media, contributors, ignored_files)


def _contributor_modes(
    source_root: Path,
    supported_paths: list[Path],
    overrides: Mapping[str, ContributorMode],
) -> dict[str, ContributorMode]:
    contributors = {path.relative_to(source_root).parts[0] for path in supported_paths if path.relative_to(source_root).parts}
    modes: dict[str, ContributorMode] = {}
    for contributor in contributors:
        child_directories = [path.name for path in (source_root / contributor).iterdir() if path.is_dir() and path.name]
        inferred = ContributorMode.UNCLASSIFIED if set(child_directories).issubset(_MEDIA_FOLDER_NAMES) else ContributorMode.CLASSIFIED
        modes[contributor] = overrides.get(contributor, inferred)
    return modes


def _media_record(
    job: JobRecord,
    source_root: Path,
    path: Path,
    contributor_modes: Mapping[str, ContributorMode],
    ffprobe_runner: ProbeRunner,
) -> MediaRecord:
    relative = path.relative_to(source_root)
    contributor = relative.parts[0]
    mode = contributor_modes[contributor]
    category = relative.parts[1] if mode is ContributorMode.CLASSIFIED and len(relative.parts) > 2 else None
    stat = path.stat()
    kind = _media_kind(path)
    assert kind is not None
    return MediaRecord(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, path.as_uri())),
        job_id=job.id,
        source_path=path,
        contributor=contributor,
        contributor_mode=mode,
        existing_category=category,
        media_kind=kind,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        captured_at=read_capture_time(path, kind, ffprobe_runner),
        sha256=sha256_file(path),
    )


def _media_kind(path: Path) -> MediaKind | None:
    suffix = path.suffix.lower()
    if suffix in _PHOTO_SUFFIXES:
        return MediaKind.PHOTO
    if suffix in _VIDEO_SUFFIXES:
        return MediaKind.VIDEO
    return None
