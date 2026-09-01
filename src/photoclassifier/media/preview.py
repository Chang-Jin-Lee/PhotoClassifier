"""Generate compact photo previews and representative video frames."""

import math
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, ImageStat

from .metadata import run_ffprobe


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


ProbeRunner = Callable[[Path], Mapping[str, Any]]


def sample_timestamps(duration_seconds: float) -> list[float]:
    """Return three to twelve evenly spaced points excluding video edges."""
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        return []
    count = min(12, max(3, math.ceil(duration_seconds / 30)))
    return [duration_seconds * (0.05 + 0.90 * index / (count - 1)) for index in range(count)]


def frame_quality(image: Image.Image) -> FrameQuality:
    statistics = ImageStat.Stat(image.convert("L"))
    brightness = float(statistics.mean[0])
    contrast = float(statistics.stddev[0])
    usable = 5 <= brightness <= 250 and contrast >= 3
    return FrameQuality(usable=usable, brightness=brightness, contrast=contrast)


def create_photo_preview(source: Path, target: Path, *, max_edge: int = 1280) -> Path:
    """Cache an orientation-corrected RGB JPEG preview."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened)
        image.thumbnail((max_edge, max_edge))
        image.convert("RGB").save(target, format="JPEG", quality=88)
    return target


def video_duration_seconds(source: Path, ffprobe_runner: ProbeRunner = run_ffprobe) -> float | None:
    """Read duration from ffprobe's format first, then its video stream."""
    try:
        probe = ffprobe_runner(source)
        format_duration = _positive_duration(probe.get("format", {}).get("duration"))
        if format_duration is not None:
            return format_duration
        for stream in probe.get("streams", []):
            if stream.get("codec_type") == "video":
                duration = _positive_duration(stream.get("duration"))
                if duration is not None:
                    return duration
    except (OSError, TypeError, ValueError, subprocess.SubprocessError):
        pass
    return None


def extract_video_frames(
    source: Path,
    cache_path: Path,
    *,
    ffmpeg_executable: str = "ffmpeg",
    ffprobe_runner: ProbeRunner = run_ffprobe,
) -> AnalysisAssets:
    """Extract usable representative frames into the supplied media cache path."""
    cache_path.mkdir(parents=True, exist_ok=True)
    duration = video_duration_seconds(source, ffprobe_runner)
    if duration is None:
        return AnalysisAssets(cache_path / "preview.jpg", (), None, ("Video duration could not be determined.",))

    usable_paths = _extract_usable_frames(source, cache_path, sample_timestamps(duration), ffmpeg_executable)
    if usable_paths:
        return AnalysisAssets(usable_paths[0], tuple(usable_paths), duration)

    midpoint = cache_path / "frame-midpoint.jpg"
    if _extract_frame(source, midpoint, duration / 2, ffmpeg_executable):
        return AnalysisAssets(
            midpoint,
            (midpoint,),
            duration,
            ("All sampled video frames were low quality; preserved the midpoint frame for review.",),
        )
    return AnalysisAssets(
        cache_path / "preview.jpg",
        (),
        duration,
        ("Video frames could not be extracted.",),
    )


def _positive_duration(value: object) -> float | None:
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return duration if math.isfinite(duration) and duration > 0 else None


def _extract_usable_frames(source: Path, cache_path: Path, timestamps: list[float], ffmpeg_executable: str) -> list[Path]:
    usable_paths: list[Path] = []
    for index, second in enumerate(timestamps, start=1):
        target = cache_path / f"frame-{index:02d}.jpg"
        if _extract_frame(source, target, second, ffmpeg_executable) and _is_usable(target):
            usable_paths.append(target)
        elif target.exists():
            target.unlink()
    return usable_paths


def _extract_frame(source: Path, target: Path, second: float, ffmpeg_executable: str) -> bool:
    try:
        subprocess.run(
            [
                ffmpeg_executable, "-hide_banner", "-loglevel", "error", "-ss", f"{second:.3f}",
                "-i", str(source), "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
                "-q:v", "3", "-y", str(target),
            ],
            check=True,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return target.is_file()


def _is_usable(path: Path) -> bool:
    try:
        with Image.open(path) as image:
            return frame_quality(image).usable
    except OSError:
        return False
