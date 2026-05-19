import hashlib
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Hasher(Protocol):
    @property
    def algorithm(self) -> str:
        ...

    def hash(self, file_path: Path) -> str:
        ...


class Sha256Hasher:
    @property
    def algorithm(self) -> str:
        return "sha256"

    def hash(self, file_path: Path) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return h.hexdigest()
