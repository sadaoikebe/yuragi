"""Write packaging/requirements.txt, the lock file of the bundled runtime, from requirements.in.

  python packaging/lock.py        (needs uv: https://docs.astral.sh/uv/)

uv resolves requirements.in for CPython 3.13 on 64-bit Windows and writes every package
with its version and hashes. torch has one build per PyTorch index (cpu, cu126, cu128), and
uv resolves one index at a time, so it runs once per build; everything but the torch line
comes out the same, and the torch line gets the hashes of all three. setup.ps1 installs the
file with --require-hashes from the index of the build it chose.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
BUILDS = ("cpu", "cu126", "cu128")  # setup.ps1 chooses among these (Select-TorchVariant)
HEADER = """\
# Written by packaging/lock.py from requirements.in. Do not edit: change requirements.in
# and run it again.
"""


def resolve(build: str) -> str:
    # The PyTorch indexes also carry old copies of other packages. Without best-match uv
    # would take certifi, requests and urllib3 from there, years behind PyPI.
    return subprocess.run(
        ["uv", "pip", "compile", str(HERE / "requirements.in"), "--generate-hashes", "--no-header",
         "--no-annotate", "--python-platform", "x86_64-pc-windows-msvc", "--python-version", "3.13",
         "--only-binary", ":all:", "--index-strategy", "unsafe-best-match",
         "--index", f"https://download.pytorch.org/whl/{build}", "--default-index", "https://pypi.org/simple"],
        check=True, capture_output=True, text=True, encoding="utf-8").stdout


def split(text: str) -> tuple[str, list[str]]:
    """The text with its torch entry replaced by {torch}, and that entry's hashes."""
    entry = re.search(r"^torch==\S+ \\\n((?:    --hash=\S+(?: \\)?\n)+)", text, re.MULTILINE)
    return text[:entry.start()] + "{torch}" + text[entry.end():], re.findall(r"sha256:[0-9a-f]{64}", entry[1])


def main() -> None:
    version = re.search(r"^torch==(\S+)$", (HERE / "requirements.in").read_text(encoding="utf-8"), re.MULTILINE)[1]
    rests, hashes = zip(*(split(resolve(build)) for build in BUILDS))
    if len(set(rests)) != 1:
        raise SystemExit("the torch builds do not share their other packages: one lock file cannot hold them")
    lines = " \\\n".join(f"    --hash={h}" for h in sorted(set().union(*hashes)))
    text = HEADER + rests[0].replace("{torch}", f"torch=={version} \\\n{lines}\n")
    (HERE / "requirements.txt").write_text(text, encoding="ascii")
    print(f"wrote requirements.txt: {text.count('==')} packages")


if __name__ == "__main__":
    main()
