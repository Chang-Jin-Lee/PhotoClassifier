from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from time import sleep

import pytest

from photoclassifier.domain import JobPhase, JobRecord, MediaRecord
from photoclassifier.store import JobStore


def test_job_round_trip_and_allowed_transition(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    job = JobRecord(
        id="job-1",
        source_root=tmp_path / "수집",
        output_parent=tmp_path / "결과",
        output_root=tmp_path / "결과" / "편집자전달용_20260901_000000",
        phase=JobPhase.CREATED,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    store.create_job(job)
    store.transition("job-1", JobPhase.SCANNED)

    assert store.get_job("job-1").phase is JobPhase.SCANNED


def test_job_rejects_skipped_transition(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    store.create_job(JobRecord.new(
        "job-1",
        tmp_path / "수집",
        tmp_path / "결과",
        now=datetime(2026, 9, 1, tzinfo=UTC),
    ))

    with pytest.raises(ValueError, match="CREATED.*ANALYZING"):
        store.transition("job-1", JobPhase.ANALYZING)


def test_get_job_waits_for_store_lock(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    store.create_job(JobRecord.new("job-1", tmp_path / "in", tmp_path / "out"))
    started = Event()
    finished = Event()

    def read_job() -> None:
        started.set()
        store.get_job("job-1")
        finished.set()

    store._lock.acquire()
    worker = Thread(target=read_job)
    worker.start()
    assert started.wait(1)
    sleep(0.05)
    assert not finished.is_set()
    store._lock.release()
    worker.join(1)
    assert finished.is_set()


def test_replace_media_rejects_records_for_another_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    store.create_job(JobRecord.new("job-1", tmp_path / "in", tmp_path / "out"))
    store.create_job(JobRecord.new("job-2", tmp_path / "in2", tmp_path / "out2"))
    from photoclassifier.domain import ContributorMode, MediaKind, MediaRecord

    record = MediaRecord(
        id="media-1", job_id="job-2", source_path=tmp_path / "photo.jpg",
        contributor="alice", contributor_mode=ContributorMode.CLASSIFIED,
        existing_category=None, media_kind=MediaKind.PHOTO, size_bytes=1,
        mtime_ns=1, captured_at=None, sha256="hash",
    )
    with pytest.raises(ValueError, match="job-1"):
        store.replace_media("job-1", [record])


def test_store_replaces_media_atomically(tmp_path: Path, scanned_media: list[MediaRecord]) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    store.create_job(JobRecord.new("job-1", tmp_path / "수집", tmp_path / "out"))

    store.replace_media("job-1", scanned_media)
    store.replace_media("job-1", scanned_media[:1])

    assert store.list_media("job-1") == scanned_media[:1]


def test_save_aliases_replaces_existing_sources_transactionally(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    store.create_job(JobRecord.new("job-1", tmp_path / "in", tmp_path / "out"))
    store.save_aliases("job-1", {"old": "canonical", "other": "name"})
    store.save_aliases("job-1", {"old": "new-canonical"})
    assert store.list_aliases("job-1") == {"old": "new-canonical", "other": "name"}
