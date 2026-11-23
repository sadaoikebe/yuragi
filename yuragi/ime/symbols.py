"""Candidates for a typed symbol (the half-width receiver).

Keys never type half-width characters; converting offers them. A symbol
segment's rows are the typed symbol first (the 1-best composition stays as
typed, full-width first), then its half-width counterpart, then
a few near symbols. A run of digits has its own rows (numbers.py).
"""
from __future__ import annotations

from yuragi.text import to_half_width

# Not in the full-width ASCII block, so not mechanical: 「 → [ and its pair 」 → ].
# ’ ” are the faces of the ' key, whose half-width forms are ' ".
_HALF_EXTRA = {"「": "[", "」": "]", "’": "'", "”": '"', "￥": "¥"}

# Typed symbol → near symbols. 」 mirrors 「.
NEAR = {
    "、": "，",
    "。": "．…‥",  # 。 then convert: the usual way to the ellipsis
    "”": "“",
    "’": "‘",
    "￥": "＼",
    "～": "〜",  # U+FF5E → the wave dash U+301C
    "「": "［【〔",
    "」": "］】〕",
}


def half_width(ch: str) -> str | None:
    """The half-width counterpart of a full-width symbol, if it has one."""
    if "！" <= ch <= "～":
        return to_half_width(ch)
    return _HALF_EXTRA.get(ch)


def symbol_spellings(ch: str) -> list[str]:
    rows = [ch]
    if (half := half_width(ch)) is not None:
        rows.append(half)
    rows += NEAR.get(ch, "")
    return list(dict.fromkeys(rows))
