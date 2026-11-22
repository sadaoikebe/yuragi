"""Markdown tables (key x state) from table.py results, for docs/keybind/macos-table.md.

    python3 report.py out/table-default.jsonl out/table-windows.jsonl out/table-live.jsonl > ../../../docs/keybind/macos-table.md

Cell notation (explained at the top of the output): see LEGEND.
"""
import json
import sys

from analyze import comp

GROUPS = [
    ("未入力・入力中", ["empty", "composing", "comp_cursor", "pred_focus", "after_commit", "abc"]),
    ("変換中", ["converted", "cand", "multi", "multi_second", "resized"]),
    ("ライブ変換", ["live", "live_cursor", "live_space", "live_cand"]),
]
NAMES = {
    "empty": "① 未入力", "composing": "② 入力中", "comp_cursor": "②' カーソル途中", "pred_focus": "予測選択",
    "after_commit": "確定直後", "abc": "英字（ABC）", "converted": "③ 変換（1 文節）", "cand": "④ 候補窓",
    "multi": "③ 複数文節", "multi_second": "③ 2 番目の文節", "resized": "⑤ 文節を縮めた",
    "live": "ライブ: 入力中", "live_cursor": "ライブ: ← ← 後", "live_space": "ライブ: Space 後", "live_cand": "ライブ: 候補窓",
}
PREP = {
    "empty": "（ひらがな、何も打たない）", "composing": "`kanji`（かんじ。予測候補の窓が出ている）",
    "comp_cursor": "`kanji` ←", "pred_focus": "`kanji` Tab（予測候補「感情」を選んでいる）",
    "after_commit": "`kanji` Space Return（「感じ」を確定した直後）", "abc": "（入力ソース ABC）",
    "converted": "`kanji` Space（「感じ」）", "cand": "`kanji` Space Space（候補窓で「漢字」）",
    "multi": "`kyouhaamedesu` Space（「今日は／雨です」の先頭）", "multi_second": "同 →（「雨です」に注目）",
    "resized": "同 Shift+←（「今日／は／雨です」）",
    "live": "ライブ変換オンで `kyouhaamedesu`", "live_cursor": "同 ← ←（← で文節を選ぶ状態に入る）", "live_space": "同 Space",
    "live_cand": "同 Space Space",
}
LEGEND = """\
| 書き方 | 意味 |
|---|---|
| `通す:moveLeft` | IME は食べず、アプリにコマンド（`doCommand(by:)` のセレクタ）か文字が届いた |
| `確定「感じ」` | 「感じ」を確定し、キーは食べた（確定した文字が表示と違うときもある） |
| `確定「感じ」→通す:…` | 確定してから、キーをアプリに通した |
| `確定「感じ」 →あ` | 確定してから、キーで次の入力を始めた |
| `–` | 食べて、何も変わらなかった |
| `か^んじ` | 入力中の文字。`^` はカーソル（末尾にあるときは書かない） |
| `*今日／雨です` | 変換中。`／` は文節の区切り、`*` は注目文節 |
| `+窓` / `-窓` | 候補（予測候補）の窓が開いた / 閉じた |
| `→英字` / `→ひらがな` | 入力ソースが変わった |
| `(空)` | 入力中の文字が無くなった（取り消し） |
"""


def lit(x):
    names = {"\u3000": "全角空白", " ": "空白", "\xa0": "NBSP"}
    return names.get(x) or (repr(x)[1:-1] if any(ord(c) < 32 for c in x) else x)


def cell(r):
    if r is None:
        return ""
    b, a, ev = r["before"], r["after"], r["events"]
    ins = [e[4:] for e in ev if e.startswith("ins:")]
    cmds = [e[4:].rstrip(":") for e in ev if e.startswith("cmd:")]
    bc, ac = comp(b), comp(a)
    committed = a["text"][len(b["text"]):]
    out = []
    if bc and ins and ins[0] and committed.startswith(ins[0]):
        rest = committed[len(ins[0]):]
        extra = cmds + ([lit(rest)] if rest else [])
        out.append(f"確定「{lit(ins[0])}」" + ("→通す:" + ",".join(extra) if extra else ""))
        if ac:
            out.append("→" + ac.replace("|", "／"))
    else:
        if cmds or (ins and not bc):
            out.append("通す:" + ",".join(cmds + [lit(x) for x in ins]))
        if ac != bc:
            out.append(ac.replace("|", "／") if ac else "(空)")
    if a["source"] != b["source"]:
        out.append("→英字" if a["source"] == "ABC" else "→ひらがな")
    if bool(a["panels"]) != bool(b["panels"]) and ac:
        out.append("+窓" if a["panels"] else "-窓")
    s = " ".join(out) or "–"
    return "`" + s.replace("`", "ˋ") + "`" if s != "–" else s


def load(path):
    by = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        by[(r["state"], r["name"])] = r  # the last (redone) row wins
    return by


def table(by, states, keys, base=None):
    print("| キー | " + " | ".join(NAMES[s] for s in states) + " |")
    print("|---|" + "---|" * len(states))
    for k in keys:
        cells = []
        for s in states:
            c = cell(by.get((s, k)))
            if base is not None:
                c = c if c != cell(base.get((s, k))) else ""
            cells.append(c)
        if base is not None and not any(cells):
            continue
        print(f"| {k} | " + " | ".join(cells) + " |")


def main():
    default = load(sys.argv[1])
    every = set()
    for path in sys.argv[1:]:
        every |= {st for st, _ in load(path)}
    keys = list(dict.fromkeys(k for _, k in default))
    print("# macOS 日本語入力プログラムの状態 × キーの表（実機）\n")
    print("[macos.md](macos.md) §10 の元データ。`tools/keyprobe/mac/report.py` で作った（手で直さない）。"
          "採り方は [tools/keyprobe/mac/README.md](../../tools/keyprobe/mac/README.md)。\n")
    print("- 環境: MacBook Air (M1)、macOS 27.2.1、US 配列、入力ソース「日本語 - ローマ字入力」。2026-11-22。"
          "キーは試験アプリの中で合成した（システムが先に取るキーは届かない。Control＋Space など）。")
    print("- 設定: ライブ変換オフ、推測候補表示オン、タイプミス修正オン、学習なし（プライベートモード）。")
    print("- **制御文字の確定**（`確定「\\x01」` など）は合成したキーでの結果。Home・End・Control＋Q などで入力を捨てて制御文字を確定した。"
          "本物のキーで同じになるかは確かめていない（[macos.md](macos.md) §10.8）。\n")
    print("**状態の作り方**\n")
    print("| 状態 | 作り方 |\n|---|---|")
    for s, p in PREP.items():
        if s not in every:
            continue
        print(f"| {NAMES[s]} | {p} |")
    print("\n**書き方**\n")
    print(LEGEND)
    for title, states in GROUPS:
        states = [s for s in states if any((s, k) in default for k in keys)]
        if not states:
            continue
        print(f"## 既定の設定: {title}\n")
        table(default, states, keys)
        print()
    if len(sys.argv) > 3:
        live = load(sys.argv[3])
        print("## ライブ変換をオンにしたとき\n")
        print("ライブ変換の文字列には注目文節の太い下線が無いので、`*` は付かない。\n")
        table(live, [s for s in GROUPS[2][1] if any((s, k) in live for k in keys)], keys)
        print()
    if len(sys.argv) > 2:
        win = load(sys.argv[2])
        print("## 「Windows風のキー操作」をオンにしたとき（既定と違うところだけ）\n")
        print("Mac から Windows に移る人が使う設定ではない。Apple が「Windows 風」として、どのキーを MS-IME 風に置き換えたかの記録として残す。"
              "空欄は既定と同じ。\n")
        for title, states in GROUPS:
            states = [s for s in states if any((s, k) in win for k in keys)]
            if states:
                print(f"### {title}\n")
                table(win, states, keys, base=default)
                print()


if __name__ == "__main__":
    main()
