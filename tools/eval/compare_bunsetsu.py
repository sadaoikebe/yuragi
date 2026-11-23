"""Show changed bunsetsu boundaries on identical dictionary 1-best paths."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

from yuragi.ime.bunsetsu import content, segments_from
from yuragi.lattice.mozc_dict import DICT_DIR, load_lex
from yuragi.lattice.table import load_table, reverse_table
from yuragi.lattice.token_viterbi import decode_tokens


def compare(readings, out) -> None:
    lex = load_lex()
    reverse = reverse_table(load_table())
    count = skipped = changed = old_count = new_count = 0
    for reading in readings:
        if not reading or any(kana not in reverse for kana in reading):
            skipped += 1
            continue
        decoded = decode_tokens([reverse[kana] for kana in reading], lex)
        pieces = decoded.pieces
        old = [p.start for i, p in enumerate(pieces)
               if i == 0 or p.learned or content(lex.base_pos(p.lid))]
        segments = segments_from(pieces, 0, lex)
        new = [s.start for s in segments]
        count += 1
        old_count += len(old)
        new_count += len(new)
        if old != new:
            boundaries = set(old[1:])
            before = "".join(("｜" if p.start in boundaries else "") + p.surface for p in pieces)
            after = "｜".join(s.selected.surface for s in segments)
            print(f"{reading}\t{before} ／ {after}\t{len(old)} → {len(new)}", file=out)
            changed += 1
    print(f"\n対象 {count} 文、差分 {changed} 文、対象外 {skipped} 文", file=out)
    if count:
        print(f"文節数 {old_count} → {new_count}（1文あたり "
              f"{old_count / count:.2f} → {new_count / count:.2f}）", file=out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--readings", type=Path, help="UTF-8 text, one kana reading per line")
    parser.add_argument("--output", type=Path, help="write the diff as UTF-8")
    args = parser.parse_args()
    if args.readings is not None:
        readings = args.readings.read_text(encoding="utf-8-sig").splitlines()
    else:
        with (DICT_DIR / "evaluation.tsv").open(encoding="utf-8", newline="") as stream:
            readings = [row[1] for row in csv.reader(stream, delimiter="\t")
                        if row and not row[0].startswith("#")]
    if args.output is None:
        compare(readings, sys.stdout)
    else:
        with args.output.open("w", encoding="utf-8") as out:
            compare(readings, out)


if __name__ == "__main__":
    main()
