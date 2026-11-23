"""Script and width conversions for displayed text and key faces."""


def katakana(hiragana: str) -> str:
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in hiragana)


def to_full_width(text: str) -> str:
    return "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)


def to_half_width(text: str) -> str:
    return "".join(chr(ord(c) - 0xFEE0) if "！" <= c <= "～" else " " if c == "　" else c
                   for c in text)
