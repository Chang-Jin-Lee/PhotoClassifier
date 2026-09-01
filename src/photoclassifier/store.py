import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from .domain import (ClassificationDecision, ContributorMode, DecisionSource,
                     JobPhase, JobRecord, MediaKind, MediaRecord)

_PHASE_ORDER = list(JobPhase)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, source_root TEXT NOT NULL, output_parent TEXT NOT NULL, output_root TEXT NOT NULL, phase TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS media (job_id TEXT NOT NULL, id TEXT NOT NULL, source_path TEXT NOT NULL, contributor TEXT NOT NULL, contributor_mode TEXT NOT NULL, existing_category TEXT, media_kind TEXT NOT NULL, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, captured_at TEXT, sha256 TEXT NOT NULL, analysis_error TEXT, PRIMARY KEY (job_id, id), FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS category_aliases (job_id TEXT NOT NULL, source_name TEXT NOT NULL, canonical_name TEXT NOT NULL, PRIMARY KEY (job_id, source_name), FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS features (job_id TEXT NOT NULL, media_id TEXT NOT NULL, dimension INTEGER NOT NULL, vector BLOB NOT NULL, dispersion REAL NOT NULL DEFAULT 0, preview_paths_json TEXT NOT NULL, ocr_text_json TEXT NOT NULL, PRIMARY KEY (job_id, media_id), FOREIGN KEY (job_id, media_id) REFERENCES media(job_id, id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS decisions (job_id TEXT NOT NULL, media_id TEXT NOT NULL, category TEXT NOT NULL, source TEXT NOT NULL, confidence_label TEXT NOT NULL, score REAL, alternative_category TEXT, PRIMARY KEY (job_id, media_id), FOREIGN KEY (job_id, media_id) REFERENCES media(job_id, id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS copy_entries (job_id TEXT NOT NULL, media_id TEXT NOT NULL, target_path TEXT NOT NULL, category TEXT NOT NULL, media_kind TEXT NOT NULL, contributor TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, status TEXT NOT NULL, duplicate_of TEXT, error_summary TEXT, PRIMARY KEY (job_id, media_id), FOREIGN KEY (job_id, media_id) REFERENCES media(job_id, id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS processing_errors (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, media_id TEXT, stage TEXT NOT NULL, source_path TEXT NOT NULL, summary TEXT NOT NULL, retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)), FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE);
"""


class JobStore:
    def __init__(self, path: Path) -> None:
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.execute("PRAGMA foreign_keys=ON")
        with self._connection:
            self._connection.executescript(_SCHEMA)
            row = self._connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                self._connection.execute("INSERT INTO schema_version(version) VALUES (1)")
            elif row[0] != 1:
                raise RuntimeError(f"Unsupported state database schema version: {row[0]}")

    def create_job(self, job: JobRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?)", (job.id, str(job.source_root), str(job.output_parent), str(job.output_root), job.phase.value, job.created_at.isoformat()))

    def get_job(self, job_id: str) -> JobRecord:
        with self._lock:
            row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return JobRecord(row[0], Path(row[1]), Path(row[2]), Path(row[3]), JobPhase(row[4]), datetime.fromisoformat(row[5]))

    def get_single_job(self) -> JobRecord:
        with self._lock:
            rows = self._connection.execute("SELECT id FROM jobs").fetchall()
            if len(rows) != 1:
                raise ValueError(f"Expected exactly one job, found {len(rows)}")
            return self.get_job(rows[0][0])

    def transition(self, job_id: str, next_phase: JobPhase) -> None:
        with self._lock, self._connection:
            current = self.get_job(job_id)
            if current.phase is next_phase:
                return
            if next_phase not in _PHASE_ORDER or _PHASE_ORDER.index(next_phase) != _PHASE_ORDER.index(current.phase) + 1:
                raise ValueError(f"Invalid transition {current.phase.name} -> {next_phase.name}")
            self._connection.execute("UPDATE jobs SET phase=? WHERE id=?", (next_phase.value, job_id))

    def replace_media(self, job_id: str, records: Sequence[MediaRecord]) -> None:
        with self._lock, self._connection:
            if any(record.job_id != job_id for record in records):
                raise ValueError(f"Media record job_id does not match {job_id}")
            self._connection.execute("DELETE FROM media WHERE job_id=?", (job_id,))
            self._connection.executemany("INSERT INTO media VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(r.job_id, r.id, str(r.source_path), r.contributor, r.contributor_mode.value, r.existing_category, r.media_kind.value, r.size_bytes, r.mtime_ns, r.captured_at.isoformat() if r.captured_at else None, r.sha256, r.analysis_error) for r in records])

    def list_media(self, job_id: str) -> list[MediaRecord]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM media WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
            return [MediaRecord(r[1], r[0], Path(r[2]), r[3], ContributorMode(r[4]), r[5], MediaKind(r[6]), r[7], r[8], datetime.fromisoformat(r[9]) if r[9] else None, r[10], r[11]) for r in rows]

    def save_alias(self, job_id: str, source_name: str, canonical_name: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("INSERT OR REPLACE INTO category_aliases VALUES (?, ?, ?)", (job_id, source_name, canonical_name))

    def save_aliases(self, job_id: str, aliases: Mapping[str, str]) -> None:
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO category_aliases VALUES (?, ?, ?)",
                [(job_id, source_name, canonical_name) for source_name, canonical_name in aliases.items()],
            )

    def list_aliases(self, job_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._connection.execute("SELECT source_name, canonical_name FROM category_aliases WHERE job_id=?", (job_id,)).fetchall())

    def save_decision(self, job_id: str, decision: ClassificationDecision) -> None:
        with self._lock, self._connection:
            self._connection.execute("INSERT OR REPLACE INTO decisions VALUES (?, ?, ?, ?, ?, ?, ?)", (job_id, decision.media_id, decision.category, decision.source.value, decision.confidence_label, decision.score, decision.alternative_category))

    def list_decisions(self, job_id: str) -> dict[str, ClassificationDecision]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM decisions WHERE job_id=?", (job_id,)).fetchall()
            return {r[1]: ClassificationDecision(r[1], r[2], DecisionSource(r[3]), r[4], r[5], r[6]) for r in rows}

    def close(self) -> None:
        self._connection.close()
