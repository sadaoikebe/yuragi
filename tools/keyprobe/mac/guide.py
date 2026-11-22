"""Keys a person has to press (system keys, holding a key, a real modifier tap).

    python3 guide.py <tag> [step-id ...]
    python3 guide.py <tag> globe-caps      (the globe key and Caps Lock, GLOBE_CAPS)
    python3 guide.py <tag> globe           (the globe key in detail, GLOBE)
    PROBE_BUNDLE=1 python3 guide.py ...    run out/KeyProbe.app through `open` (an ordinary app) instead of out/probe

The probe window sets each state up by itself, beeps and shows what to press (in red). Press it, then
wait: the step ends 0.3 s after the key is released (8 s for the first step and 4 s afterwards if nothing arrives; the run stops if the first step gets no key). Appends to out/guide-<tag>.jsonl.
`real` in each record is the key events the app saw from the keyboard (down / up / flags, repeat).
"""
import json
import os
import subprocess
import sys

from table import ABC, J, OUT, show

KO = "com.apple.inputmethod.Korean.2SetKorean"
ZH = "com.apple.inputmethod.SCIM.ITABC"

STEPS = [
    ("delete_pred", J, "kanji {Tab}", "Delete（⌫）を 1 回押す"),
    ("space_hold", J, "kanji", "Space を 2 秒押し続けて離す"),
    ("globe_comp", J, "kanji", "地球儀キー（fn）を 1 回押す"),
    ("shift_tap_comp", J, "kanji", "Shift だけを 1 回押して離す"),
    ("home_pred", J, "kanji {Tab}", "fn＋←（Home）を 1 回押す"),
    ("ctrl_q_comp", J, "kanji", "Control＋Q を 1 回押す"),
]

# globe key and Caps Lock: (id, source, prep, say, extra fields: settle = seconds to wait after the key,
# until_caps_off = the step ends when Caps Lock is turned off again, pre_source = select this input source first,
# so that it is the "previous" one)
GLOBE_CAPS = [
    ("check", J, "kanji", "Space を 1 回押す（確認）", {}),
    ("globe_once", J, "", "地球儀キー（fn）を 1 回押す", {"settle": 2.0, "pre_source": ABC}),
    ("globe_twice", J, "", "地球儀キー（fn）を 2 回続けて押す", {"settle": 2.0, "pre_source": ABC}),
    ("caps_type", J, "", "Caps Lock → A → I → Caps Lock（消す）の順に押す", {"until_caps_off": True}),
    ("caps_type_comp", J, "kanji", "Caps Lock → A → I → Caps Lock（消す）の順に押す", {"until_caps_off": True}),
]

# the globe key, in detail: (id, source, prep, say, extra). pre_sources are selected in order before `source`.
GLOBE = [
    ("check", J, "kanji", "Space を 1 回押す（確認）", {}),
    ("g1_abc_j", J, "", "地球儀キーを 1 回押す", {"pre_sources": [ABC], "presses": 1, "settle": 1.2}),
    ("g1_ko_j", J, "", "地球儀キーを 1 回押す", {"pre_sources": [KO], "presses": 1, "settle": 1.2}),
    ("g1_zh_j", J, "", "地球儀キーを 1 回押す", {"pre_sources": [ZH], "presses": 1, "settle": 1.2}),
    ("g1_j_j", J, "", "地球儀キーを 1 回押す", {"pre_sources": [J], "presses": 1, "settle": 1.2}),
    ("g1_ko_j_again", J, "", "地球儀キーを 1 回押す", {"pre_sources": [KO], "presses": 1, "settle": 1.2}),
    ("g1_j_abc", ABC, "", "地球儀キーを 1 回押す", {"pre_sources": [J], "presses": 1, "settle": 1.2}),
    ("g1_ko_abc", ABC, "", "地球儀キーを 1 回押す", {"pre_sources": [KO], "presses": 1, "settle": 1.2}),
    ("g2_fast_ko_j", J, "", "地球儀キーをすばやく 2 回押す", {"pre_sources": [KO], "presses": 2, "settle": 1.2}),
    ("g2_slow_ko_j", J, "", "地球儀キーを 1 回押し、1 秒待って、もう 1 回押す", {"pre_sources": [KO], "presses": 2, "settle": 1.2}),
    ("g3_fast_abc_j", J, "", "地球儀キーをすばやく 3 回押す", {"pre_sources": [ABC], "presses": 3, "settle": 1.2}),
    ("ghold_abc_j", J, "", "地球儀キーを 1 秒押し続けて離す", {"pre_sources": [ABC], "presses": 1, "settle": 1.2}),
    ("g1_comp_abc_j", J, "kanji", "地球儀キーを 1 回押す（入力中）", {"pre_sources": [ABC], "presses": 1, "settle": 1.2}),
]


def main():
    tag, only = sys.argv[1], sys.argv[2:]
    if only == ["globe"]:
        steps = [{"id": i, "source": s, "prep": p, "say": say, **extra} for i, s, p, say, extra in GLOBE]
    elif only == ["globe-caps"]:
        steps = [{"id": i, "source": s, "prep": p, "say": say, **extra} for i, s, p, say, extra in GLOBE_CAPS]
    else:
        steps = [{"id": i, "source": s, "prep": p, "say": say} for i, s, p, say in STEPS if not only or i in only]
    path = os.path.join(OUT, f"guide-steps-{tag}.json")
    with open(path, "w") as f:
        json.dump(steps, f, ensure_ascii=False)
    if os.environ.get("PROBE_BUNDLE"):
        # as an ordinary app: out/KeyProbe.app started by LaunchServices (`open`); its output goes to a file
        res = os.path.join(OUT, f"guide-bundle-{tag}.out")
        subprocess.run(["open", "-W", "-n", "--stdout", res, "--stderr", "/dev/null",
                        os.path.join(OUT, "KeyProbe.app"), "--args", "guide", path])
        lines = open(res, encoding="utf-8")
    else:
        p = subprocess.Popen([os.path.join(OUT, "probe"), "guide", path], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        lines = p.stdout
    with open(os.path.join(OUT, f"guide-{tag}.jsonl"), "a", encoding="utf-8") as f:
        for line in lines:
            if not line.startswith("{") or '"say"' not in line:
                continue
            r = json.loads(line)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            f.flush()
            real = " ".join(f"{e['type']}:{e['code']}{'r' if e['repeat'] else ''}" for e in r["real"])
            post = f" | post -> {show(r['post_after'])} {','.join(r['post_events'])}" if "post_after" in r else ""
            print(f"{r['id']:18} {show(r['before'])} -> {show(r['after'])} {','.join(r['events'])} "
                  f"kept={r['kept']!r} caps={r['after'].get('caps')} sys={r['after'].get('sysSource')} tv={r.get('tvSource')} real=[{real}]{post}", flush=True)
    if not os.environ.get("PROBE_BUNDLE"):
        p.wait()


if __name__ == "__main__":
    main()
