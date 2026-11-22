"""Keys a person has to press (system keys, holding a key, a real modifier tap).

    python3 guide.py <tag> [step-id ...]

The probe window sets each state up by itself, beeps and shows what to press (in red). Press it, then
wait: the step ends 0.3 s after the key is released (4 s if nothing arrives; the run stops if the first step gets no key). Appends to out/guide-<tag>.jsonl.
`real` in each record is the key events the app saw from the keyboard (down / up / flags, repeat).
"""
import json
import os
import subprocess
import sys

from table import ABC, J, OUT, show

STEPS = [
    ("delete_pred", J, "kanji {Tab}", "Delete（⌫）を 1 回押す"),
    ("space_hold", J, "kanji", "Space を 2 秒押し続けて離す"),
    ("globe_comp", J, "kanji", "地球儀キー（fn）を 1 回押す"),
    ("shift_tap_comp", J, "kanji", "Shift だけを 1 回押して離す"),
    ("home_pred", J, "kanji {Tab}", "fn＋←（Home）を 1 回押す"),
    ("ctrl_q_comp", J, "kanji", "Control＋Q を 1 回押す"),
]


def main():
    tag, only = sys.argv[1], sys.argv[2:]
    steps = [{"id": i, "source": s, "prep": p, "say": say} for i, s, p, say in STEPS if not only or i in only]
    path = os.path.join(OUT, f"guide-steps-{tag}.json")
    with open(path, "w") as f:
        json.dump(steps, f, ensure_ascii=False)
    p = subprocess.Popen([os.path.join(OUT, "probe"), "guide", path], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    with open(os.path.join(OUT, f"guide-{tag}.jsonl"), "a", encoding="utf-8") as f:
        for line in p.stdout:
            if not line.startswith("{") or '"say"' not in line:
                continue
            r = json.loads(line)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            real = " ".join(f"{e['type']}:{e['code']}{'r' if e['repeat'] else ''}" for e in r["real"])
            print(f"{r['id']:18} {show(r['before'])} -> {show(r['after'])} {','.join(r['events'])} "
                  f"kept={r['kept']!r} real=[{real}]", flush=True)
    p.wait()


if __name__ == "__main__":
    main()
