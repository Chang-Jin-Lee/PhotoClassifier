import json
import re
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from ..domain import MediaKind

_FILENAME_TIME = re.compile(r"(?<!\d)(\d{8})[_-](\d{6})(?!\d)")


def run_ffprobe(path: Path) -> Mapping[str, Any]:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "--", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=True,
    )
    return json.loads(completed.stdout)


def read_capture_time(
    path: Path,
    kind: MediaKind,
    ffprobe_runner: Callable[[Path], Mapping[str, Any]] = run_ffprobe,
) -> datetime | None:
    captured_at = _photo_exif_time(path) if kind is MediaKind.PHOTO else _video_creation_time(path, ffprobe_runner)
    return captured_at or _filename_time(path)


def _photo_exif_time(path: Path) -> datetime | None:
    try:
        with Image.open(path) as image:
            value = image.getexif().get(36867)
        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S") if isinstance(value, str) else None
    except (OSError, ValueError):
        return None


def _video_creation_time(path: Path, ffprobe_runner: Callable[[Path], Mapping[str, Any]]) -> datetime | None:
    try:
        probe = ffprobe_runner(path)
        format_tags = probe.get("format", {}).get("tags", {})
        values = [format_tags.get("creation_time")]
        values.extend(stream.get("tags", {}).get("creation_time") for stream in probe.get("streams", []))
        for value in values:
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, AttributeError):
        pass
    return None


def _filename_time(path: Path) -> datetime | None:
    match = _FILENAME_TIME.search(path.stem)
    if match is None:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None
