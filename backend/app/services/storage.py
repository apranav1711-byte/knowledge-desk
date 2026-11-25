"""Original uploaded files, kept in a folder on this PC (data/files/<tenant>/<document>/<name>)."""
from pathlib import Path

from app.core.config import settings


def _path(rel: str) -> Path:
    root = settings.STORAGE_DIR.resolve()
    p = (root / rel).resolve()
    if root not in p.parents:  # never escape the storage folder
        raise ValueError("invalid storage path")
    return p


def put(rel: str, data: bytes) -> None:
    p = _path(rel)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def get(rel: str) -> bytes:
    return _path(rel).read_bytes()


def delete(rel: str) -> None:
    p = _path(rel)
    p.unlink(missing_ok=True)
    for d in (p.parent, p.parent.parent):  # tidy empty <document>/<tenant> folders
        try:
            d.rmdir()
        except OSError:
            break
