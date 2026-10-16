"""Fetch the reference JavaScript libraries listed in tests/oracle/MANIFEST.json.

They are not part of the repository. Each tarball is checked against the size and
sha256 in the manifest, then unpacked to tests/oracle/<name>/. The oracle tests skip
until this script has run and Node.js is on the PATH.

    python scripts/fetch_oracles.py
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

FOLDER = Path(__file__).resolve().parents[1] / "tests" / "oracle"


def _unpack(body: bytes, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts
            if not member.isfile() or parts[0] != "package" or ".." in parts:
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            path = target.joinpath(*parts[1:])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source.read())


def main() -> int:
    manifest = json.loads((FOLDER / "MANIFEST.json").read_text(encoding="utf-8"))
    failed = 0
    for name, entry in manifest.items():
        with urllib.request.urlopen(entry["url"], timeout=60) as response:
            body = response.read()
        digest = hashlib.sha256(body).hexdigest()
        if len(body) != entry["size"] or digest != entry["sha256"]:
            print(f"{name}: got {len(body)} bytes, sha256 {digest}; manifest differs")
            failed += 1
            continue
        _unpack(body, FOLDER / name)
        print(f"{name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
