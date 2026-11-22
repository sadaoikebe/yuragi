"""Tk window for the key probe (tools/keyprobe/README.md): records every key event Tk receives.

    python target_tk.py <title> <log path> [--menu]

Each line of the log is JSON: {"t": ms, "ev": "down"|"up"|"menu", ...}.
"""
import json
import sys
import time
import tkinter as tk


def main():
    title, path = sys.argv[1], sys.argv[2]
    with_menu = "--menu" in sys.argv[3:]
    out = open(path, "a", encoding="utf-8", buffering=1)

    def log(**kw):
        kw["t"] = int(time.monotonic() * 1000)
        out.write(json.dumps(kw, ensure_ascii=False) + "\n")

    root = tk.Tk()
    root.title(title)
    root.geometry("520x260+120+120")
    if with_menu:
        bar = tk.Menu(root)
        file_menu = tk.Menu(bar, tearoff=0, postcommand=lambda: log(ev="menu"))
        file_menu.add_command(label="Nothing")
        bar.add_cascade(label="File", underline=0, menu=file_menu)
        root.config(menu=bar)
    text = tk.Text(root)
    text.pack(fill="both", expand=True)
    for seq, ev in (("<KeyPress>", "down"), ("<KeyRelease>", "up")):
        root.bind_all(seq, lambda e, ev=ev: log(ev=ev, keysym=e.keysym, keycode=e.keycode, state=e.state))
    text.focus_set()
    root.after(100, lambda: log(ev="ready"))
    root.mainloop()


if __name__ == "__main__":
    main()
