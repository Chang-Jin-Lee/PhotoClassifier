from datetime import UTC, datetime
from pathlib import Path

import pytest

from photoclassifier.domain import MediaKind
from photoclassifier.media.metadata import read_capture_time

from tests.conftest import write_jpeg


def test_read_capture_time_prefers_photo_exif_datetime_original(tmp_path: Path) -> None:
    path = tmp_path / "20260826_084948.jpg"
    write_jpeg(path, captured_at="2025:01:02 03:04:05")

    assert read_capture_time(path, MediaKind.PHOTO) == datetime(2025, 1, 2, 3, 4, 5)


@pytest.mark.parametrize("filename, expected", [
    ("20260826_084948.jpg", datetime(2026, 8, 26, 8, 49, 48)),
    ("20260826-085521.mp4", datetime(2026, 8, 26, 8, 55, 21)),
])
def test_read_capture_time_falls_back_to_filename(filename: str, expected: datetime, tmp_path: Path) -> None:
    path = tmp_path / filename
    path.write_bytes(b"not a valid media file")

    assert read_capture_time(path, MediaKind.PHOTO if path.suffix == ".jpg" else MediaKind.VIDEO) == expected


def test_read_capture_time_reads_video_ffprobe_creation_time(tmp_path: Path) -> None:
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"video")

    result = read_capture_time(
        path,
        MediaKind.VIDEO,
        lambda _: {"format": {"tags": {"creation_time": "2026-08-26T08:55:21Z"}}},
    )

    assert result == datetime(2026, 8, 26, 8, 55, 21, tzinfo=UTC)
