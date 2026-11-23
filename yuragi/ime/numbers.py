"""Spellings for a run of typed digits (a number rewriter).

The typed digits stay first, so the 1-best composition is unchanged. The
other rows are the usual IME spellings of the same number. The digit keys
type full-width digits; the half-width ones are the next row.
"""
from __future__ import annotations

from yuragi.text import to_full_width

KANJI_DIGITS = "〇一二三四五六七八九"
SMALL_UNITS = ((1000, "千"), (100, "百"), (10, "十"))
LARGE_UNITS = ("", "万", "億", "兆", "京")


def is_digit(ch: str) -> bool:
    return "0" <= ch <= "9" or "０" <= ch <= "９"


def half_width_digits(digits: str) -> str:
    return "".join(chr(ord(c) - 0xFEE0) if "０" <= c <= "９" else c for c in digits)


def _below_10000(n: int) -> str:
    out = ""
    for value, unit in SMALL_UNITS:
        d, n = divmod(n, value)
        if d:
            out += ("" if d == 1 else KANJI_DIGITS[d]) + unit
    return out + (KANJI_DIGITS[n] if n else "")


def positional_kanji(digits: str) -> str | None:
    """千二百三十四 for 1234; None where the reading is not a plain quantity."""
    if len(digits) > 1 and digits[0] == "0":
        return None  # 007 is a code, not a quantity.
    n = int(digits)
    if n == 0:
        return "〇"
    if n >= 10000 ** len(LARGE_UNITS):
        return None
    out = ""
    for unit in reversed(range(len(LARGE_UNITS))):
        group, n = divmod(n, 10000 ** unit)
        if group:
            out += _below_10000(group) + LARGE_UNITS[unit]
    return out


def number_spellings(digits: str) -> list[str]:
    """The typed digits, half-width, full-width, kanji digit by digit,
    positional kanji, grouped."""
    typed, digits = digits, half_width_digits(digits)
    wide = to_full_width(digits)
    rows = [typed, digits, wide, "".join(KANJI_DIGITS[int(c)] for c in digits)]
    if (kanji := positional_kanji(digits)) is not None:
        rows.append(kanji)
    if len(digits) >= 4 and digits[0] != "0":
        grouped = f"{int(digits):,}"
        rows += [grouped, to_full_width(grouped)]
    return list(dict.fromkeys(rows))
