"""Symbols from their readings (きごう → ※ ☆ …).

The data is Mozc's src/data/symbol/symbol.tsv, committed unchanged as
data/symbol.tsv (not in the dictionary manifest: it travels with the code).
Like Mozc, the symbols are not dictionary words: bunsetsu.with_symbols()
inserts them among a clause's rows when the clause's reading is one of
theirs, in the file's row order (the one last chosen from that reading
first: learning.py records it).

Not used: rows whose symbol is empty or contains a character
outside the BMP (mostly hentaigana), rows described as 部首 (radicals: てへん
→ 扌, こう → 爻 would crowd ordinary words' rows), and readings of one
character (は → ㇵ would crowd a particle's rows); the other readings of that
row still give it.
"""
from __future__ import annotations

from pathlib import Path

from yuragi.lattice.mozc_dict import ROOT

SYMBOL_TSV = ROOT / "data" / "symbol.tsv"


def parse(text: str) -> dict[str, tuple[str, ...]]:
    """reading → its symbols, in the file's row order."""
    by_reading: dict[str, list[str]] = {}
    for n, line in enumerate(text.splitlines()):
        if n == 0 or not line or line.startswith("#"):
            continue  # the header (POS, CHAR, Reading ...), comments
        columns = line.split("\t")
        symbol = columns[1] if len(columns) > 1 else ""
        # Separated by spaces; one row (ECU) uses U+3000, also a space.
        readings = columns[2].split() if len(columns) > 2 else []
        description = columns[3] if len(columns) > 3 else ""
        if not symbol or any(ord(c) > 0xFFFF for c in symbol) or description == "部首":
            continue
        for reading in readings:
            if len(reading) == 1:
                continue
            symbols = by_reading.setdefault(reading, [])
            if symbol not in symbols:
                symbols.append(symbol)
    return {r: tuple(s) for r, s in by_reading.items()}


def load_symbols(path: Path = SYMBOL_TSV) -> dict[str, tuple[str, ...]]:
    return parse(Path(path).read_text(encoding="utf-8"))
