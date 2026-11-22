"""One line per key from probe's JSON lines: what the input method did with it.

    out/probe app <input-source-id> "<keys>" | python3 summary.py

marked<*今日は|雨です>  the composition; | separates clauses, * marks the focused one (thick underline)
insert<...>             committed text (or a character that passed through)
cmd<...>                a command the input method left to the app (the key was not eaten)
source<...>             the input source changed
=> text<...> src=... panels=N   after the key: committed text, the input source, and how many other
                        windows the probe process has (candidate window, input source indicator)
"""
import json
import sys

for line in sys.stdin:
    if not line.startswith("{"):
        print("  !!", line.strip()[:150])
        continue
    r = json.loads(line)
    ev = r["ev"]
    if ev == "press":
        print(f"\n[{r['key']}]", end=" ")
    elif ev == "setMarkedText":
        segs = "|".join(("*" if s.get("NSUnderline") == 2 else "") + s["s"] for s in r["segs"])
        print(f"marked<{segs}> sel={r['sel']}", end=" ")
    elif ev == "insertText":
        print(f"insert<{r['s']}>", end=" ")
    elif ev == "doCommand":
        print(f"cmd<{r['sel']}>", end=" ")
    elif ev == "keyDown":
        print(f"handled={r['handled']}", end=" ")
    elif ev == "source":
        print(f"source<{r['id'].split('.')[-1]}>", end=" ")
    elif ev == "after":
        own = [f"{w['class']}:{w['frame']}" for w in r["own"]]
        print(f"=> text<{r['text']}> src={r['source'].split('.')[-1]} panels={len(own)}", end="")
    else:
        print("\n", {k: v for k, v in r.items() if k != "sources"})
print()
