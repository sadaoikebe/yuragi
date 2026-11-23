"""Download Mozc OSS dictionary text (not a full Mozc build)."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "third_party" / "mozc_oss_dict"
# The files, their SHA-256 and the upstream commit they are fetched from
# (upstream_commit) are all in the manifest, and only there.
MANIFEST = ROOT / "data" / "dictionary-manifest.json"
BASE = "https://raw.githubusercontent.com/google/mozc/{}/src/data/dictionary_oss/"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()




def _is_current(dest: Path, expected: str) -> bool:
    # Only an exact match counts: a file fetched from another upstream
    # revision (e.g. master) is replaced, not kept.
    return dest.exists() and _sha256(dest) == expected


def main(argv=()) -> None:
    """python -m tools.eval.fetch_mozc_dict [--out DIR] (default third_party/mozc_oss_dict)."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None,
                        help="where to put the files (the installer: shared\\dict\\<commit>)")
    out = parser.parse_args(argv).out or OUT
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    base = BASE.format(manifest["upstream_commit"])
    for name, entry in manifest["files"].items():
        dest = out / name
        if _is_current(dest, entry["sha256"]):
            print("skip", name, dest.stat().st_size)
            continue
        print("GET", name)
        urllib.request.urlretrieve(base + name, dest)
        print(" ", dest.stat().st_size)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
