"""Download an LM model at a pinned revision (DESIGN「インストール・更新・アンインストール」).

Run with the installation's own Python (the one that will run the
server), so the only network dependency is HuggingFace:

  python packaging/fetch_model.py <name> <dest-dir>            name: medium | small

medium is for a GPU, small for the CPU (CONVERSION「装置とモデル」). The
revision is a full commit hash: what gets installed never floats with the
upstream repository. setup.ps1 and the release workflow read the MODEL_ lines.
"""

from __future__ import annotations

import sys

MODEL_medium = ("Miwa-Keita/zenz-v2.5-medium", "623bc8edf5417129b8269b628223d08245e9c68e")
MODEL_small = ("Miwa-Keita/zenz-v2.5-small", "1e408d69a7e284efa4e4d63e456f50e363a82953")
MODELS = {"medium": MODEL_medium, "small": MODEL_small}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in MODELS:
        print(__doc__)
        return 2
    repo_id, revision = MODELS[argv[0]]
    from huggingface_hub import snapshot_download

    snapshot_download(repo_id=repo_id, revision=revision, local_dir=argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
