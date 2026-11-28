"""Download Mozc OSS dictionary text (not a full Mozc build).

  python -m tools.eval.fetch_mozc_dict [--out DIR]     (default third_party/mozc_oss_dict)

The files come from the google/mozc commit in yuragi/lattice/mozc_dict.py
(UPSTREAM_COMMIT). After changing that line, run this again.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from yuragi.lattice.mozc_dict import DICT_DIR, LOADER_FILES, UPSTREAM_COMMIT

# What the loader reads, id.def for the names of the parts of speech, the evaluation set,
# and the upstream notices that travel with them.
FILES = [*LOADER_FILES, "id.def", "evaluation.tsv", "README.txt", "README.md"]
BASE = f"https://raw.githubusercontent.com/google/mozc/{UPSTREAM_COMMIT}/src/data/dictionary_oss/"


def main(argv=()) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DICT_DIR,
                        help="where to put the files (the installer: shared\\dict\\<commit>)")
    out = parser.parse_args(argv).out
    out.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        print("GET", name, flush=True)
        urllib.request.urlretrieve(BASE + name, out / name)  # raises when the download is cut short


if __name__ == "__main__":
    main(sys.argv[1:])
