from pathlib import Path

from PIL import Image

from photoclassifier.media.preview import (
    create_photo_preview,
    extract_video_frames,
    frame_quality,
    sample_timestamps,
)
from tests.conftest import make_mp4, write_oriented_jpeg


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


def test_extract_video_frames_uses_real_ffmpeg_output(tmp_path: Path) -> None:
    source = make_mp4(tmp_path / "sample.mp4")
    target_dir = tmp_path / "cache"

    assets = extract_video_frames(source, target_dir)

    assert assets.duration_seconds is not None
    assert 3 <= len(assets.frame_paths) <= 12
    assert all(path.is_file() for path in assets.frame_paths)
