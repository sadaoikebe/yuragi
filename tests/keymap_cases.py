"""Compare the compiled TIP's decisions with actual engine key replies."""

import subprocess
import sys
from unittest.mock import patch

from yuragi.chord.fsm import Plain
from yuragi.chord.keys import ALT_VKS
from yuragi.ime.bunsetsu import Candidate
from yuragi.ime.server import dispatch
from yuragi.ime.session import ImeSession
from yuragi.lattice.mozc_dict import MozcLex
from yuragi.lattice.table import load_table
from tests import support  # noqa: F401 (Mozc の品詞名)


def key_cases():
    lex = MozcLex({}, set(), [0] * 4, 2)
    table = load_table()
    for phase in ("direct", "empty", "composing", "converting", "selecting",
                  "resizing", "predicting", "editing"):
        for flags in range(16):
            mods = [m for i, m in enumerate(("shift", "ctrl", "alt", "win")) if flags & (1 << i)]
            for vk in range(1, 0x100):
                session = ImeSession(_table=table, _lex=lex, direct=phase == "direct")
                if phase not in ("empty", "direct"):
                    count = 2 if phase in ("composing", "converting", "resizing", "editing") else 1
                    session._ingest([Plain("k")] * count)
                if phase == "composing":
                    # A phase-only TIP table must reserve Ctrl+Delete because a
                    # caret inside the input requires a commit before replay.
                    dispatch(session, {"op": "down", "vk": 0x25})
                if phase in ("converting", "selecting", "resizing", "editing"):
                    dispatch(session, {"op": "down", "vk": 0x20, "mods": ["shift"]})
                    if phase == "selecting":  # the second press opens the window
                        dispatch(session, {"op": "down", "vk": 0x20, "mods": ["shift"]})
                    if phase in ("converting", "resizing", "editing"):
                        dispatch(session, {"op": "down", "vk": 0x25, "mods": ["shift"]})
                    if phase in ("converting", "editing"):
                        dispatch(session, {"op": "down", "vk": 0x20, "mods": ["shift"]})
                    if phase == "editing":
                        dispatch(session, {"op": "down", "vk": 0x1B})
                if phase == "predicting":
                    with patch("yuragi.ime.session.predict", return_value=[
                            Candidate("キーワード", "きーわーど", 0, 1, 1, "predict")]):
                        dispatch(session, {"op": "down", "vk": 9})
                assert session.phase == phase
                reply = dispatch(session, {"op": "down", "vk": vk, "mods": mods, "t": 100})
                # A key which commits before passing must still be sent. Alt
                # alone is observed out of band, so WantKey always passes it.
                # A phase-specific TIP command needs to reach the engine to
                # resolve it. A plain global fallback can run in the TIP.
                chord = session.keyboard.chord(vk, flags)
                scoped_global = "global" in reply and chord in session.keymap._rows[phase]
                send = vk not in ALT_VKS and (reply["eat"] or bool(reply["commit"]) or scoped_global)
                yield f"{phase} {vk} {flags} {int(send)}\n"


if __name__ == "__main__":
    cases = "".join(key_cases())
    subprocess.run([sys.argv[1], "--key-cases"], input=cases, text=True, check=True)
