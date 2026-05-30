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
