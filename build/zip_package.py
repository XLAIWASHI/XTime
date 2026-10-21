"""Create the release zip with portable forward-slash entry names."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: zip_package.py <source-dir> <output.zip>", file=sys.stderr)
        return 2

    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if not source.is_dir():
        print(f"source directory not found: {source}", file=sys.stderr)
        return 1

    base = source.name
    files = sorted(path for path in source.rglob("*") if path.is_file())
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
    ) as archive:
        for path in files:
            arcname = f"{base}/{path.relative_to(source).as_posix()}"
            archive.write(path, arcname)
    print(f"wrote {output} ({output.stat().st_size / (1024 * 1024):.1f} MB, {len(files)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
