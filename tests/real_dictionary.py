"""The real dictionary for the tests, read once per test process.

It takes about 1.5 GB and a few seconds to load; a class that kept its own
copy made the whole suite hold several of them at once. The tests share this
one and must not change it.
"""
from __future__ import annotations

from functools import cache

from yuragi.lattice.mozc_dict import MozcLex, load_lex


@cache
def real_lex() -> MozcLex:
    return load_lex()
