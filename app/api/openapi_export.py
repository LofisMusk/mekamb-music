from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from app.main import app


def export_openapi(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the Mekamb Music OpenAPI schema.")
    parser.add_argument(
        "output",
        nargs="?",
        default="openapi.json",
        help="Path to write the OpenAPI JSON file. Defaults to openapi.json.",
    )
    args = parser.parse_args(argv)
    export_openapi(Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

