import hashlib
from collections.abc import Callable
from pathlib import Path


class CancelledError(RuntimeError):
    """Raised when a caller cancels a long-running file hash."""


def sha256_file(path: Path, cancel_check: Callable[[], bool] = lambda: False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            if cancel_check():
                raise CancelledError(str(path))
            digest.update(block)
    return digest.hexdigest()
