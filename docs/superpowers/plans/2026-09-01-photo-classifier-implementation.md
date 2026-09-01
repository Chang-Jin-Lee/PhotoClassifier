# PhotoClassifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 세 명의 게임스컴 사진·영상을 로컬에서 분석하여 영상 편집자가 바로 사용할 수 있는 주제/사진·동영상 폴더 구조로 안전하게 복사하는 Windows용 브라우저 애플리케이션을 만든다.

**Architecture:** Python 코어가 스캔, 폴더명 정규화, 미디어 특징 추출, 분류, 복사 계획, 해시 검증을 담당하고 SQLite가 재개 가능한 작업 상태를 저장한다. FastAPI는 127.0.0.1에만 바인딩되어 정적 웹 UI와 JSON API를 제공하며, OpenCLIP과 FFmpeg는 교체 가능한 어댑터 뒤에서 실행한다.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, SQLite, Pillow, NumPy, PyTorch, OpenCLIP ViT-B-32, FFmpeg/ffprobe 9.x, 선택적 EasyOCR, vanilla HTML/CSS/JavaScript, pytest

**Spec:** docs/superpowers/specs/2026-09-01-photo-classifier-design.md

## Global Constraints

- Windows에서 Python 3.13로 실행한다. 현재 확인된 인터프리터는 Python 3.13.15다.
- 영상 처리는 PATH에서 발견되는 FFmpeg와 ffprobe를 사용한다. 현재 확인된 버전은 9.0이다.
- 첫 버전의 지원 입력 형식은 대소문자를 구분하지 않는 .jpg, .jpeg, .mp4다.
- 입력 폴더와 그 안의 모든 파일은 읽기 전용으로 취급한다.
- 결과는 입력 폴더 밖의 새 편집자전달용_YYYYMMDD_HHMMSS 폴더에만 기록한다.
- 결과 구조는 대표주제명/사진과 대표주제명/동영상이다.
- 원본 이름과 수정 시각을 유지하고, 같은 대상 폴더에서 이름이 충돌할 때만 출처자와 순번을 붙인다.
- SHA-256이 완전히 같은 파일만 중복으로 생략한다. 유사 사진과 다른 인코딩 영상은 모두 보존한다.
- 고신뢰도만 자동 분류하고 나머지는 사용자가 승인하거나 검토필요로 보낸다.
- 복사 후 모든 결과 파일의 SHA-256을 원본과 비교한다.
- 상태는 결과 폴더의 .photoclassifier/state.sqlite3에 파일 단위로 커밋한다.
- CSV는 Excel에서 바로 열 수 있는 UTF-8 BOM 형식으로 쓴다.
- 서버는 127.0.0.1에만 바인딩하며 미디어 내용을 외부 서비스로 전송하지 않는다.
- Google Drive API 업로드와 ZIP 생성은 구현하지 않는다.
- 입력 경로와 출처자 이름을 코드에 하드코딩하지 않는다.
- OpenCLIP 가중치와 선택적 OCR 가중치는 최초 설치 또는 최초 사용 시 내려받고 이후 로컬 캐시를 사용한다.

## Planned File Structure

~~~text
PhotoClassifier/
  pyproject.toml                    # 패키지, 실행 명령, 의존성, pytest 설정
  .gitignore                       # 가상환경, 캐시, 모델/작업 산출물 제외
  README.md                        # 설치, 실행, 편집자 전달 절차
  scripts/
    setup.ps1                      # Python 3.13 가상환경과 의존성 설치
    run.ps1                        # 로컬 웹 앱 실행
  src/photoclassifier/
    __init__.py                    # 패키지 버전
    __main__.py                    # python -m 진입점
    cli.py                         # serve, inspect 명령
    domain.py                      # 공용 enum/dataclass와 상태 전이
    store.py                       # SQLite 스키마와 저장소
    hashing.py                     # 취소 가능한 SHA-256
    scanner.py                     # 입력 구조와 지원 미디어 검색
    categories.py                  # 폴더명 정규화와 병합 후보
    media/
      __init__.py
      metadata.py                  # EXIF, ffprobe, 파일명 시각
      preview.py                   # 사진 미리보기와 영상 대표 프레임
    ml/
      __init__.py
      embedder.py                  # OpenCLIP 및 테스트용 임베더
      ocr.py                       # 선택적 OCR 어댑터
      classifier.py               # 참조 인덱스, 점수, 보정, 자동 분류 게이트
    workflow.py                    # 단계 전이와 사용자 결정 조정
    copyplan.py                    # 중복, 경로, 충돌, 용량 계획
    copier.py                      # 재개 가능한 복사와 해시 검증
    reports.py                     # CSV와 편집자 안내서
    web/
      __init__.py
      app.py                       # FastAPI 앱과 미디어 제공
      schemas.py                   # API 요청·응답 모델
      runner.py                    # 한 작업씩 실행하는 백그라운드 실행기
      templates/index.html         # 9단계 작업 화면
      static/app.js                # API 호출, 검토, 진행률
      static/styles.css            # 편집자 중심 반응형 화면
  tests/
    conftest.py                    # 임시 미디어와 공용 fixture
    test_store.py
    test_scanner.py
    test_categories.py
    media/test_metadata.py
    media/test_preview.py
    ml/test_embedder.py
    ml/test_classifier.py
    test_workflow.py
    test_copyplan.py
    test_copier.py
    test_reports.py
    web/test_api.py
    web/test_ui_contract.py
    integration/test_end_to_end.py
~~~

## Test Fixture Contract

tests/conftest.py는 다음 공용 helper를 실제 구현한다. write_oriented_jpeg는 Pillow Exif 객체의 orientation tag 274를 지정하며 make_mp4는 Task 4의 FFmpeg 명령을 subprocess.run(check=True)으로 호출한다.

~~~python
def write_jpeg(path: Path, color: str = "red", size: tuple[int, int] = (64, 48)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path, format="JPEG")
    return path


def write_oriented_jpeg(path: Path, orientation: int) -> Path: ...
def make_mp4(path: Path, duration_seconds: int = 3) -> Path: ...


@pytest.fixture
def source_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "수집"
    write_jpeg(root / "분류자" / "넥서스아니마" / "known.jpg", "red")
    write_jpeg(root / "미분류자" / "사진" / "unknown.jpg", "red")
    make_mp4(root / "미분류자" / "동영상" / "unknown.mp4")
    return root
~~~

각 테스트 모듈의 전용 helper는 모듈 안에 다음 서명으로 둔다.

~~~python
# tests/test_scanner.py
@pytest.fixture
def scanned_media(tmp_path: Path) -> list[MediaRecord]: ...

# tests/ml/test_classifier.py
def reference_index(values: Mapping[str, Sequence[Sequence[float]]]) -> ReferenceIndex: ...

# tests/test_workflow.py
@pytest.fixture
def workflow_dependencies(tmp_path: Path) -> WorkflowDependencies: ...
@pytest.fixture
def workflow(tmp_path: Path) -> WorkflowService: ...

# tests/test_copyplan.py
def media(media_id: str, path: Path, sha256: str, contributor: str) -> MediaRecord: ...
def decision(category: str) -> ClassificationDecision: ...
def decisions_for(records: Sequence[MediaRecord], category: str) -> dict[str, ClassificationDecision]: ...

# tests/test_copier.py
def one_file_plan(tmp_path: Path, content: bytes) -> tuple[CopyPlan, JobStore]: ...

# tests/test_reports.py
def report_fixture(tmp_path: Path) -> ReportInput: ...

# tests/web/test_api.py
def wait_for_phase(client: TestClient, job_id: str, phase: str) -> None: ...
@pytest.fixture
def registered_video_id(client: TestClient, source_fixture: Path) -> str: ...
@dataclass(frozen=True)
class CompletedJobFixture:
    id: str
    state_database: Path
    cache_root: Path
@pytest.fixture
def completed_job(client: TestClient, source_fixture: Path) -> CompletedJobFixture: ...

# tests/integration/test_end_to_end.py
@dataclass(frozen=True)
class EndToEndResult:
    output_root: Path
    summary: CopySummary
    input_count: int
class EndToEndFixture:
    def run(self) -> EndToEndResult: ...
@pytest.fixture
def e2e_fixture(tmp_path: Path) -> EndToEndFixture: ...
~~~

workflow와 e2e_fixture는 실제 모델 다운로드를 하지 않는다. FakeEmbedder, 고정 OCR 결과, 임시 JPG/MP4를 WorkflowDependencies에 주입한다. 실제 OpenCLIP과 실제 게임스컴 폴더는 Task 13의 수동 검증에서만 사용한다.

---

### Task 1: 프로젝트 골격, 도메인 모델, SQLite 상태 저장소

**Files:**
- Create: pyproject.toml
- Create: .gitignore
- Create: src/photoclassifier/__init__.py
- Create: src/photoclassifier/domain.py
- Create: src/photoclassifier/store.py
- Create: tests/test_store.py

**Interfaces:**
- Consumes: 없음
- Produces: JobPhase, ContributorMode, MediaKind, DecisionSource, CopyStatus, JobRecord, MediaRecord, ClassificationDecision, ProcessingError, JobStore

- [ ] **Step 1: 저장소 왕복과 상태 전이 실패 테스트 작성**

~~~python
# tests/test_store.py
from datetime import UTC, datetime
from pathlib import Path

import pytest

from photoclassifier.domain import JobPhase, JobRecord
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
~~~

- [ ] **Step 2: 테스트가 import 오류로 실패하는지 확인**

Run: python -m pytest tests/test_store.py -v

Expected: FAIL with ModuleNotFoundError: No module named 'photoclassifier'

- [ ] **Step 3: 패키지 설정과 공용 타입 작성**

pyproject.toml에 다음 의존성과 실행점을 넣는다.

~~~toml
[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "photoclassifier"
version = "0.1.0"
requires-python = ">=3.13,<3.14"
dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn>=0.34,<1",
  "jinja2>=3.1,<4",
  "python-multipart>=0.0.20,<1",
  "pillow>=11,<13",
  "numpy>=2,<3",
  "torch>=2.7,<3",
  "torchvision>=0.22,<1",
  "open-clip-torch>=2.32,<4",
]

[project.optional-dependencies]
ocr = ["easyocr>=1.7,<2"]
dev = ["pytest>=8,<9", "pytest-cov>=6,<8", "httpx>=0.28,<1"]

[project.scripts]
photoclassifier = "photoclassifier.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/photoclassifier"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
addopts = "-ra"
~~~

.gitignore에는 다음 로컬 산출물을 제외한다.

~~~gitignore
.venv/
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.photoclassifier/
편집자전달용_*/
~~~

domain.py에 다음 값과 불변 dataclass를 정의한다.

~~~python
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
    def new(
        cls,
        job_id: str,
        source_root: Path,
        output_parent: Path,
        *,
        now: datetime | None = None,
    ) -> "JobRecord":
        created_at = now or datetime.now(UTC)
        output_root = output_parent / f"편집자전달용_{created_at:%Y%m%d_%H%M%S}"
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
~~~

- [ ] **Step 4: SQLite 스키마와 JobStore 최소 구현**

JobStore는 sqlite3.connect(..., check_same_thread=False), threading.RLock, PRAGMA foreign_keys=ON을 사용한다. 초기화 시 아래 스키마를 한 트랜잭션에서 만든다.

~~~sql
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source_root TEXT NOT NULL,
    output_parent TEXT NOT NULL,
    output_root TEXT NOT NULL,
    phase TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
    job_id TEXT NOT NULL,
    id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    contributor TEXT NOT NULL,
    contributor_mode TEXT NOT NULL,
    existing_category TEXT,
    media_kind TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    captured_at TEXT,
    sha256 TEXT NOT NULL,
    analysis_error TEXT,
    PRIMARY KEY (job_id, id),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS category_aliases (
    job_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    PRIMARY KEY (job_id, source_name),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS features (
    job_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    dimension INTEGER NOT NULL,
    vector BLOB NOT NULL,
    dispersion REAL NOT NULL DEFAULT 0,
    preview_paths_json TEXT NOT NULL,
    ocr_text_json TEXT NOT NULL,
    PRIMARY KEY (job_id, media_id),
    FOREIGN KEY (job_id, media_id) REFERENCES media(job_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS decisions (
    job_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence_label TEXT NOT NULL,
    score REAL,
    alternative_category TEXT,
    PRIMARY KEY (job_id, media_id),
    FOREIGN KEY (job_id, media_id) REFERENCES media(job_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS copy_entries (
    job_id TEXT NOT NULL,
    media_id TEXT NOT NULL,
    target_path TEXT NOT NULL,
    category TEXT NOT NULL,
    media_kind TEXT NOT NULL,
    contributor TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    duplicate_of TEXT,
    error_summary TEXT,
    PRIMARY KEY (job_id, media_id),
    FOREIGN KEY (job_id, media_id) REFERENCES media(job_id, id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS processing_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    media_id TEXT,
    stage TEXT NOT NULL,
    source_path TEXT NOT NULL,
    summary TEXT NOT NULL,
    retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)),
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);
~~~

schema_version에 행이 없으면 1을 기록하고, 1이 아닌 값이면 지원하지 않는 상태 DB라는 명확한 오류로 연다. 공개 메서드는 아래 서명을 정확히 사용한다.

~~~python
class JobStore:
    def __init__(self, path: Path) -> None: ...
    def create_job(self, job: JobRecord) -> None: ...
    def get_job(self, job_id: str) -> JobRecord: ...
    def get_single_job(self) -> JobRecord: ...
    def transition(self, job_id: str, next_phase: JobPhase) -> None: ...
    def replace_media(self, job_id: str, records: Sequence[MediaRecord]) -> None: ...
    def list_media(self, job_id: str) -> list[MediaRecord]: ...
    def save_alias(self, job_id: str, source_name: str, canonical_name: str) -> None: ...
    def list_aliases(self, job_id: str) -> dict[str, str]: ...
    def save_decision(self, job_id: str, decision: ClassificationDecision) -> None: ...
    def list_decisions(self, job_id: str) -> dict[str, ClassificationDecision]: ...
    def close(self) -> None: ...
~~~

상태 전이는 CREATED→SCANNED→MERGES_REVIEWED→ANALYZING→CLASSIFICATION_REVIEW→PLAN_CONFIRMED→COPYING→VERIFIED만 허용한다. 같은 상태로의 전이는 재시도용 no-op으로 허용한다.

- [ ] **Step 5: 저장소 테스트 전체 통과 확인**

Run: python -m pytest tests/test_store.py -v

Expected: 2 passed

- [ ] **Step 6: 프로젝트 골격 커밋**

~~~powershell
git add pyproject.toml .gitignore src/photoclassifier tests/test_store.py
git commit -m "feat: add job domain and persistent state store"
~~~

### Task 2: 입력 스캔, 촬영 시각, SHA-256

**Files:**
- Create: src/photoclassifier/hashing.py
- Create: src/photoclassifier/media/__init__.py
- Create: src/photoclassifier/media/metadata.py
- Create: src/photoclassifier/scanner.py
- Create: tests/conftest.py
- Create: tests/media/test_metadata.py
- Create: tests/test_scanner.py
- Modify: src/photoclassifier/store.py

**Interfaces:**
- Consumes: MediaRecord, ContributorMode, MediaKind, JobStore.replace_media
- Produces: sha256_file(path, cancel_check), read_capture_time(path, kind, ffprobe_runner), scan_source(job, mode_overrides)

- [ ] **Step 1: 파일명 촬영 시각과 구조 추정 실패 테스트 작성**

~~~python
def test_scan_infers_classified_and_unclassified_contributors(tmp_path: Path) -> None:
    source = tmp_path / "수집"
    write_jpeg(source / "서주영" / "사진" / "20260826_084948.jpg")
    write_jpeg(source / "이상민" / "넥서스아니마" / "20260826_085521.jpg")

    result = scan_source(JobRecord.new("job-1", source, tmp_path / "out"), {})

    by_person = {item.contributor: item for item in result.contributors}
    assert by_person["서주영"].mode is ContributorMode.UNCLASSIFIED
    assert by_person["이상민"].mode is ContributorMode.CLASSIFIED
    assert result.media[0].captured_at.year == 2026
    assert {item.existing_category for item in result.media} == {None, "넥서스아니마"}


def test_scan_ignores_unsupported_files(tmp_path: Path) -> None:
    source = tmp_path / "수집"
    (source / "서주영" / "사진").mkdir(parents=True)
    (source / "서주영" / "사진" / "메모.txt").write_text("x", encoding="utf-8")

    result = scan_source(JobRecord.new("job-1", source, tmp_path / "out"), {})

    assert result.media == []
    assert result.ignored_count == 1
~~~

- [ ] **Step 2: 스캔 테스트 실패 확인**

Run: python -m pytest tests/test_scanner.py tests/media/test_metadata.py -v

Expected: FAIL because scan_source and read_capture_time do not exist

- [ ] **Step 3: 메타데이터와 해시 구현**

hashing.py는 8MiB 블록으로 읽고 매 블록 전에 cancel_check()를 호출한다.

~~~python
def sha256_file(path: Path, cancel_check: Callable[[], bool] = lambda: False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            if cancel_check():
                raise CancelledError(str(path))
            digest.update(block)
    return digest.hexdigest()
~~~

metadata.py는 사진에서 EXIF DateTimeOriginal을 먼저 읽고, 영상은 다음 형식의 ffprobe JSON을 파싱한다. 메타데이터가 없으면 YYYYMMDD_HHMMSS 또는 YYYYMMDD-HHMMSS 파일명 패턴을 사용하고, 모든 시각은 timezone 정보가 없으면 로컬 시각으로 유지한다.

~~~powershell
ffprobe -v error -print_format json -show_format -show_streams -- "input.mp4"
~~~

ffprobe 호출은 shell=False인 subprocess.run(list[str], capture_output=True, text=True, encoding="utf-8", errors="replace")로 제한한다.

- [ ] **Step 4: 스캐너 구현**

scanner.py의 공개 API는 다음과 같다.

~~~python
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
) -> ScanResult: ...
~~~

최상위 하위 폴더를 출처자로 본다. 그 아래의 비어 있지 않은 폴더명이 사진·동영상뿐이면 미분류, 그 외 주제 폴더가 하나라도 있으면 분류됨으로 추정한다. mode_overrides가 있으면 추정보다 우선한다. 지원 파일은 정렬된 절대 경로 순서로 처리하고 UUIDv5(source_path.as_uri())를 안정 ID로 사용한다. 지원하지 않는 파일은 ignored_files에 보존하여 WorkflowService가 processing_errors에 stage=scan, retryable=false로 기록하게 한다.

- [ ] **Step 5: 스캔 결과를 SQLite에 저장하는 테스트와 구현 추가**

~~~python
def test_store_replaces_media_atomically(tmp_path: Path, scanned_media: list[MediaRecord]) -> None:
    store = JobStore(tmp_path / "state.sqlite3")
    store.create_job(JobRecord.new("job-1", tmp_path / "수집", tmp_path / "out"))

    store.replace_media("job-1", scanned_media)
    store.replace_media("job-1", scanned_media[:1])

    assert store.list_media("job-1") == scanned_media[:1]
~~~

Run: python -m pytest tests/test_store.py tests/test_scanner.py tests/media/test_metadata.py -v

Expected: all passed

- [ ] **Step 6: 스캔 기능 커밋**

~~~powershell
git add src/photoclassifier tests
git commit -m "feat: scan contributor media and capture metadata"
~~~

### Task 3: 폴더명 정규화와 안전한 병합 후보

**Files:**
- Create: src/photoclassifier/categories.py
- Create: tests/test_categories.py
- Modify: src/photoclassifier/store.py

**Interfaces:**
- Consumes: MediaRecord.existing_category, JobStore.save_alias
- Produces: normalized_key, select_canonical_name, build_merge_candidates, apply_aliases, MergeCandidate, CanonicalAssignment

- [ ] **Step 1: 자동 통합과 의미 후보 경계 테스트 작성**

~~~python
def test_exact_normalization_is_auto_merge() -> None:
    result = build_merge_candidates(["넥서스아니마", " 넥서스아니마 ", "NEXUS-ANIMA", "NEXUS_ANIMA"])
    groups = [set(item.names) for item in result if item.kind is MergeKind.AUTO]
    assert {"NEXUS-ANIMA", "NEXUS_ANIMA"} in groups
    assert {"넥서스아니마", " 넥서스아니마 "} in groups


def test_related_but_distinct_names_require_review() -> None:
    result = build_merge_candidates(["KOCCA 한국 공동관", "한국공동관인터뷰"])
    candidate = next(item for item in result if set(item.names) == {"KOCCA 한국 공동관", "한국공동관인터뷰"})
    assert candidate.kind is MergeKind.REVIEW


def test_aliases_are_applied_without_changing_source_record(media_record: MediaRecord) -> None:
    mapped = apply_aliases([media_record], {"실버 팰리스": "실버팰리스"})
    assert mapped[0].category == "실버팰리스"
    assert media_record.existing_category == "실버 팰리스"
~~~

- [ ] **Step 2: 테스트 실패 확인**

Run: python -m pytest tests/test_categories.py -v

Expected: FAIL because categories module does not exist

- [ ] **Step 3: 결정적인 이름 정규화 구현**

~~~python
def normalized_key(value: str) -> str:
    value = unicodedata.normalize("NFC", value).strip().casefold()
    value = re.sub(r"[_\-\s]+", " ", value)
    return value.rstrip(" ._-")


def select_canonical_name(names: Sequence[str]) -> str:
    counts = Counter(name.strip() for name in names)
    return min(
        counts,
        key=lambda name: (-counts[name], name.count("_") + name.count("-"), len(name), name.casefold()),
    )
~~~

apply_aliases는 원본 MediaRecord를 변경하지 않고 다음 값을 반환한다.

~~~python
@dataclass(frozen=True, slots=True)
class CanonicalAssignment:
    media_id: str
    category: str
~~~

MergeKind는 AUTO와 REVIEW를 갖는다. normalized_key가 같은 이름만 AUTO다. REVIEW 후보는 공백 토큰 Jaccard가 0.5 이상, difflib.SequenceMatcher 비율이 0.72 이상, 또는 공백을 뺀 두 키의 최장 공통 부분문자열이 4글자 이상인 서로 다른 정규화 키다. 마지막 규칙으로 KOCCA 한국 공동관과 한국공동관인터뷰를 검토 후보로 잡되 REVIEW는 절대 별칭으로 자동 저장하지 않는다.

- [ ] **Step 4: 병합 승인 저장과 재로딩 구현**

JobStore에 save_aliases(job_id, aliases: Mapping[str, str])를 트랜잭션으로 추가한다. 같은 source_name을 다시 승인하면 canonical_name을 갱신한다.

Run: python -m pytest tests/test_categories.py tests/test_store.py -v

Expected: all passed

- [ ] **Step 5: 폴더 통합 커밋**

~~~powershell
git add src/photoclassifier/categories.py src/photoclassifier/store.py tests
git commit -m "feat: normalize and review category merges"
~~~

### Task 4: 사진 미리보기와 영상 대표 프레임

**Files:**
- Create: src/photoclassifier/media/preview.py
- Create: tests/media/test_preview.py
- Modify: tests/conftest.py

**Interfaces:**
- Consumes: MediaRecord, ffmpeg executable
- Produces: sample_timestamps, create_photo_preview, extract_video_frames, AnalysisAssets

- [ ] **Step 1: 프레임 시간과 저품질 필터 테스트 작성**

~~~python
def test_sample_timestamps_avoids_only_using_edges() -> None:
    points = sample_timestamps(120.0)
    assert 3 <= len(points) <= 12
    assert points[0] > 0
    assert points[-1] < 120.0
    assert points == sorted(points)


def test_black_frame_is_rejected() -> None:
    black = Image.new("RGB", (320, 180), "black")
    assert frame_quality(black).usable is False


def test_photo_preview_applies_exif_orientation(tmp_path: Path) -> None:
    source = write_oriented_jpeg(tmp_path / "rotated.jpg", orientation=6)
    target = tmp_path / "preview.jpg"
    create_photo_preview(source, target, max_edge=1024)
    with Image.open(target) as image:
        assert image.height > image.width
~~~

- [ ] **Step 2: 미리보기 테스트 실패 확인**

Run: python -m pytest tests/media/test_preview.py -v

Expected: FAIL because preview functions do not exist

- [ ] **Step 3: 사진 미리보기와 프레임 품질 구현**

사진은 ImageOps.exif_transpose, thumbnail((max_edge, max_edge)), RGB 변환, JPEG quality=88로 캐시한다. frame_quality는 grayscale 평균이 5 미만 또는 250 초과면 unusable, grayscale 표준편차가 3 미만이면 unusable로 판정한다.

~~~python
@dataclass(frozen=True, slots=True)
class FrameQuality:
    usable: bool
    brightness: float
    contrast: float


@dataclass(frozen=True, slots=True)
class AnalysisAssets:
    preview_path: Path
    frame_paths: tuple[Path, ...]
    duration_seconds: float | None
    warnings: tuple[str, ...] = ()
~~~

- [ ] **Step 4: ffprobe 길이와 FFmpeg 프레임 추출 구현**

영상 길이는 ffprobe JSON의 format.duration을 우선하고 없으면 video stream duration을 사용한다. 30초마다 한 장을 목표로 하되 3~12장 범위에서 5%~95% 지점을 균등 선택한다. WorkflowService는 preview와 frame을 output_root/.photoclassifier/cache/media_id 아래에 생성한다. 각 프레임은 다음 인수 배열로 추출하며 shell을 사용하지 않는다.

~~~python
[
    "ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{second:.3f}",
    "-i", str(source), "-frames:v", "1", "-vf",
    "scale='min(1280,iw)':-2", "-q:v", "3", "-y", str(target),
]
~~~

모든 프레임이 저품질이면 중간 시각 프레임 한 장을 보존하고 analysis_error에 경고를 기록한다.

- [ ] **Step 5: 실제 FFmpeg가 만든 짧은 MP4로 통합 테스트**

tests/conftest.py의 make_mp4는 다음 명령으로 3초 테스트 영상을 만든다.

~~~powershell
ffmpeg -f lavfi -i testsrc2=size=320x180:rate=10 -t 3 -pix_fmt yuv420p -y sample.mp4
~~~

Run: python -m pytest tests/media -v

Expected: all passed and extracted frame count is between 3 and 12

- [ ] **Step 6: 미디어 준비 기능 커밋**

~~~powershell
git add src/photoclassifier/media tests/media tests/conftest.py
git commit -m "feat: prepare photo previews and video frames"
~~~

### Task 5: 로컬 OpenCLIP 특징과 선택적 OCR 어댑터

**Files:**
- Create: src/photoclassifier/ml/__init__.py
- Create: src/photoclassifier/ml/embedder.py
- Create: src/photoclassifier/ml/ocr.py
- Create: tests/ml/test_embedder.py
- Modify: src/photoclassifier/store.py

**Interfaces:**
- Consumes: AnalysisAssets.frame_paths, Pillow images
- Produces: ImageEmbedder protocol, OpenClipEmbedder, FakeEmbedder, OcrProvider protocol, NullOcrProvider, EasyOcrProvider, aggregate_media_features, frame_dispersion

- [ ] **Step 1: 정규화된 특징과 영상 집계 실패 테스트 작성**

~~~python
def test_fake_embedder_returns_unit_vectors() -> None:
    embedder = FakeEmbedder({"a.jpg": np.array([3.0, 4.0], dtype=np.float32)})
    result = embedder.encode_images([Path("a.jpg")])
    np.testing.assert_allclose(result[0], np.array([0.6, 0.8], dtype=np.float32))


def test_video_feature_is_mean_of_usable_frames() -> None:
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    result = aggregate_media_features(vectors)
    np.testing.assert_allclose(result, np.array([2**-0.5, 2**-0.5]), atol=1e-6)


def test_unrelated_video_frames_have_high_dispersion() -> None:
    vectors = np.array([[1.0, 0.0], [-1.0, 0.0]], dtype=np.float32)
    assert frame_dispersion(vectors) > 0.25
~~~

- [ ] **Step 2: 임베더 테스트 실패 확인**

Run: python -m pytest tests/ml/test_embedder.py -v

Expected: FAIL because embedder module does not exist

- [ ] **Step 3: 임베더 프로토콜과 OpenCLIP 구현**

~~~python
class ImageEmbedder(Protocol):
    dimension: int
    def encode_images(self, paths: Sequence[Path]) -> np.ndarray: ...
    def encode_texts(self, texts: Sequence[str]) -> np.ndarray: ...


class OpenClipEmbedder:
    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        device: str | None = None,
    ) -> None: ...
~~~

모델은 첫 encode 호출 때 지연 로드한다. device가 없으면 torch.cuda.is_available()일 때 cuda, 아니면 cpu를 쓴다. model.eval(), torch.inference_mode()를 사용하며 결과를 float32 NumPy 단위 벡터로 반환한다. 한 배치가 메모리 부족이면 배치 크기를 절반으로 줄여 재시도하고 최종적으로 1장에서도 실패하면 해당 미디어만 오류 처리한다.

aggregate_media_features는 프레임 단위 벡터의 산술 평균을 다시 단위 벡터로 정규화한다. frame_dispersion은 각 프레임과 집계 벡터 사이 cosine distance의 평균이며 프레임이 한 장이면 0.0이다.

- [ ] **Step 4: OCR 프로토콜과 안전한 폴백 구현**

~~~python
class OcrProvider(Protocol):
    def read(self, image_path: Path) -> tuple[str, ...]: ...


class NullOcrProvider:
    def read(self, image_path: Path) -> tuple[str, ...]:
        return ()
~~~

EasyOcrProvider는 importlib로 easyocr을 지연 import하고 languages=("ko", "en"), gpu=torch.cuda.is_available()로 reader를 한 번만 만든다. 패키지나 가중치가 없으면 앱 전체를 실패시키지 않고 NullOcrProvider로 전환하며 UI 상태에 OCR 비활성 이유를 노출한다.

- [ ] **Step 5: 특징 BLOB 저장 구현**

JobStore에 save_feature(job_id, media_id, vector, dispersion, preview_paths, ocr_text)와 load_features(job_id)를 추가한다. 벡터는 float32 little-endian bytes와 dimension을 함께 저장하고 읽을 때 shape을 검증한다.

Run: python -m pytest tests/ml/test_embedder.py tests/test_store.py -v

Expected: all passed without downloading a real model

- [ ] **Step 6: 로컬 특징 추출 커밋**

~~~powershell
git add src/photoclassifier/ml src/photoclassifier/store.py tests/ml tests/test_store.py
git commit -m "feat: extract and persist local media features"
~~~

### Task 6: 참조 인덱스, 보정, 신뢰도 분류

**Files:**
- Create: src/photoclassifier/ml/classifier.py
- Create: tests/ml/test_classifier.py

**Interfaces:**
- Consumes: MediaRecord, ClassificationDecision, ImageEmbedder vectors, frame dispersion, canonical aliases
- Produces: CandidateScore, ClassificationResult, Thresholds, calibrate_thresholds, build_reference_index, build_text_scores, build_temporal_scores, classify_feature

- [ ] **Step 1: 고신뢰도 게이트와 새 주제 보호 테스트 작성**

~~~python
def test_high_confidence_requires_score_and_margin() -> None:
    index = reference_index({"넥서스아니마": [[1.0, 0.0]], "실버팰리스": [[0.0, 1.0]]})
    result = classify_feature(
        np.array([0.99, 0.01], dtype=np.float32),
        index,
        Thresholds(min_score=0.80, min_margin=0.08),
        frame_dispersion=0.0,
        text_scores={},
        temporal_scores={},
    )
    assert result.auto_category == "넥서스아니마"
    assert result.confidence_label == "high"


def test_close_candidates_are_sent_to_review() -> None:
    index = reference_index({"A": [[1.0, 0.0]], "B": [[0.99, 0.01]]})
    result = classify_feature(
        np.array([1.0, 0.0], dtype=np.float32),
        index,
        Thresholds(min_score=0.80, min_margin=0.08),
        frame_dispersion=0.0,
        text_scores={},
        temporal_scores={},
    )
    assert result.auto_category is None
    assert result.review_reason == "small_margin"


def test_no_close_reference_never_forces_existing_category() -> None:
    index = reference_index({"A": [[1.0, 0.0]], "B": [[0.0, 1.0]]})
    result = classify_feature(
        np.array([-1.0, 0.0], dtype=np.float32),
        index,
        Thresholds(min_score=0.80, min_margin=0.08),
        frame_dispersion=0.0,
        text_scores={},
        temporal_scores={},
    )
    assert result.auto_category is None
    assert result.review_reason == "low_score"


def test_mixed_video_is_reviewed_even_with_strong_mean_match() -> None:
    index = reference_index({"A": [[1.0, 0.0]], "B": [[0.0, 1.0]]})
    result = classify_feature(
        np.array([1.0, 0.0], dtype=np.float32),
        index,
        Thresholds(min_score=0.80, min_margin=0.08),
        frame_dispersion=0.30,
        text_scores={},
        temporal_scores={},
    )
    assert result.auto_category is None
    assert result.review_reason == "mixed_video"
~~~

- [ ] **Step 2: 분류기 테스트 실패 확인**

Run: python -m pytest tests/ml/test_classifier.py -v

Expected: FAIL because classifier module does not exist

- [ ] **Step 3: 참조 인덱스와 결합 점수 구현**

~~~python
@dataclass(frozen=True, slots=True)
class Thresholds:
    min_score: float = 0.80
    min_margin: float = 0.08


@dataclass(frozen=True, slots=True)
class CandidateScore:
    category: str
    score: float
    visual_neighbor: float
    visual_centroid: float
    text_score: float | None
    temporal_score: float | None


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    candidates: tuple[CandidateScore, ...]
    auto_category: str | None
    confidence_label: str
    review_reason: str | None


@dataclass(frozen=True, slots=True)
class ReferenceIndex:
    vectors_by_category: Mapping[str, np.ndarray]
    centroids_by_category: Mapping[str, np.ndarray]


def classify_feature(
    feature: np.ndarray,
    index: ReferenceIndex,
    thresholds: Thresholds,
    *,
    frame_dispersion: float,
    text_scores: Mapping[str, float],
    temporal_scores: Mapping[str, float],
) -> ClassificationResult: ...
~~~

기본 가중치는 최근접 시각 0.45, 중심 시각 0.35, 시간 0.15, OCR/주제 텍스트 0.05다. 선택 신호가 없으면 남은 가중치 합으로 재정규화한다. 시각 cosine은 (-1, 1)에서 (0, 1)로 변환한다. 후보는 점수 내림차순, 동점이면 Unicode 정렬한다. 영상 프레임의 평균 cosine distance인 frame_dispersion이 0.25를 넘으면 점수와 무관하게 auto_category=None, review_reason=mixed_video로 처리한다.

build_text_scores는 OCR 각 줄을 normalized_key로 바꾸고 카테고리명이 OCR 문자열에 포함되면 1.0, 토큰 Jaccard가 있으면 그 비율, 둘 다 없으면 0.0을 반환한다. build_temporal_scores는 촬영 시각 전후 10분 안의 EXISTING·USER·AUTO 결정만 사용하고, 분 차이의 역수 1/(1+minutes)를 카테고리별로 합한 뒤 최댓값이 1.0이 되도록 정규화한다. 촬영 시각이 없거나 이웃이 없으면 빈 매핑을 반환한다.

- [ ] **Step 4: 기존 분류 자료 교차 검증과 문턱 보정 구현**

calibrate_thresholds는 카테고리마다 참조가 두 개 이상인 샘플에 leave-one-out을 적용한다. 관측된 score와 margin 후보를 탐색하여 정확도 0.95 이상인 조합 중 자동 처리 비율이 가장 큰 값을 선택한다. 검증 가능한 샘플이 10개 미만이거나 0.95 정확도 조합이 없으면 Thresholds(0.80, 0.08)를 반환하고 fallback_used=True를 기록한다.

~~~python
@dataclass(frozen=True, slots=True)
class CalibrationResult:
    thresholds: Thresholds
    evaluated_samples: int
    expected_precision: float | None
    expected_coverage: float | None
    fallback_used: bool
~~~

- [ ] **Step 5: 분류기 테스트 통과 확인**

Run: python -m pytest tests/ml/test_classifier.py -v

Expected: all passed, including deterministic tie ordering and calibration fallback

- [ ] **Step 6: 신뢰도 분류 커밋**

~~~powershell
git add src/photoclassifier/ml/classifier.py tests/ml/test_classifier.py
git commit -m "feat: classify media with calibrated confidence gates"
~~~

### Task 7: 작업 흐름과 검토 결정

**Files:**
- Create: src/photoclassifier/workflow.py
- Create: tests/test_workflow.py
- Modify: src/photoclassifier/store.py

**Interfaces:**
- Consumes: scan_source, category aliases, AnalysisAssets, ImageEmbedder, classifier, JobStore
- Produces: WorkflowDependencies, WorkflowService.create_new, open_existing, scan, confirm_merges, analyze, list_review_items, decide, defer, classification_summary

- [ ] **Step 1: 자동 결정·사용자 결정·보류 상태 테스트 작성**

~~~python
def test_analyze_persists_only_high_confidence_as_auto(workflow: WorkflowService) -> None:
    workflow.scan("job-1", {})
    workflow.confirm_merges("job-1", {})
    workflow.analyze("job-1")

    decisions = workflow.store.list_decisions("job-1")
    assert decisions["high"].source is DecisionSource.AUTO
    assert "ambiguous" not in decisions
    assert workflow.store.get_job("job-1").phase is JobPhase.CLASSIFICATION_REVIEW


def test_user_can_bulk_decide_and_defer(workflow: WorkflowService) -> None:
    workflow.decide("job-1", ["a", "b"], "닌텐도")
    workflow.defer("job-1", ["c"])

    decisions = workflow.store.list_decisions("job-1")
    assert decisions["a"].source is DecisionSource.USER
    assert decisions["b"].category == "닌텐도"
    assert decisions["c"].source is DecisionSource.DEFERRED
    assert decisions["c"].category == "검토필요"


def test_existing_output_workspace_reopens_after_restart(
    workflow_dependencies: WorkflowDependencies,
    source_fixture: Path,
    tmp_path: Path,
) -> None:
    created = WorkflowService.create_new(source_fixture, tmp_path / "out", workflow_dependencies)
    created.scan(created.job.id, {})
    reopened = WorkflowService.open_existing(created.job.output_root, workflow_dependencies)
    assert reopened.job.id == created.job.id
    assert reopened.job.phase is JobPhase.SCANNED
    assert reopened.job.output_root.joinpath(".photoclassifier", "state.sqlite3").is_file()
~~~

- [ ] **Step 2: 작업 흐름 테스트 실패 확인**

Run: python -m pytest tests/test_workflow.py -v

Expected: FAIL because WorkflowService does not exist

- [ ] **Step 3: 단계별 WorkflowService 구현**

~~~python
@dataclass(frozen=True, slots=True)
class WorkflowDependencies:
    ffprobe_runner: ProbeRunner
    embedder: ImageEmbedder
    ocr: OcrProvider
    free_bytes: Callable[[Path], int]


@dataclass(frozen=True, slots=True)
class ReviewItem:
    media_id: str
    media_kind: MediaKind
    contributor: str
    captured_at: datetime | None
    preview_path: Path | None
    candidates: tuple[CandidateScore, ...]
    analysis_error: str | None


@dataclass(frozen=True, slots=True)
class ClassificationSummary:
    total: int
    existing: int
    automatic: int
    needs_review: int
    failed_analysis: int


class WorkflowService:
    @classmethod
    def create_new(
        cls,
        source_root: Path,
        output_parent: Path,
        dependencies: WorkflowDependencies,
        *,
        now: datetime | None = None,
    ) -> "WorkflowService": ...
    @classmethod
    def open_existing(
        cls,
        output_root: Path,
        dependencies: WorkflowDependencies,
    ) -> "WorkflowService": ...
    @property
    def job(self) -> JobRecord: ...
    def scan(self, job_id: str, mode_overrides: Mapping[str, ContributorMode]) -> ScanResult: ...
    def confirm_merges(self, job_id: str, aliases: Mapping[str, str]) -> None: ...
    def analyze(self, job_id: str) -> ClassificationSummary: ...
    def list_review_items(self, job_id: str) -> list[ReviewItem]: ...
    def decide(self, job_id: str, media_ids: Sequence[str], category: str) -> None: ...
    def defer(self, job_id: str, media_ids: Sequence[str]) -> None: ...
    def classification_summary(self, job_id: str) -> ClassificationSummary: ...
~~~

create_new는 JobRecord.new가 만든 기본 결과 이름이 이미 있으면 _2, _3 순서로 빈 경로를 고른다. 선택한 output_root/.photoclassifier을 만들고 그 안의 state.sqlite3로 JobStore를 초기화한 뒤 JobRecord를 저장한다. open_existing은 지정한 결과 폴더의 state.sqlite3에서 get_single_job을 읽고 source_root가 존재하는지 확인한다. 이 두 경로만 상태 DB를 만들거나 연다.

분류된 기여자의 파일은 canonical alias를 적용한 EXISTING 결정으로 저장한다. 미분류 파일만 특징 분석한다. 고신뢰도는 AUTO로 저장하고, 나머지는 결정 없이 ReviewItem으로 노출한다. 미리보기·프레임 분석에 실패한 지원 파일도 오류 이유와 함께 ReviewItem으로 노출하여 재시도 또는 검토필요 복사를 선택하게 한다. 사용자가 새 이름을 입력하면 categories.normalized_key로 검증하고 Windows에서 쓸 수 없는 빈 이름은 거부한다.

- [ ] **Step 4: 입력 변경 시 분석 무효화 구현**

재스캔에서 같은 media_id의 size_bytes, mtime_ns 또는 sha256이 달라지면 해당 features, decisions, copy_entries를 한 트랜잭션에서 삭제한다. 변경되지 않은 특징과 사용자 결정은 재사용한다.

Run: python -m pytest tests/test_workflow.py tests/test_store.py -v

Expected: all passed

- [ ] **Step 5: 작업 흐름 커밋**

~~~powershell
git add src/photoclassifier/workflow.py src/photoclassifier/store.py tests
git commit -m "feat: orchestrate analysis and classification review"
~~~

### Task 8: 중복·충돌·용량을 포함한 복사 계획

**Files:**
- Create: src/photoclassifier/copyplan.py
- Create: tests/test_copyplan.py
- Modify: src/photoclassifier/domain.py
- Modify: src/photoclassifier/workflow.py

**Interfaces:**
- Consumes: MediaRecord, ClassificationDecision, aliases
- Produces: CopyEntry, CopyPlan, build_copy_plan, sanitize_segment, validate_output_location, WorkflowService.preview_plan, confirm_plan

- [ ] **Step 1: 중복과 파일명 충돌 실패 테스트 작성**

~~~python
def test_exact_duplicate_has_one_copy_and_one_duplicate_entry(tmp_path: Path) -> None:
    records = [
        media("a", tmp_path / "이상민" / "A" / "same.jpg", "hash-1", "이상민"),
        media("b", tmp_path / "이창진" / "A" / "same.jpg", "hash-1", "이창진"),
    ]
    plan = build_copy_plan(records, decisions_for(records, "A"), tmp_path / "result", free_bytes=10_000)
    assert [entry.status for entry in plan.entries].count(CopyStatus.PLANNED) == 1
    assert [entry.status for entry in plan.entries].count(CopyStatus.DUPLICATE) == 1


def test_same_name_different_hash_adds_contributor(tmp_path: Path) -> None:
    records = [
        media("a", tmp_path / "p1" / "A" / "same.jpg", "hash-1", "p1"),
        media("b", tmp_path / "p2" / "A" / "same.jpg", "hash-2", "p2"),
    ]
    plan = build_copy_plan(records, decisions_for(records, "A"), tmp_path / "result", free_bytes=10_000)
    assert {entry.target_path.name for entry in plan.entries} == {"same.jpg", "same_p2.jpg"}


def test_same_hash_with_different_categories_requires_review(tmp_path: Path) -> None:
    records = [
        media("a", tmp_path / "p1" / "A" / "one.jpg", "hash-1", "p1"),
        media("b", tmp_path / "p2" / "B" / "two.jpg", "hash-1", "p2"),
    ]
    with pytest.raises(ValueError, match="동일 파일의 주제 충돌"):
        build_copy_plan(records, {"a": decision("A"), "b": decision("B")}, tmp_path / "result", free_bytes=10_000)


def test_output_inside_source_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="입력 폴더 내부"):
        validate_output_location(tmp_path / "수집", tmp_path / "수집" / "결과")
~~~

- [ ] **Step 2: 복사 계획 테스트 실패 확인**

Run: python -m pytest tests/test_copyplan.py -v

Expected: FAIL because copyplan module does not exist

- [ ] **Step 3: Windows 안전 경로와 결과 이름 구현**

sanitize_segment는 < > : " / \ | ? * 및 제어문자를 _로 바꾸고 끝의 공백·점을 제거한다. CON, PRN, AUX, NUL, COM1~COM9, LPT1~LPT9는 이름 뒤에 _를 붙인다. 빈 결과는 검토필요로 바꾼다.

~~~python
@dataclass(frozen=True, slots=True)
class CopyEntry:
    media_id: str
    source_path: Path
    target_path: Path
    category: str
    media_kind: MediaKind
    contributor: str
    sha256: str
    size_bytes: int
    status: CopyStatus
    duplicate_of: str | None = None


@dataclass(frozen=True, slots=True)
class CopyPlan:
    job_id: str
    output_root: Path
    entries: tuple[CopyEntry, ...]
    required_bytes: int
    duplicate_count: int
    collision_count: int
~~~

- [ ] **Step 4: 결정적인 중복 대표와 충돌 이름 구현**

같은 SHA-256 그룹의 canonical category가 둘 이상이면 계획을 만들지 않고 동일 파일의 주제 충돌로 검토에 돌려보낸다. 주제가 같으면 media kind, source path 문자열 순으로 첫 파일을 대표로 삼는다. 동일 target name에 서로 다른 해시가 있으면 첫 파일은 원래 이름, 다음 파일은 _출처자, 그다음은 _출처자_2 순서로 지정한다. 모든 정렬은 casefold 후 원문 순서로 결정한다.

필요 공간은 PLANNED 항목 size_bytes 합계에 1%와 64MiB 중 큰 안전 여유를 더한다. shutil.disk_usage(output_root.parent).free가 부족하면 계획 확정을 막는다. 테스트에서는 free_bytes 인수로 실제 디스크 조회를 대체한다.

WorkflowService.preview_plan(job_id)는 저장된 결정으로 매번 결정적인 CopyPlan을 만들되 상태를 바꾸지 않는다. confirm_plan(job_id)은 미결정 파일이 없거나 사용자가 명시적으로 검토필요로 보낸 경우에만 copy_entries를 저장하고 phase를 PLAN_CONFIRMED로 바꾼다.

- [ ] **Step 5: 계획 테스트 통과 확인**

Run: python -m pytest tests/test_copyplan.py -v

Expected: all passed, including Windows reserved names and 검토필요 paths

- [ ] **Step 6: 복사 계획 커밋**

~~~powershell
git add src/photoclassifier/copyplan.py src/photoclassifier/domain.py src/photoclassifier/workflow.py tests/test_copyplan.py
git commit -m "feat: build safe deduplicated copy plans"
~~~

### Task 9: 재개 가능한 복사와 전수 해시 검증

**Files:**
- Create: src/photoclassifier/copier.py
- Create: tests/test_copier.py
- Modify: src/photoclassifier/store.py
- Modify: src/photoclassifier/workflow.py

**Interfaces:**
- Consumes: CopyPlan, CopyEntry, sha256_file, JobStore
- Produces: CancelToken, CopyProgress, CopySummary, CopyExecutor.execute, WorkflowService.execute_copy, cancel_copy

- [ ] **Step 1: 성공·중단·재개·손상 테스트 작성**

~~~python
def test_copy_verifies_hash_and_preserves_mtime(tmp_path: Path) -> None:
    plan, store = one_file_plan(tmp_path, content=b"media")
    summary = CopyExecutor(store).execute(plan, CancelToken())
    assert summary.verified == 1
    assert plan.entries[0].target_path.read_bytes() == b"media"
    assert plan.entries[0].target_path.stat().st_mtime_ns == plan.entries[0].source_path.stat().st_mtime_ns


def test_resume_skips_already_verified_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, store = one_file_plan(tmp_path, content=b"media")
    executor = CopyExecutor(store)
    executor.execute(plan, CancelToken())
    monkeypatch.setattr(shutil, "copyfileobj", Mock(side_effect=AssertionError("must not recopy")))
    summary = executor.execute(plan, CancelToken())
    assert summary.skipped_verified == 1


def test_hash_mismatch_removes_partial_and_records_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, store = one_file_plan(tmp_path, content=b"media")
    monkeypatch.setattr("photoclassifier.copier.sha256_file", lambda path, cancel_check=lambda: False: "wrong")
    summary = CopyExecutor(store).execute(plan, CancelToken())
    assert summary.failed == 1
    assert not any(plan.output_root.rglob("*.part"))
~~~

- [ ] **Step 2: 복사 테스트 실패 확인**

Run: python -m pytest tests/test_copier.py -v

Expected: FAIL because CopyExecutor does not exist

- [ ] **Step 3: 안전한 파일 단위 복사 구현**

~~~python
class CancelToken:
    def cancel(self) -> None: ...
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class CopyProgress:
    media_id: str
    completed_files: int
    total_files: int
    completed_bytes: int
    total_bytes: int
    status: CopyStatus


@dataclass(frozen=True, slots=True)
class CopySummary:
    verified: int
    duplicates: int
    failed: int
    skipped_verified: int
    cancelled: bool


class CopyExecutor:
    def __init__(self, store: JobStore) -> None: ...
    def execute(
        self,
        plan: CopyPlan,
        cancel: CancelToken,
        progress: Callable[[CopyProgress], None] = lambda _: None,
    ) -> CopySummary: ...
~~~

각 PLANNED 파일은 대상 디렉터리를 만든 뒤 .파일명.media_id.part에 복사한다. shutil.copyfileobj의 length는 8MiB이며 블록 사이에 취소를 확인한다. shutil.copystat으로 시각을 복사하고 SHA-256 검증 성공 후 os.replace로 최종 이름을 만든다. 최종 파일이 이미 있고 해시가 같으면 VERIFIED로 복구하며, 해시가 다르면 덮어쓰지 않고 오류 처리한다.

- [ ] **Step 4: 파일별 상태 커밋과 오류 저장 구현**

JobStore에 save_copy_entries, mark_copy_status, list_copy_entries, add_processing_error를 추가한다. COPYING과 VERIFIED는 파일마다 즉시 커밋한다. 취소는 현재 .part를 삭제하고 다음 파일을 시작하지 않으며 작업 phase는 COPYING으로 유지한다.

WorkflowService.execute_copy(job_id, progress)는 phase를 COPYING으로 전환하고 저장된 copy_entries로 CopyExecutor를 실행한다. WorkflowService.cancel_copy(job_id)는 해당 작업의 CancelToken을 설정한다. 복사를 다시 요청하면 저장된 VERIFIED 파일을 검증한 뒤 이어서 처리한다.

Run: python -m pytest tests/test_copier.py tests/test_store.py -v

Expected: all passed

- [ ] **Step 5: 복사 실행기 커밋**

~~~powershell
git add src/photoclassifier/copier.py src/photoclassifier/store.py src/photoclassifier/workflow.py tests
git commit -m "feat: copy media with resumable hash verification"
~~~

### Task 10: 편집자용 보고서와 완료 무결성

**Files:**
- Create: src/photoclassifier/reports.py
- Create: tests/test_reports.py
- Modify: src/photoclassifier/workflow.py

**Interfaces:**
- Consumes: JobStore media, decisions, copy entries, errors
- Produces: ReportPaths, write_reports, verify_job_accounting

- [ ] **Step 1: CSV 인코딩·정렬·합계 실패 테스트 작성**

~~~python
def test_classification_csv_is_utf8_bom_and_editor_sorted(tmp_path: Path) -> None:
    paths = write_reports(report_fixture(tmp_path))
    raw = paths.classification_csv.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    assert [row["결과 주제"] for row in rows] == ["A", "A", "B"]
    assert list(rows[0])[:4] == ["결과 주제", "미디어 종류", "촬영 시각", "출처자"]


def test_accounting_requires_every_input_to_have_final_state() -> None:
    with pytest.raises(ValueError, match="최종 상태가 없는 파일"):
        verify_job_accounting(media_ids={"a", "b"}, final_media_ids={"a"})
~~~

- [ ] **Step 2: 보고서 테스트 실패 확인**

Run: python -m pytest tests/test_reports.py -v

Expected: FAIL because reports module does not exist

- [ ] **Step 3: 세 CSV와 편집자 안내서 구현**

분류목록.csv 열 순서는 결과 주제, 미디어 종류, 촬영 시각, 출처자, 원본 파일명, 원본 경로, 결과 상대 경로, 파일 크기, SHA-256, 분류 방식, 분류 신뢰 등급, 최상위 대안 주제다. 중복파일.csv는 대표 결과 상대 경로, 대표 원본, 생략 원본, 출처자, SHA-256을 쓴다. 처리오류.csv는 처리 단계, 원본 경로, 오류 요약, 재시도 가능 여부를 쓴다.

~~~python
@dataclass(frozen=True, slots=True)
class ReportInput:
    job: JobRecord
    media: tuple[MediaRecord, ...]
    decisions: Mapping[str, ClassificationDecision]
    copy_entries: tuple[CopyEntry, ...]
    errors: tuple[ProcessingError, ...]


@dataclass(frozen=True, slots=True)
class ReportPaths:
    classification_csv: Path
    duplicates_csv: Path
    errors_csv: Path
    editor_readme: Path


def write_reports(report: ReportInput) -> ReportPaths: ...
~~~

모든 CSV는 open(path, "w", encoding="utf-8-sig", newline="")와 csv.DictWriter를 사용한다. README_편집자용.txt에는 폴더 구조, 검토필요의 의미, 분류목록 열 설명, Google Drive 폴더 업로드 절차를 한국어로 쓴다.

- [ ] **Step 4: 완료 전 계정 일치와 보고서 재생성 연결**

verify_job_accounting은 모든 media.id가 VERIFIED, DUPLICATE, ERROR 중 하나인지 검사한다. 통과한 경우에만 WorkflowService.complete가 보고서를 원자적 임시 파일 교체로 쓰고 phase를 VERIFIED로 바꾼다. 보고서 쓰기 실패 시 phase는 COPYING에 남긴다.

Run: python -m pytest tests/test_reports.py tests/test_workflow.py -v

Expected: all passed

- [ ] **Step 5: 보고서 커밋**

~~~powershell
git add src/photoclassifier/reports.py src/photoclassifier/workflow.py tests
git commit -m "feat: generate editor manifests and completion reports"
~~~

### Task 11: 로컬 API와 백그라운드 실행기

**Files:**
- Create: src/photoclassifier/web/__init__.py
- Create: src/photoclassifier/web/schemas.py
- Create: src/photoclassifier/web/runner.py
- Create: src/photoclassifier/web/app.py
- Create: tests/web/test_api.py

**Interfaces:**
- Consumes: WorkflowService, CopyExecutor, JobStore
- Produces: create_app, WorkflowRegistry, JobRunner, REST API, 안전한 preview/video 응답

- [ ] **Step 1: 앱 바인딩과 핵심 API 계약 실패 테스트 작성**

~~~python
def test_create_scan_review_and_plan_flow(client: TestClient, source_fixture: Path, tmp_path: Path) -> None:
    created = client.post("/api/jobs", json={
        "source_root": str(source_fixture),
        "output_parent": str(tmp_path / "out"),
    })
    assert created.status_code == 201
    job_id = created.json()["id"]

    assert client.post(f"/api/jobs/{job_id}/scan", json={"mode_overrides": {}}).status_code == 202
    wait_for_phase(client, job_id, "scanned")
    assert client.get(f"/api/jobs/{job_id}/contributors").status_code == 200


def test_media_endpoint_accepts_only_known_media_id(client: TestClient) -> None:
    response = client.get("/api/media/not-known")
    assert response.status_code == 404


def test_known_video_supports_range_requests(client: TestClient, registered_video_id: str) -> None:
    response = client.get(
        f"/api/media/{registered_video_id}/original",
        headers={"Range": "bytes=0-1023"},
    )
    assert response.status_code == 206
    assert response.headers["content-range"].startswith("bytes 0-")


def test_clear_cache_never_deletes_state_database(
    client: TestClient,
    completed_job: CompletedJobFixture,
) -> None:
    response = client.delete(f"/api/jobs/{completed_job.id}/cache")
    assert response.status_code == 204
    assert completed_job.state_database.is_file()
    assert not completed_job.cache_root.exists()
~~~

- [ ] **Step 2: API 테스트 실패 확인**

Run: python -m pytest tests/web/test_api.py -v

Expected: FAIL because create_app does not exist

- [ ] **Step 3: 요청·응답 모델과 JobRunner 구현**

JobRunner는 ThreadPoolExecutor(max_workers=1)를 사용해 한 번에 하나의 CPU/GPU 분석 작업만 실행한다. 같은 job_id와 operation의 중복 제출을 409로 거부한다. 예외는 processing_errors에 기록하고 GET /api/jobs/{id}의 active_operation, progress, last_error에 노출한다.

~~~python
class CreateJobRequest(BaseModel):
    source_root: Path
    output_parent: Path


class OpenJobRequest(BaseModel):
    output_root: Path


class ScanRequest(BaseModel):
    mode_overrides: dict[str, ContributorMode] = Field(default_factory=dict)


class MergeRequest(BaseModel):
    aliases: dict[str, str]


class DecisionRequest(BaseModel):
    media_ids: list[str]
    category: str | None = None
    defer: bool = False
~~~

WorkflowRegistry는 job_id→WorkflowService를 프로세스 메모리에 보관한다. create는 WorkflowService.create_new를 호출하고, open은 WorkflowService.open_existing을 호출한다. 같은 job_id를 다시 열면 기존 인스턴스를 반환한다. 재시작 뒤에는 사용자가 결과 폴더를 지정해 작업을 다시 연다.

- [ ] **Step 4: REST 엔드포인트 구현**

정확한 엔드포인트 목록은 다음과 같다.

~~~text
POST /api/jobs
POST /api/jobs/open
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/scan
GET  /api/jobs/{job_id}/contributors
GET  /api/jobs/{job_id}/merge-candidates
PUT  /api/jobs/{job_id}/merges
POST /api/jobs/{job_id}/analyze
GET  /api/jobs/{job_id}/review-items
PUT  /api/jobs/{job_id}/decisions
GET  /api/jobs/{job_id}/plan
POST /api/jobs/{job_id}/confirm-plan
POST /api/jobs/{job_id}/copy
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/reports
DELETE /api/jobs/{job_id}/cache
GET  /api/media/{media_id}/preview
GET  /api/media/{media_id}/original
~~~

상태를 건너뛰는 요청은 409, 없는 작업·미디어는 404, 잘못된 경로·이름은 422를 반환한다. original은 JobStore에 등록된 media_id만 Path.resolve 후 FileResponse로 제공하며 사용자가 보낸 임의 경로는 받지 않는다. MP4 original은 브라우저 탐색 재생을 위해 Range 요청에 206과 Content-Range를 반환한다. cache 삭제는 활성 작업이 없을 때만 output_root/.photoclassifier/cache의 확인된 절대 경로를 지우고 state.sqlite3는 보존한다.

- [ ] **Step 5: API 테스트 통과 확인**

Run: python -m pytest tests/web/test_api.py -v

Expected: all passed, including invalid transition, duplicate operation, and unknown media checks

- [ ] **Step 6: API 커밋**

~~~powershell
git add src/photoclassifier/web tests/web/test_api.py
git commit -m "feat: expose local classification workflow API"
~~~

### Task 12: 영상 편집자 중심 브라우저 UI

**Files:**
- Create: src/photoclassifier/web/templates/index.html
- Create: src/photoclassifier/web/static/app.js
- Create: src/photoclassifier/web/static/styles.css
- Create: tests/web/test_ui_contract.py
- Modify: src/photoclassifier/web/app.py

**Interfaces:**
- Consumes: Task 11 REST API
- Produces: 원본 선택부터 완료까지 한 화면에서 진행하는 한국어 UI

- [ ] **Step 1: 필수 UI 영역 계약 테스트 작성**

~~~python
def test_index_contains_editor_workflow_controls(client: TestClient) -> None:
    html = client.get("/").text
    required_ids = [
        "source-root", "output-parent", "resume-output-root", "scan-button", "contributors-step",
        "merges-step", "analysis-step", "review-step", "plan-step",
        "copy-step", "completion-step", "clear-cache-button",
    ]
    for element_id in required_ids:
        assert f'id="{element_id}"' in html


def test_static_assets_are_served(client: TestClient) -> None:
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
~~~

- [ ] **Step 2: UI 계약 테스트 실패 확인**

Run: python -m pytest tests/web/test_ui_contract.py -v

Expected: FAIL because template and static assets do not exist

- [ ] **Step 3: 9단계 단일 페이지 구조 구현**

index.html은 새 작업의 원본·결과 위치 선택, 기존 결과 폴더에서 재개, 구조 확인, 폴더명 정리, 분석 진행, 분류 검토, 실행 계획, 복사·검증, 완료 섹션을 갖는다. 완료되지 않은 다음 섹션은 disabled와 aria-disabled=true를 함께 사용한다. 현재 단계 제목, 전체 진행률, 원본 불변 안내를 항상 상단에 표시한다.

검토 카드는 다음 정보를 반드시 표시한다.

~~~html
<article class="review-card" data-media-id="">
  <img class="review-preview" alt="분류할 미디어 미리보기">
  <video class="review-video" controls preload="metadata"></video>
  <div class="capture-time"></div>
  <div class="contributor"></div>
  <div class="recommendation"></div>
  <div class="confidence-reason"></div>
  <select class="category-choice"></select>
  <button class="create-category">새 주제</button>
  <button class="defer-item">검토필요로 보내기</button>
</article>
~~~

- [ ] **Step 4: API 상태 관리와 일괄 검토 구현**

app.js는 fetchJson(url, options), pollJob(jobId), renderReviewItems(items), submitBulkDecision(mediaIds, category), renderPlan(plan), startCopy(jobId)를 각각 독립 함수로 구현한다. 선택 체크박스와 촬영 시각 범위 선택으로 여러 미디어를 같은 주제로 배정한다. 네트워크 오류는 3회 지수 재시도 후 화면 상단 오류 영역에 다음 행동과 함께 표시한다.

- [ ] **Step 5: 편집자 가독성 CSS와 접근성 구현**

썸네일 그리드는 1600px 이상 5열, 1100px 이상 3열, 그 미만 1열이다. 선택 카드, 검토필요, 고신뢰도, 오류 상태는 색뿐 아니라 텍스트 배지를 함께 사용한다. 긴 경로는 중간 생략하되 title에 전체 경로를 둔다. 모든 버튼과 select는 키보드 포커스 윤곽을 가진다.

- [ ] **Step 6: UI 계약과 API 회귀 테스트**

Run: python -m pytest tests/web -v

Expected: all passed

- [ ] **Step 7: 브라우저 UI 커밋**

~~~powershell
git add src/photoclassifier/web tests/web
git commit -m "feat: add editor-focused classification interface"
~~~

### Task 13: 실행 명령, 실제 자료 검사, 전체 통합

**Files:**
- Create: src/photoclassifier/cli.py
- Create: src/photoclassifier/__main__.py
- Create: scripts/setup.ps1
- Create: scripts/run.ps1
- Create: tests/integration/test_end_to_end.py
- Modify: README.md

**Interfaces:**
- Consumes: create_app, WorkflowService, scan_source
- Produces: main(argv), photoclassifier serve, photoclassifier inspect, setup/run scripts, 실제 입력 dry inspection

- [ ] **Step 1: CLI와 종단 간 실패 테스트 작성**

~~~python
def test_inspect_prints_supported_counts(
    source_fixture: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["inspect", "--source", str(source_fixture), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["total"] == 3
    assert payload["photos"] == 2
    assert payload["videos"] == 1


def test_end_to_end_fake_model_creates_verified_editor_tree(e2e_fixture: EndToEndFixture) -> None:
    result = e2e_fixture.run()
    assert result.output_root.joinpath("넥서스아니마", "사진").is_dir()
    assert result.output_root.joinpath("넥서스아니마", "동영상").is_dir()
    assert result.output_root.joinpath("분류목록.csv").is_file()
    assert result.summary.failed == 0
    assert result.summary.verified + result.summary.duplicates == result.input_count
~~~

- [ ] **Step 2: CLI 및 종단 간 테스트 실패 확인**

Run: python -m pytest tests/integration/test_end_to_end.py -v

Expected: FAIL because cli and end-to-end fixture do not exist

- [ ] **Step 3: serve와 inspect 명령 구현**

~~~python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="photoclassifier")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1"])
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("--source", type=Path, required=True)
    inspect_cmd.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_command(args)
~~~

serve는 uvicorn을 시작하기 전에 ffmpeg와 ffprobe를 shutil.which로 확인하고, 브라우저를 http://127.0.0.1:8765에 한 번 연다. inspect는 파일을 복사하거나 모델을 내려받지 않고 스캔 요약과 지원하지 않는 파일 수만 출력한다.

- [ ] **Step 4: 설치·실행 PowerShell 스크립트 작성**

scripts/setup.ps1은 다음 명령을 오류 시 즉시 중단하도록 실행한다.

~~~powershell
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
try {
    .\.venv\Scripts\python.exe -m pip install -e ".[ocr]"
} catch {
    Write-Warning "선택적 OCR 설치에 실패했습니다. 비전 분류 기능만으로 계속 실행할 수 있습니다."
}
.\.venv\Scripts\python.exe -m pytest --collect-only -q
~~~

scripts/run.ps1은 가상환경이 없으면 setup.ps1 실행 안내와 함께 종료하고 다음 명령으로 앱을 연다.

~~~powershell
$ErrorActionPreference = "Stop"
.\.venv\Scripts\python.exe -m photoclassifier serve
~~~

- [ ] **Step 5: README를 사용자 실행 절차로 교체**

README에는 다음 내용을 실제 명령과 함께 쓴다.

1. scripts/setup.ps1 최초 1회 실행
2. scripts/run.ps1 실행
3. 수집 폴더와 결과 상위 폴더 입력
4. 폴더명·저신뢰도 검토
5. 복사 계획 승인
6. 완료 후 선택적으로 미리보기 캐시 삭제
7. 완료된 편집자전달용 폴더를 Google Drive의 폴더 업로드로 전송
8. 중단 후 같은 결과 폴더의 state.sqlite3로 재개
9. 모델 다운로드 실패, FFmpeg 없음, 디스크 부족 해결 방법

- [ ] **Step 6: 전체 자동 테스트와 커버리지 실행**

Run: python -m pytest -v

Expected: all passed

Run: python -m pytest --cov=photoclassifier --cov-report=term-missing

Expected: core modules scanner, categories, classifier, copyplan, copier, reports each at least 90%; total at least 85%

- [ ] **Step 7: 실제 게임스컴 폴더 복사 없는 검사**

Run:

~~~powershell
.\.venv\Scripts\python.exe -m photoclassifier inspect --source "C:\Users\user\Desktop\게임스컴자료\편집용분류\수집" --json
~~~

Expected JSON fields:

~~~json
{
  "total": 275,
  "photos": 162,
  "videos": 113,
  "contributors": 3,
  "bytes": 19618589977
}
~~~

bytes는 스캔 시점 이후 원본이 바뀌면 달라질 수 있으므로 total, photos, videos, contributors를 필수 검증값으로 사용하고 bytes 변화는 사용자에게 보고한다. inspect는 결과 파일을 만들지 않는다.

- [ ] **Step 8: 로컬 서버 보안·화면 스모크 확인**

Run: .\scripts\run.ps1

Expected: 브라우저가 http://127.0.0.1:8765/에서 열리고, netstat -ano | findstr :8765 결과의 로컬 주소가 127.0.0.1:8765이며 0.0.0.0:8765가 아니다.

원본 경로를 넣고 스캔까지만 실행하여 3명, 275개, JPG/JPEG 162개, MP4 113개가 화면과 API에서 일치하는지 확인한다. 복사 버튼은 사용자가 분류 검토와 계획 승인을 마칠 때까지 누르지 않는다.

- [ ] **Step 9: 통합과 사용자 문서 커밋**

~~~powershell
git add src/photoclassifier/cli.py src/photoclassifier/__main__.py scripts README.md tests/integration
git commit -m "feat: deliver runnable photo classification workflow"
~~~

## Spec Coverage Check

| 설계 문서 범위 | 구현 작업 |
|---|---|
| 목적, 입력, 사용자 결정, 성공 기준, 범위 | Global Constraints, Tasks 1–13 |
| 기술 구조와 작업 상태 | Tasks 1, 7, 11 |
| 폴더명 통합 | Task 3 |
| 사진·영상 분석, OCR, 혼합 주제 영상 | Tasks 4–6 |
| 신뢰도 보정과 자동·수동 분류 | Tasks 6–7 |
| 검토 화면과 일괄 작업 | Task 12 |
| 결과 구조, 파일명 충돌, 정확한 중복 | Task 8 |
| 복사, 검증, 취소, 재개 | Tasks 7, 9 |
| CSV와 편집자 안내 | Task 10 |
| 오류 처리와 입력 변경 감지 | Tasks 2, 4, 5, 7, 9, 11 |
| 로컬 전용 보안과 캐시 삭제 | Tasks 5, 11, 12 |
| 자동·실제 자료 검증 | Tasks 1–13, Final Verification Gate |
| 실행과 Google Drive 전달 절차 | Task 13 |

설계 문서의 구현 대상 요구사항은 모두 작업에 연결되어 있다. 향후 확장에 적힌 Drive API, ZIP, 프록시 영상, 연락처 시트, 프로젝트 프리셋은 계획에 포함하지 않는다.

## Final Verification Gate

구현 완료를 선언하기 직전에 다음을 새 터미널에서 순서대로 실행한다.

~~~powershell
git status --short
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pytest --cov=photoclassifier --cov-report=term-missing
.\.venv\Scripts\python.exe -m photoclassifier inspect --source "C:\Users\user\Desktop\게임스컴자료\편집용분류\수집" --json
~~~

합격 조건:

- git status --short에 의도하지 않은 파일이 없다.
- 전체 테스트가 통과한다.
- 핵심 모듈 커버리지가 각각 90% 이상이고 전체가 85% 이상이다.
- 실제 입력 요약이 275개, 사진 162개, 영상 113개, 출처자 3명이다.
- 입력 폴더의 파일 크기, 수정 시각, SHA-256을 구현 전 표본과 비교했을 때 변하지 않는다.
- 앱이 127.0.0.1에만 열린다.
- 사용자 승인 없이 실제 19.6GB 복사를 시작하지 않는다.
