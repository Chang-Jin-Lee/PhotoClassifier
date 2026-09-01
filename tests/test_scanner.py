from datetime import datetime
from pathlib import Path

import pytest

from photoclassifier.domain import ContributorMode, JobRecord
from photoclassifier.hashing import CancelledError, sha256_file
from photoclassifier.scanner import scan_source

from tests.conftest import write_jpeg


def test_scan_infers_classified_and_unclassified_contributors(tmp_path: Path) -> None:
    source = tmp_path / "수집"
    write_jpeg(source / "서주영" / "사진" / "20260826_084948.jpg")
    write_jpeg(source / "이상민" / "넥서스아니마" / "20260826_085521.jpg")

    result = scan_source(JobRecord.new("job-1", source, tmp_path / "out"), {})

    by_person = {item.name: item for item in result.contributors}
    assert by_person["서주영"].mode is ContributorMode.UNCLASSIFIED
    assert by_person["이상민"].mode is ContributorMode.CLASSIFIED
    assert result.media[0].captured_at == datetime(2026, 8, 26, 8, 49, 48)
    assert {item.existing_category for item in result.media} == {None, "넥서스아니마"}


def test_scan_ignores_unsupported_files(tmp_path: Path) -> None:
    source = tmp_path / "수집"
    ignored = source / "서주영" / "사진" / "메모.txt"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("x", encoding="utf-8")

    result = scan_source(JobRecord.new("job-1", source, tmp_path / "out"), {})

    assert result.media == []
    assert result.ignored_count == 1
    assert result.ignored_files == (ignored.resolve(),)


def test_scan_uses_override_and_stable_absolute_order(tmp_path: Path) -> None:
    source = tmp_path / "수집"
    write_jpeg(source / "B" / "사진" / "20260826_084948.jpg")
    write_jpeg(source / "A" / "주제" / "20260826_085521.jpg")

    result = scan_source(
        JobRecord.new("job-1", source, tmp_path / "out"),
        {"A": ContributorMode.UNCLASSIFIED},
    )

    assert [item.source_path for item in result.media] == sorted(item.source_path for item in result.media)
    assert next(item for item in result.contributors if item.name == "A").mode is ContributorMode.UNCLASSIFIED


def test_sha256_file_cancels_before_reading_a_block(tmp_path: Path) -> None:
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"content")

    with pytest.raises(CancelledError, match="photo.jpg"):
        sha256_file(path, cancel_check=lambda: True)
