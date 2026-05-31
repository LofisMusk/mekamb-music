from pathlib import Path
from shutil import copy2


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put_file(self, source: Path, key: str) -> Path:
        target = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in target.parents:
            raise ValueError("Storage key escaped the library root.")
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, target)
        return target

    def delete_file(self, key: str) -> None:
        target = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in target.parents:
            raise ValueError("Storage key escaped the library root.")
        target.unlink(missing_ok=True)
        _remove_empty_parents(target.parent, root)


def _remove_empty_parents(path: Path, stop_at: Path) -> None:
    while path != stop_at and stop_at in path.parents:
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent
