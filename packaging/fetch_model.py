"""Download an LM model at a pinned revision and check its files (DESIGN「インストールと更新」).

Run with the installation's own Python (the one that will run the
server), so the only network dependency is HuggingFace:

  python packaging/fetch_model.py <name> <dest-dir>            name: medium | small

medium is for a GPU, small for the CPU (CONVERSION「装置とモデル」). The
revision is a full commit hash: what gets installed never floats with the
upstream repository. setup.ps1 and the release workflow read the MODEL_ lines.

After a download every file the engine reads must have the size and SHA-256
pinned in FILES for that revision.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

MODEL_medium = ("Miwa-Keita/zenz-v2.5-medium", "623bc8edf5417129b8269b628223d08245e9c68e")
MODEL_small = ("Miwa-Keita/zenz-v2.5-small", "1e408d69a7e284efa4e4d63e456f50e363a82953")
MODELS = {"medium": MODEL_medium, "small": MODEL_small}

# revision -> the files the engine reads: (size, SHA-256). Fixed by the revision (a commit).
_TOKENIZER = {
    "generation_config.json": (132, "7f1c883b529b8c416a112354cc8bf4d659ee2953ae94c8f536e8b241f15c020e"),
    "merges.txt": (44804, "dde8cf4cc72f4d6eb7461a1c7dde6847916f0ad405395238aaf67501e2803ca7"),
    "special_tokens_map.json": (96, "f17f705b191ddb9aef0b42e40869d325d79b2a1e229e0d51d72698b5d3e4fc90"),
    "tokenizer_config.json": (871, "bd7ac21f1da24ee416971702ffdd9c8489f0327914a067c65561f59c142f848d"),
    "vocab.json": (104544, "67fd752abb091e649a9bb08bcb2b52b27cd6e3893ff5ee6e391e5555c0a90e0f"),
}
FILES = {
    MODEL_medium[1]: {
        "config.json": (761, "53de408a3de15d99768dd3a672002e44fd31eb14dd77ac60e84cbb968efd715f"),
        "model.safetensors": (619038328, "0c6168ed97ceab703e77116f137f331e356924d02810cebb8e18bfac51d82397"),
        **_TOKENIZER,
    },
    MODEL_small[1]: {
        "config.json": (834, "1d8a326f5f6d20036467e37391239bf32d23e8a52c651242c6518bc5b85b17cd"),
        "model.safetensors": (180915904, "cbd383ceb19c2ed8563c0a0df0d3d3633aab236deaa9a058b6cc108d26e113e3"),
        **_TOKENIZER,
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def problems(revision: str, dest: Path) -> list[str]:
    found = []
    for name, (size, sha256) in FILES[revision].items():
        path = dest / name
        if not path.is_file():
            found.append(f"missing {name}")
        elif path.stat().st_size != size:
            found.append(f"size {name}: {path.stat().st_size}, not {size}")
        elif _sha256(path) != sha256:
            found.append(f"changed {name} (SHA-256)")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in MODELS:
        print(__doc__)
        return 2
    repo_id, revision = MODELS[argv[0]]
    dest = Path(argv[1])
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, revision=revision, local_dir=dest)
    found = problems(revision, dest)
    for p in found:
        print(p)
    print(f"model {repo_id}@{revision[:8]} {dest}: " + ("OK" if not found else f"{len(found)} problem(s)"))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
