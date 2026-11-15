"""Candidates for a typed symbol (symbols design §5, the half-width receiver).

Keys never type half-width characters; converting offers them. A symbol
segment's rows are the typed symbol first (the 1-best composition stays as
typed, full-width first, design §7 I), then its half-width counterpart, then
a few near symbols. A run of digits has its own rows (numbers.py).
"""
from __future__ import annotations

# Not in the full-width ASCII block, so not mechanical: 「 → [ is in §5; 」 → ]
# is its pair. ’ ” are the faces of the ' key, whose half-width forms are ' ".
_HALF_EXTRA = {"「": "[", "」": "]", "’": "'", "”": '"', "￥": "¥"}

# §5 item 2, in the design's direction: typed symbol → near symbols. 」 mirrors 「.
NEAR = {
    "、": "，",
    "。": "．",
    "”": "“",
    "’": "‘",
    "￥": "＼",
    "～": "〜",  # U+FF5E → the wave dash U+301C (§7 F)
    "「": "［【〔",
    "」": "］】〕",
}


def half_width(ch: str) -> str | None:
    """The half-width counterpart of a full-width symbol, if it has one."""
    if "！" <= ch <= "～":
        return chr(ord(ch) - 0xFEE0)
    return _HALF_EXTRA.get(ch)


def symbol_spellings(ch: str) -> list[str]:
    rows = [ch]
    if (half := half_width(ch)) is not None:
        rows.append(half)
    rows += NEAR.get(ch, "")
    return list(dict.fromkeys(rows))
