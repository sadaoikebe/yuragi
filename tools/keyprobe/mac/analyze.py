"""Print a table.py result as key x state, one short verdict per cell.

    python3 analyze.py out/table-<tag>.jsonl [state ...]

Verdicts:
  pass:<cmd>        the input method did not eat the key; the app got the command (or the character)
  commit>pass:<..>  the composition was committed, then the key went to the app
  commit            the composition was committed and the key was eaten
  =                 eaten, nothing changed
  <after>           eaten, the composition became <after> (| clause boundary, * focused clause,
                    ^ cursor while composing, W a candidate/prediction window is open)
  @<source>         the input source changed
  unhandled         handleEvent returned false: neither the input method nor the key bindings took it
Also checks that every case of a state started from the same composition (before).
"""
import collections
import json
import sys


def comp(s):
    segs = s["segs"]
    if not segs:
        return ""
    if len(segs) == 1 and s["sel"][1] == 0:  # composing: show the cursor
        t = segs[0][0]
        c = s["sel"][0]
        return t[:c] + "^" + t[c:] if c < len(t) else t
    return "|".join(("*" if u == 2 else "") + t for t, u in segs)


def verdict(r):
    b, a, ev = r["before"], r["after"], r["events"]
    ins = [e[4:] for e in ev if e.startswith("ins:")]
    cmds = [e[4:].rstrip(":") for e in ev if e.startswith("cmd:")]
    out = []
    bc, ac = comp(b), comp(a)
    committed = a["text"][len(b["text"]):]
    if bc and ins and committed.startswith(ins[0]) and ins[0] and not ac:
        out.append("commit")
        rest = committed[len(ins[0]):]
        if cmds or rest:
            out[-1] = "commit>pass:" + ",".join(cmds + ([repr(rest)] if rest else []))
    elif cmds or (ins and not bc):
        out.append("pass:" + ",".join(cmds + [repr(x) for x in ins]))
    if ac != bc and not (out and out[0].startswith("commit") and not ac):
        out.append(ac or "(empty)")
    if a["source"] != b["source"]:
        out.append("@" + a["source"])
    if bool(a["panels"]) != bool(b["panels"]) and ac:
        out.append("W" if a["panels"] else "noW")
    if "unhandled" in ev:
        out.append("unhandled")
    if not a["front"]:
        out.append("!front")
    return " ".join(out) or "="


def main():
    rows = [json.loads(x) for x in open(sys.argv[1], encoding="utf-8")]
    states = sys.argv[2:] or list(dict.fromkeys(r["state"] for r in rows))
    by = {(r["state"], r["name"]): r for r in rows}
    keys = list(dict.fromkeys(r["name"] for r in rows))
    for st in states:
        befores = collections.Counter((comp(r["before"]), r["before"]["text"], bool(r["before"]["panels"]))
                                      for r in rows if r["state"] == st)
        print(f"# {st}: before = {befores.most_common(3)}")
    for st in states:
        print(f"\n## {st}")
        common = collections.Counter((comp(r["before"]), r["before"]["text"]) for r in rows if r["state"] == st).most_common(1)[0][0]
        for k in keys:
            r = by.get((st, k))
            if not r:
                continue
            odd = "" if (comp(r["before"]), r["before"]["text"]) == common else f"   [before differs: {comp(r['before'])!r}]"
            print(f"{k:18} {verdict(r)}  kept={r['kept']!r}{odd}")


if __name__ == "__main__":
    main()
