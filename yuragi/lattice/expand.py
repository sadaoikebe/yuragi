"""Token faces and the shared literal/reading boundary."""


def is_literal_face(text: str) -> bool:
    """NICOLA readings are hiragana U+3041..U+3096 and ー; other faces are literal."""
    return not all("ぁ" <= ch <= "ゖ" or ch == "ー" for ch in text)


def token_branches(token: dict) -> list[str]:
    if token["kind"] == "literal":
        return [token["text"]]
    if token["kind"] == "plain":
        return [token["kana"]]
    return list(token["faces"].values())
