"""One JSON file = one timestamped IME protocol transcript.

The recorded key events go through the same dispatch() as the engine. Checked:
no event raises, and the document formed by concatenating commits is the
recorded one. The steps are the key events only.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import Entry, MozcLex
from yuragi.lattice.table import load_table

TRANSCRIPT_NOW = datetime(2026, 11, 12, 9, 30)  # a Thursday


def make_session(case: dict, real_lex: MozcLex | None = None) -> ImeSession:
    if "lexicon" not in case:
        if real_lex is None:
            raise ValueError("a transcript without lexicon needs the real dictionary")
        lex = real_lex
    else:
        by_reading: dict[str, list[Entry]] = {}
        prefixes: set[str] = set()
        for row in case["lexicon"]:
            reading, surface = row["reading"], row["surface"]
            entry = Entry(surface, reading, row.get("lid", 1), row.get("rid", 1),
                          row.get("cost", 100))
            by_reading.setdefault(reading, []).append(entry)
            prefixes.update(reading[:i] for i in range(1, len(reading) + 1))
        matrix = case.get("connection", {"size": 2})
        size = matrix["size"]
        costs = [matrix.get("default", 0)] * (size * size)
        for rid, lid, cost in matrix.get("overrides", []):
            costs[rid * size + lid] = cost
        lex = MozcLex(by_reading, prefixes, costs, size)
    # Date rows depend on the clock; a transcript sees one fixed day.
    return ImeSession(_table=load_table(), _lex=lex,
                      clock=lambda: TRANSCRIPT_NOW)


def run_transcript(test, path: Path, real_lex: MozcLex | None = None) -> None:
    case = json.loads(path.read_text(encoding="utf-8"))
    session = make_session(case, real_lex)
    committed = ""
    for step in case["steps"]:
        committed += dispatch(session, step["event"])["commit"]
    test.assertEqual(committed, case["committed"])
