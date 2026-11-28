"""One recording session with the probe: select it, wait while a person types, go back to ABC, print the log.

    python3 session.py [--mark] [--tap] [--eat-modes] [--chars] [--quiet 8] [--max 180] [--commits Terminal,Safari]
    python3 session.py --show          print the log as it is, select nothing

--mark       letters become marked text, Return commits (what each app answers is logged)
--tap        ask for Input Monitoring and log the event tap (key up, real time, keyboard type)
--eat-modes  the probe eats Eisu / Kana
--chars      log the typed characters too
--quiet N    stop N seconds after the last logged event (once something was logged)
--commits    with --mark: stop 2 seconds after each named app committed twice
The probe is never stopped here, and the log is only appended to: see README (注意).
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.expanduser("~/Library/Logs/yuragi-probe")
LOG = os.path.join(DIR, "imk.jsonl")
ID = "io.github.yuragi.inputmethod.YuragiProbe.Japanese"
FLAGS = {"mark": "mark", "tap": "request-tap", "eat_modes": "eat-modes", "chars": "chars"}


def rows(start=0):
    out = []
    try:
        with open(LOG, encoding="utf-8") as f:
            for line in list(f)[start:]:
                try:
                    out.append(json.loads(line.strip("\0\n")))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def ctl(*a):
    subprocess.run([os.path.join(HERE, "out", "ctl"), *a], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def show(rs):
    repeats = 0
    for r in rs:
        ev = r["ev"]
        if ev in ("handle", "tap"):
            if r.get("repeat"):
                repeats += 1
                continue
            if repeats:
                print(f"       ... {repeats} repeats")
                repeats = 0
            kind = {10: "down", 11: "up", 12: "mods"}.get(r["type"], r["type"])
            line = f"{ev:6} {kind:4} code {r['code']:3} kb {r.get('kbtype', '-'):>3} t {r['t']:.4f}"
            if ev == "tap":
                line += f" srcpid {r.get('srcpid')}"
            else:
                line += f" handled {r['handled']}"
                if "chars" in r:
                    line += f" chars {r['chars']!r}"
            c = r.get("client")
            if c:
                marked = [x if x < 1e18 else "-" for x in c["marked"]]
                line += (f" | {c['app']} sel {c['sel']} marked {marked} len {c['length']} leftLen {c.get('leftLen')}"
                         f" leftOK {c.get('leftEndsWithCommitted')} rect {[round(x) for x in c['rect']]}"
                         f" valid {','.join(sorted(a.replace('NS', '') for a in c['validAttrs']))}")
            print(line)
        else:
            if repeats:
                print(f"       ... {repeats} repeats")
                repeats = 0
            print("  ", {k: v for k, v in r.items() if k not in ("now", "path", "bundle")})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in FLAGS:
        ap.add_argument("--" + name.replace("_", "-"), action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--quiet", type=float, default=8)
    ap.add_argument("--max", type=float, default=180)
    ap.add_argument("--commits", default="")
    a = ap.parse_args()
    if a.show:
        show(rows())
        return
    os.makedirs(DIR, exist_ok=True)
    start = len(rows())
    for name, file in FLAGS.items():
        path = os.path.join(DIR, file)
        if getattr(a, name):
            open(path, "w").close()
        elif os.path.exists(path):
            os.remove(path)
    apps = [x for x in a.commits.split(",") if x]
    ctl("select", ID)
    t0 = time.time()
    try:
        while True:
            time.sleep(0.5)
            rs = rows(start)
            keys = [r for r in rs if r["ev"] in ("handle", "tap")]
            idle = time.time() - os.path.getmtime(LOG) if os.path.exists(LOG) else 0
            if apps:
                done = all(sum(1 for r in keys if r.get("client") and r["code"] == 36 and app in r["client"]["app"]) >= 2
                           for app in apps)
                if done and idle > 2:
                    break
            elif keys and idle > a.quiet:
                break
            if not keys and time.time() - t0 > 60:
                print("ABORT: nothing arrived in 60 s", file=sys.stderr)
                break
            if time.time() - t0 > a.max:
                print(f"stopped at {a.max:.0f} s", file=sys.stderr)
                break
    finally:
        ctl("select", "com.apple.keylayout.ABC")
        for file in FLAGS.values():
            path = os.path.join(DIR, file)
            if os.path.exists(path):
                os.remove(path)
    show(rows(start))


if __name__ == "__main__":
    main()
