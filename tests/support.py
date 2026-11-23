"""Shared test helpers: input typed on plain faces, and key events with a clock."""
from __future__ import annotations

from array import array

from yuragi.chord.fsm import Plain
from yuragi.ime import bunsetsu
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession, Literal
from yuragi.lattice.mozc_dict import DEFAULT_NOUN_ID, Entry, MozcLex, finish_lex
from yuragi.lattice.table import load_table

VK_RETURN, VK_SPACE, VK_DOWN = 0x0D, 0x20, 0x28

# Importing this module replaces Mozc's id.def with the parts of speech the tests use.
bunsetsu._pos_names = lambda: {
    12: ("副詞",), **dict.fromkeys((680, 684, 701, 731, 765), ("動詞", "自立")),
    1841: ("名詞", "サ変接続"), 1851: ("名詞", "一般"), 1922: ("名詞", "固有名詞", "人名", "名"),
    1931: ("名詞", "形容動詞語幹"), 2011: ("名詞", "接尾", "助数詞"), 2044: ("名詞", "数"),
    2047: ("名詞", "数"), 2051: ("名詞", "数"), 2121: ("名詞", "非自立"), 2620: ("接頭詞", "名詞接続")}


def plain_table(reading: str) -> dict:
    """A layout with each character of reading on its own key's plain face."""
    return {"keys": {c: {"plain": c} for c in reading}}


def type_plain(session: ImeSession, reading: str) -> None:
    """Set the input to reading, every character unambiguous (no FSM)."""
    session._table = plain_table(reading)
    session.tokens = [Plain(c) for c in reading]
    session._refresh()


def ingest_plain(session: ImeSession, reading: str, *, literals: str = "") -> str:
    """Type reading through the input path; the characters in literals as typed."""
    session._table = plain_table(reading)
    return session._ingest([Literal(c) if c in literals else Plain(c) for c in reading])


def kana_session(lex: MozcLex | None = None) -> ImeSession:
    """The NICOLA layout; without lex, no dictionary rows (kana stays kana)."""
    return ImeSession(_table=load_table(),
                      _lex=lex if lex is not None else MozcLex({}, set(), [0] * 4, 2))


def small_lex(words: str) -> MozcLex:
    """Lines of "reading surface cost [part of speech]", a noun by default."""
    size = 2672  # as many parts of speech as Mozc
    lex = MozcLex({}, set(), array("h", [1]) * size * size, size)
    for line in words.strip().splitlines():
        reading, surface, cost, *pos = line.split()
        pos = int(pos[0]) if pos else DEFAULT_NOUN_ID
        lex.by_reading.setdefault(reading, []).append(Entry(surface, reading, pos, pos, int(cost)))
        lex.prefixes.update(reading[:i] for i in range(1, len(reading) + 1))
    finish_lex(lex)
    return lex


class Keys:
    """Key events with a running clock and request numbers, sent to a session
    through dispatch() or to another request handler (a pipeline, an engine)."""

    def __init__(self, target):
        self.s = None if callable(target) else target
        self.handle = target if callable(target) else (lambda msg: dispatch(self.s, msg))
        self.t = 1000
        self.seq = 0
        self.committed = ""

    def send(self, op, key=None, mods=None, *, step=30, **extra):
        self.t += step
        self.seq += 1
        msg = {"op": op, "t": self.t, "seq": self.seq, **extra}
        if key is not None:
            msg["vk"] = ord(key) if isinstance(key, str) else key
        if mods is not None:
            msg["mods"] = mods
        reply = self.handle(msg)
        self.committed += reply["commit"]
        return reply

    def down(self, key, mods=None, **extra):
        return self.send("down", key, mods, **extra)

    def up(self, key, mods=None):
        return self.send("up", key, mods)

    def tap(self, key, mods=None, **extra):
        """Down and up; the reply after the release, with both events' commits."""
        commit = self.down(key, mods, **extra)["commit"]
        reply = self.up(key, mods)
        return {**reply, "commit": commit + reply["commit"]}

    def press(self, key, mods=None, *, step=100):
        """Down and up; the reply after the down (what the key did), with both
        events' commits."""
        reply = self.send("down", key, mods, step=step)
        commit = self.up(key, mods)["commit"]
        return {**reply, "commit": reply["commit"] + commit}

    def commit(self):
        """Enter; the request number of the reply that carries the commit."""
        self.down(VK_RETURN)
        return self.seq

    def idle(self):
        """Let a pending chord's timer run out."""
        self.t += 300
        return self.send("timeout", step=0)

    def ctrl_down(self):
        return self.press(VK_DOWN, ["ctrl"])

    def convert(self):
        self.send("down", VK_SPACE, step=200)
        return self.send("up", VK_SPACE)

    def plain(self, letter):
        self.send("down", letter.upper(), step=200)
        return self.send("up", letter.upper())

    def chords(self, *letters):
        """One Space press with these keys typed inside it (turn 1, 2, ...)."""
        self.send("down", VK_SPACE, step=200)
        for letter in letters:
            self.send("down", letter.upper(), step=20)
            self.send("up", letter.upper(), step=40)
        return self.send("up", VK_SPACE, step=20)

    def shift(self, letter):
        return self.tap(letter, ["shift"])

    def letters(self, text):
        for ch in text:
            reply = self.tap(ch.upper(), [])
        return reply
