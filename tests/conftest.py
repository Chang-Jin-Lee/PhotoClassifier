from pathlib import Path
import subprocess

import pytest
from PIL import Image

from photoclassifier.domain import ContributorMode, MediaKind, MediaRecord


def write_jpeg(path: Path, *, captured_at: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1, 1), "white")
    exif = Image.Exif()
    if captured_at:
        exif[36867] = captured_at
    image.save(path, exif=exif)


def write_oriented_jpeg(path: Path, *, orientation: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 180), "white")
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, exif=exif)
    return path


def make_mp4(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10",
            "-t", "3", "-pix_fmt", "yuv420p", "-y", str(path),
        ],
        check=True,
        shell=False,
    )
    return path


@pytest.fixture
def scanned_media(tmp_path: Path) -> list[MediaRecord]:
    source_path = tmp_path / "수집" / "서주영" / "사진" / "20260826_084948.jpg"
    write_jpeg(source_path)
    stat = source_path.stat()
    return [MediaRecord(
        id="media-1", job_id="job-1", source_path=source_path.resolve(),
        contributor="서주영", contributor_mode=ContributorMode.UNCLASSIFIED,
        existing_category=None, media_kind=MediaKind.PHOTO,
        size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns,
        captured_at=None, sha256="hash",
    )]
