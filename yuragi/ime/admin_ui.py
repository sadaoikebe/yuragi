"""The management window: word registration, learning, settings, keys, status.

  python -m yuragi.ime.admin_ui [--runtime-dir DIR] [--dict-dir DIR]

--dict-dir is the dictionary the engine was given (the installer's shared copy).

A thin shell over personal, learning_admin and config, on the same files the
engine uses. AdminModel holds everything the
window does and imports no tkinter, so it is tested without a display;
AdminWindow only lays out widgets and forwards to it.

Everything the window shows is Japanese: setting names, values, descriptions,
status and messages come from the tables here.

Word and learning changes reach a running engine at its next conversion or
keystroke; settings are read when the engine starts (状態タブ: 変換エンジンを再起動).
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
from datetime import datetime
import hashlib
import io
import os
from pathlib import Path
import sys

from . import broker_client, config, keymap, learning_admin, personal
from .keymap_ui import KeyTab
from .learning import LearningStore

POS_NAMES = list(personal.POS_NAMES)
RESTART_NOTE = "変換エンジンを再起動すると反映されます（「状態」タブ）。"
# The product icon (assets/icon/THEME.md). The installed app is the source tree,
# so the same relative place holds there too.
ICON = Path(__file__).resolve().parents[2] / "assets" / "icon" / "yuragi.ico"


@dataclass(frozen=True)
class Outcome:
    """What an action did, for the status line; ok=False is shown as an error."""
    ok: bool
    message: str


@dataclass(frozen=True)
class SettingText:
    label: str
    help: str
    values: dict  # value in config.json -> shown


# The settings config.json holds, in the order the window lists them.
SETTINGS: dict[str, SettingText] = {
    "learning": SettingText(
        "学習", "確定した変換を覚えて、次から先頭に出します。",
        {"on": "学習する", "off": "使わない"}),
    "prediction": SettingText(
        "入力の予測", "学習した内容と辞書から続きの候補を出します。"
        "自動表示した候補は Tab キーで選べます。",
        {"auto": "自動で出す", "tab": "Tab キーで出す", "off": "使わない"}),
    "lm_rescore": SettingText(
        "言語モデル", "変換するとき、言語モデル（zenz-v2.5）が読みと直前に確定した文から"
        "変換の結果を選びます。使わないときは、辞書だけで変換します。",
        {True: "使う", False: "使わない"}),
    "keyboard": SettingText(
        "キーボード", "親指シフトキーボードを使うときに選びます。US キーボードでは使いません。",
        {"auto": "Windows の設定に従う", "kb232": "富士通 FMV-KB232"}),
    "space_thumb": SettingText(
        "スペースバーの親指", "スペースバーを押す親指を決めます。US キーボードでは使いません。",
        {"auto": "ゆらぎ（自動）", "right": "右親指", "left": "左親指"}),
}

LEARNING_STATES = {"on": "学習中", "off": "使わない設定"}
ENGINE_STATES = {"ready": "動作中", "starting": "起動中", "down": "停止中"}
WARNINGS = {
    "lm": "言語モデルを使えません（辞書だけで変換しています）",
    "keymap": "キー設定を読み込めませんでした（「キー」タブを確認してください）",
}
STOP_REASONS = {
    "exited": "変換エンジンが繰り返し止まった（理由は記録のフォルダの engine.log）",
    "hang": "変換エンジンが反応しなくなった",
}


@dataclass(frozen=True)
class SettingRow:
    name: str  # the key in config.json
    label: str
    value: str  # as shown, with （既定） when nothing is stored
    edit: str  # what the list starts with
    choices: list[str]  # shown values to offer
    help: str


class AdminModel:
    """The window's behaviour, on the engine's files; every change re-reads them."""

    def __init__(self, runtime_dir: Path | None = None):
        self.runtime_dir = runtime_dir or config.DEFAULT_RUNTIME_DIR
        self.config_file = self.runtime_dir / config.CONFIG_NAME
        # The engine's files (yuragi.engine: --data-dir).
        self.personal_file = self.runtime_dir / "personal_lexicon.jsonl"
        self.learning_file = self.runtime_dir / "learning.jsonl"

    # -- word registration (personal lexicon) --------------------------------

    def words(self) -> list[personal.Word]:
        return personal.read_words(self.personal_file)

    def add_word(self, reading: str, surface: str, pos: str = "名詞",
                 cost: str = "") -> Outcome:
        reading, surface, cost = reading.strip(), surface.strip(), cost.strip()
        try:
            cost_value = int(cost) if cost else personal.DEFAULT_COST
        except ValueError:
            return Outcome(False, f"コストは整数で入力してください（「{cost}」は使えません）")
        try:
            word = personal.add_word(self.personal_file, reading, surface, pos, cost_value)
        except ValueError as exc:
            return Outcome(False, str(exc))
        return Outcome(True, f"登録しました: {word.reading} → {word.surface}"
                             f"（{word.pos}、コスト {word.cost}）")

    def remove_word(self, reading: str, surface: str) -> Outcome:
        if not personal.remove_word(self.personal_file, reading, surface):
            return Outcome(False, f"登録されていません: {reading} → {surface}")
        return Outcome(True, f"削除しました: {reading} → {surface}")

    # -- learning --------------------------------------------------------------

    def _values(self) -> dict:
        """The settings the engine would use (a broken file: its note is the engine's)."""
        with contextlib.redirect_stderr(io.StringIO()):
            return config.load(self.config_file)

    def learning_state(self) -> str:
        return self._values()["learning"]

    def learning_store(self) -> LearningStore | None:
        """The history read once: what one refresh of the window shows comes from it."""
        return LearningStore(self.learning_file) if self.learning_file.exists() else None

    def learned(self, query: str = "", store: LearningStore | None = None
                ) -> list[learning_admin.LearnedPair]:
        if store is None and (store := self.learning_store()) is None:
            return []
        query = query.strip()
        return [p for p in learning_admin.pairs(store) if query in p.reading or query in p.surface]

    @staticmethod
    def learned_row(pair: learning_admin.LearnedPair) -> tuple[str, str, str, str]:
        """reading, surface, last confirmed, ○ if learned from kana as a word."""
        when = datetime.fromtimestamp(pair.last).strftime("%Y-%m-%d %H:%M")
        return (pair.reading, pair.surface, when, "○" if pair.user_word else "")

    def learning_counts(self, store: LearningStore | None = None) -> str:
        pairs = self.learned(store=store)
        words = sum(p.user_word for p in pairs)
        return (f"学習: {LEARNING_STATES[self.learning_state()]} ・ 学習した変換 {len(pairs)} 件"
                f"（うち単語として覚えたもの {words} 件） ・ 登録した単語 {len(self.words())} 件")

    def forget(self, reading: str, surface: str) -> Outcome:
        if not self.learning_file.exists():
            return Outcome(False, "学習履歴がまだありません")
        if not learning_admin.forget(self.learning_file, reading, surface):
            return Outcome(False, f"学習していません: {reading} → {surface}")
        return Outcome(True, f"忘れました: {reading} → {surface}")

    def promote(self, reading: str, surface: str, pos: str = "名詞") -> Outcome:
        if not self.learning_file.exists():
            return Outcome(False, "学習履歴がまだありません")
        try:
            word = learning_admin.promote(self.learning_file, self.personal_file,
                                          reading, surface, pos)
        except ValueError as exc:
            return Outcome(False, str(exc))
        if word is None:
            return Outcome(False, f"学習していません: {reading} → {surface}")
        return Outcome(True, f"単語登録しました: {word.reading} → {word.surface}（{word.pos}）。"
                             "学習履歴を消しても残ります")

    # -- settings --------------------------------------------------------------

    def setting_rows(self) -> list[SettingRow]:
        values = self._values()
        try:
            stored = config.stored(self.config_file)
        except (OSError, ValueError):
            stored = {}
        rows = []
        for name, text in SETTINGS.items():
            shown = text.values[values[name]]
            rows.append(SettingRow(name, text.label, shown + ("" if name in stored else "（既定）"),
                                   shown, list(text.values.values()), text.help))
        return rows

    def set_setting(self, name: str, shown: str) -> Outcome:
        """Write a value to config.json."""
        text = SETTINGS[name]
        value = {v: k for k, v in text.values.items()}.get(shown.strip())
        if value is None:
            return Outcome(False, f"「{text.label}」は一覧から選んでください")
        try:
            config.set_setting(self.config_file, name, value)
        except ValueError:
            return Outcome(False, f"設定ファイル {self.config_file} が壊れているため保存できません")
        return Outcome(True, f"「{text.label}」を「{shown.strip()}」にしました。{RESTART_NOTE}")

    def reset_setting(self, name: str) -> Outcome:
        label = SETTINGS[name].label
        try:
            removed = config.unset_setting(self.config_file, name)
        except ValueError:
            return Outcome(False, f"設定ファイル {self.config_file} が壊れているため保存できません")
        if not removed:
            return Outcome(True, f"「{label}」は既定値のままです")
        return Outcome(True, f"「{label}」を既定値に戻しました。{RESTART_NOTE}")

    def key_settings(self) -> keymap.KeymapSettings:
        return keymap.load_keymap(self.runtime_dir, list_presets=True)

    def save_keys(self, settings: keymap.KeymapSettings) -> Outcome:
        try:
            settings.save(self.runtime_dir)
        except (OSError, ValueError) as exc:
            return Outcome(False, f"キー設定を保存できませんでした（{exc}）")
        reply = broker_client.reload_keymap() or {}
        result = reply.get("keymap_reload")
        if result == "applied":
            return Outcome(True, "キー設定を保存して反映しました")
        if result == "failed":
            return Outcome(False, f"保存しましたが、反映できませんでした（{reply.get('reason', '理由不明')}）")
        if result == "deferred":
            return Outcome(True, "キー設定を保存しました。エンジンの次の起動時に反映します")
        return Outcome(True, "キー設定を保存しました。すぐに効かない場合は、エンジンを起動し直してください")

    # -- status ----------------------------------------------------------------

    def status_rows(self, store: LearningStore | None = None) -> list[tuple[str, str]]:
        """What the 状態 tab shows (DESIGN「メニュー」), in Japanese."""
        rows = []
        broker = broker_client.status()
        if broker is None:
            rows.append(("変換エンジン", "ゆらぎの常駐プログラムが動いていません"))
        else:
            rows.append(("変換エンジン", ENGINE_STATES.get(broker["state"], broker["state"])))
        warnings = [WARNINGS.get(w, w) for w in (broker or {}).get("warnings", [])]
        rows.append(("注意", "、".join(warnings) if warnings else "なし"))
        stop = broker_client.last_stop(self.runtime_dir / "logs")
        rows.append(("最後に止まった理由",
                     f"{STOP_REASONS.get(stop['stopped'], stop['stopped'])}"
                     f"（{stop['time'].replace('T', ' ')}）"
                     if stop else "なし"))

        rows.append(("学習", LEARNING_STATES[self.learning_state()]))
        if store is None:
            store = self.learning_store()
        if store is not None:
            pairs = learning_admin.pairs(store)
            rows += [("学習した変換", f"{len(pairs)} 件"),
                     ("　うち単語として覚えたもの", f"{sum(p.user_word for p in pairs)} 件"),
                     ("学習履歴の行数", f"{store.lines} 行"),
                     ("学習履歴の読めなかった行", f"{store.skipped} 行")]
        else:
            rows.append(("学習した変換", "0 件（学習履歴はまだありません）"))
        words, skipped = personal.scan_words(self.personal_file)
        rows += [("登録した単語", f"{len(words)} 件"),
                 ("個人辞書の読めなかった行", f"{skipped} 行"),
                 ("設定ファイル", str(self.config_file)
                  + ("" if self.config_file.exists()
                     else "（まだありません。すべて既定値で動いています）")),
                 ("学習履歴のファイル", str(self.learning_file)),
                 ("個人辞書のファイル", str(self.personal_file))]
        return rows

    def restart_engine(self) -> Outcome:
        """DESIGN「メニュー」: the broker's "retry" starts the engine again (new settings)."""
        if broker_client.retry():
            return Outcome(True, "変換エンジンを新しい設定で起動し直します")
        return Outcome(False, "ゆらぎの常駐プログラムが動いていません")


def declare_dpi_aware() -> None:
    """Tell Windows this process draws for the monitor's scale itself.

    Without it the window is drawn at 96 dpi and stretched as a picture (blurred
    on a scaled 4K monitor). Tk then reads the real dpi and sizes its fonts.
    """
    if sys.platform == "win32":
        import ctypes
        ctypes.OleDLL("shcore").SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE


def application_in_front() -> bool:
    """Whether the foreground window belongs to this process (always, off Windows)."""
    if sys.platform != "win32":
        return True
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetForegroundWindow.argtypes = []
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value == os.getpid()


def work_area(root, x: int, y: int) -> tuple[int, int, int, int]:
    """Left, top, right, bottom of the monitor at (x, y) without the taskbar
    (the screen, off Windows)."""
    if sys.platform != "win32":
        return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    user32 = ctypes.WinDLL("user32")
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MonitorInfo)]
    info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
    monitor = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    work = info.rcWork
    return work.left, work.top, work.right, work.bottom


class AdminWindow:
    """Widgets only: every button calls AdminModel and redraws from it."""

    def __init__(self, root, model: AdminModel):
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk, self.root, self.model = tk, ttk, root, model
        self._rows = {}  # tree -> {item id: row as given}
        self._setting_rows = {}  # settings tree item id -> SettingRow
        self._comboboxes = []
        # Pixel sizes below are at 96 dpi; the window is dpi aware (declare_dpi_aware).
        self.scale = root.winfo_fpixels("1i") / 96
        root.report_callback_exception = self._failed
        root.title("ゆらぎ 設定")
        if sys.platform == "win32":  # .ico is a Windows icon; Tk elsewhere keeps its own
            root.iconbitmap(default=str(ICON))  # default: the dialogs get it too
        root.geometry(f"{self.px(860)}x{self.px(540)}")
        from tkinter import font
        line = font.nametofont("TkDefaultFont").metrics("linespace")
        ttk.Style(root).configure("Treeview", rowheight=int(line * 1.4))
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=self.px(6), pady=self.px(6))
        self.message = tk.StringVar()
        self.message_label = ttk.Label(root, textvariable=self.message, anchor="w")
        self.message_label.pack(fill="x", padx=self.px(8), pady=(0, self.px(6)))
        for title, build in (("単語登録", self._words_tab), ("学習", self._learning_tab),
                             ("設定", self._settings_tab), ("キー", self._keys_tab),
                             ("状態", self._status_tab)):
            frame = ttk.Frame(notebook, padding=self.px(6))
            build(frame)
            notebook.add(frame, text=title)
        self.notebook, self.status_frame = notebook, frame
        notebook.bind("<<NotebookTabChanged>>", lambda e: self._tab_changed())
        root.bind_class("ComboboxPopdown", "<Map>", lambda e: self._close_lists_when_left(),
                        add="+")
        self._keep_committed_text(root)
        self.refresh()

    def _keep_committed_text(self, root):
        # Tk gets an IME's committed text as key events with the modifiers held then and a
        # keysym from the character's low byte (え, U+3048, comes as "h"). Committed by a
        # Ctrl key (Ctrl+Q while converting: commit and pass), it was ignored or ran
        # TEntry's Ctrl+H, D or K. A real Ctrl+letter carries a control character or none.
        root.bind_class("CommittedText", "<Control-Key>",
                        "if {[string is print -strict %A] && ![string equal %A { }]} "
                        "{ttk::entry::Insert %W %A; break}")
        widgets = [root]
        while widgets:
            widget = widgets.pop()
            widgets.extend(widget.winfo_children())
            if widget.winfo_class() == "TEntry":
                widget.bindtags(("CommittedText", *widget.bindtags()))

    def px(self, pixels: int) -> int:
        return round(pixels * self.scale)

    def work_area(self, x: int, y: int) -> tuple[int, int, int, int]:
        return work_area(self.root, x, y)

    def _combobox(self, parent, variable, values, width):
        box = self.ttk.Combobox(parent, textvariable=variable, values=values, state="readonly",
                                width=width)
        self._comboboxes.append(box)
        return box

    def _close_lists_when_left(self):
        # An open Combobox list holds Tk's grab, and on Windows Tk then reports no
        # FocusOut (nor Deactivate) when the user switches to another application:
        # Tk's own "close on FocusOut" never runs and the list stays on screen over
        # the other windows. While a list is open, watch the foreground window.
        tcl = self.root.tk
        posted = [box for box in self._comboboxes
                  if tcl.call("winfo", "exists", f"{box}.popdown")
                  and tcl.call("winfo", "ismapped", f"{box}.popdown")]
        if not posted:
            return
        if application_in_front():
            self.root.after(200, self._close_lists_when_left)
            return
        for box in posted:
            tcl.call("ttk::combobox::Unpost", str(box))

    # helpers
    def _table(self, parent, columns, widths, *, horizontal=False):
        ttk = self.ttk
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for col, width in zip(columns, widths):
            tree.heading(col, text=col)
            tree.column(col, width=self.px(width), stretch=not horizontal and col == columns[-1])
        bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        if horizontal:
            scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            tree.configure(xscrollcommand=scroll.set)
            scroll.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.pack(fill="both", expand=True)
        return tree

    def _fill(self, tree, rows):
        # The rows are kept here and read back by item id: Tk's own copy of the
        # values comes back converted (a surface "10" as the int 10).
        tree.delete(*tree.get_children())
        self._rows[tree] = {}
        for i, row in enumerate(rows):
            iid = str(i)
            self._rows[tree][iid] = tuple(row)
            tree.insert("", "end", iid=iid, values=row)

    def _selected(self, tree):
        sel = tree.selection()
        return self._rows.get(tree, {}).get(sel[0]) if sel else None

    def _show(self, outcome: Outcome):
        self.message.set(outcome.message)
        self.message_label.configure(foreground="" if outcome.ok else "red")
        self.refresh()

    def _failed(self, _kind, error, _traceback):
        """A button's handler raised, e.g. a file could not be written (disk
        full, read-only). The window has no console to print to: say it here."""
        self.message.set(f"できませんでした（{error}）")
        self.message_label.configure(foreground="red")

    def _tab_changed(self):
        # A message belongs to the tab it came from.
        self.message.set("")
        self.refresh()

    def _ask(self, question: str) -> bool:
        from tkinter import messagebox
        return messagebox.askyesno("ゆらぎ", question, parent=self.root)

    # tabs
    def _words_tab(self, frame):
        tk, ttk = self.tk, self.ttk
        form = ttk.Frame(frame)
        form.pack(fill="x", pady=(0, self.px(6)))
        self.w_reading, self.w_surface = tk.StringVar(), tk.StringVar()
        self.w_pos, self.w_cost = tk.StringVar(value="名詞"), tk.StringVar()
        for label, var, width in (("読み", self.w_reading, 16), ("単語", self.w_surface, 16)):
            ttk.Label(form, text=label).pack(side="left")
            ttk.Entry(form, textvariable=var, width=width).pack(side="left", padx=(2, self.px(8)))
        ttk.Label(form, text="品詞").pack(side="left")
        self._combobox(form, self.w_pos, POS_NAMES, 9).pack(side="left", padx=(2, self.px(8)))
        ttk.Label(form, text="コスト").pack(side="left")
        ttk.Entry(form, textvariable=self.w_cost, width=6).pack(side="left", padx=(2, self.px(8)))
        ttk.Button(form, text="登録", command=self._add_word).pack(side="left")
        ttk.Button(form, text="選択を削除", command=self._remove_word).pack(side="right")
        ttk.Label(frame, text=f"コストは小さいほど上位に出ます（空欄なら {personal.DEFAULT_COST}）"
                  ).pack(fill="x", pady=(0, self.px(4)))
        self.words_tree = self._table(frame, ("読み", "単語", "品詞", "コスト"),
                                      (180, 220, 120, 80))

    def _add_word(self):
        outcome = self.model.add_word(self.w_reading.get(), self.w_surface.get(),
                                      self.w_pos.get(), self.w_cost.get())
        if outcome.ok:
            self.w_reading.set("")
            self.w_surface.set("")
        self._show(outcome)

    def _remove_word(self):
        row = self._selected(self.words_tree)
        if row and self._ask(f"{row[0]} → {row[1]} を削除しますか？"):
            self._show(self.model.remove_word(row[0], row[1]))

    def _learning_tab(self, frame):
        tk, ttk = self.tk, self.ttk
        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, self.px(6)))
        self.l_query, self.l_pos = tk.StringVar(), tk.StringVar(value="名詞")
        ttk.Label(top, text="検索").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.l_query, width=16)
        entry.pack(side="left", padx=(2, self.px(8)))
        entry.bind("<Return>", lambda e: self.refresh())
        ttk.Button(top, text="検索", command=self.refresh).pack(side="left")
        self.l_counts = tk.StringVar()
        ttk.Label(frame, textvariable=self.l_counts).pack(fill="x")
        actions = ttk.Frame(frame)
        actions.pack(side="bottom", fill="x", pady=(self.px(6), 0))
        ttk.Button(actions, text="選択を忘れる", command=self._forget).pack(side="left")
        ttk.Label(actions, text="品詞").pack(side="left", padx=(self.px(16), 2))
        self._combobox(actions, self.l_pos, POS_NAMES, 9).pack(side="left", padx=(0, self.px(4)))
        ttk.Button(actions, text="選択を単語登録", command=self._promote).pack(side="left")
        self.learning_tree = self._table(
            frame, ("読み", "変換", "最後の確定", "単語として覚えた"),
            (160, 200, 140, 110))

    def _forget(self):
        row = self._selected(self.learning_tree)
        if row and self._ask(f"{row[0]} → {row[1]} の学習を忘れますか？"):
            self._show(self.model.forget(row[0], row[1]))

    def _promote(self):
        row = self._selected(self.learning_tree)
        if row:
            self._show(self.model.promote(row[0], row[1], self.l_pos.get()))

    def _settings_tab(self, frame):
        tk, ttk = self.tk, self.ttk
        edit = ttk.Frame(frame)
        edit.pack(side="bottom", fill="x", pady=(self.px(6), 0))
        self.s_name, self.s_label, self.s_value = "", tk.StringVar(), tk.StringVar()
        ttk.Label(edit, textvariable=self.s_label).pack(side="left")
        self.s_box = self._combobox(edit, self.s_value, [], 30)
        self.s_box.configure(state="disabled")  # until an item is picked
        self.s_box.pack(side="left", padx=self.px(4))
        ttk.Button(edit, text="保存", command=self._save_setting).pack(side="left")
        ttk.Button(edit, text="既定に戻す", command=self._reset_setting
                   ).pack(side="left", padx=self.px(4))
        # The description column is cut at its width: the picked item's is shown here whole.
        self.s_help = tk.StringVar(value="項目を選ぶと、ここに説明が出て、下で変更できます。"
                                         "変更は、変換エンジンを再起動すると反映されます（「状態」タブ）。")
        ttk.Label(frame, textvariable=self.s_help, wraplength=self.px(820), justify="left"
                  ).pack(side="bottom", fill="x", pady=(self.px(6), 0))
        self.settings_tree = self._table(frame, ("項目", "値", "説明"), (260, 200, 400))
        self.settings_tree.bind("<<TreeviewSelect>>", self._pick_setting)

    def _pick_setting(self, _event=None):
        sel = self.settings_tree.selection()
        if not sel:
            return
        row = self._setting_rows[sel[0]]
        self.s_name = row.name
        self.s_label.set(row.label)
        self.s_help.set(row.help)
        self.s_value.set(row.edit)
        self.s_box.configure(values=row.choices, state="readonly")

    def _save_setting(self):
        if self.s_name:
            self._show(self.model.set_setting(self.s_name, self.s_value.get()))

    def _reset_setting(self):
        if self.s_name:
            self._show(self.model.reset_setting(self.s_name))

    def _status_tab(self, frame):
        ttk = self.ttk
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(0, self.px(6)))
        ttk.Button(buttons, text="表示を更新", command=self._refresh_status).pack(side="right")
        ttk.Button(buttons, text="変換エンジンを再起動",
                   command=lambda: self._show(self.model.restart_engine())
                   ).pack(side="right", padx=self.px(6))
        self.status_tree = self._table(frame, ("項目", "内容"), (240, 560))

    def _keys_tab(self, frame):
        self.keys_frame, self.keys_tab = frame, KeyTab(self, frame)

    def refresh(self):
        m = self.model
        store = m.learning_store()
        self._fill(self.words_tree, [(w.reading, w.surface, w.pos, w.cost) for w in m.words()])
        self._fill(self.learning_tree,
                   [m.learned_row(p) for p in m.learned(self.l_query.get(), store)])
        self.l_counts.set(m.learning_counts(store))
        rows = m.setting_rows()
        self._fill(self.settings_tree, [(r.label, r.value, r.help) for r in rows])
        self._setting_rows = {str(i): r for i, r in enumerate(rows)}
        # Query the broker when the status tab is visible.
        if self.notebook.select() == str(self.status_frame):
            self._refresh_status(store)
        elif self.notebook.select() == str(self.keys_frame):
            self.keys_tab.open()

    def _refresh_status(self, store=None):
        self._fill(self.status_tree, self.model.status_rows(store))


@contextlib.contextmanager
def _windows_activation(config_file: Path):
    """Own this config's window, or signal its owner and yield None."""
    import _winapi
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]

    path = os.path.normcase(str(config_file.resolve()))
    name = "Local\\yuragi-ime-admin-" + hashlib.sha256(os.fsencode(path)).hexdigest()
    with contextlib.ExitStack() as handles:
        # Create the event first so a second launch can signal us during startup.
        event = kernel32.CreateEventW(None, False, False, name + "-activate")
        if not event:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.callback(_winapi.CloseHandle, event)
        mutex = kernel32.CreateMutexW(None, False, name)
        if not mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.callback(_winapi.CloseHandle, mutex)
        if _winapi.WaitForSingleObject(mutex, 0) == _winapi.WAIT_TIMEOUT:
            if not kernel32.SetEvent(event):
                raise ctypes.WinError(ctypes.get_last_error())
            yield None
            return
        handles.callback(kernel32.ReleaseMutex, mutex)
        yield event


def _raise_windows_admin(root):
    import ctypes
    from ctypes import wintypes

    if root.state() in ("iconic", "withdrawn"):
        root.deiconify()
    # An already active window can still be covered by an inactive one.
    root.lift()
    user32 = ctypes.WinDLL("user32")
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetLastActivePopup.argtypes = [wintypes.HWND]
    user32.GetLastActivePopup.restype = wintypes.HWND
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    hwnd = user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT, Tk's outer window
    popup = user32.GetLastActivePopup(hwnd)
    target = popup if popup and user32.IsWindowVisible(popup) else hwnd
    if not user32.SetForegroundWindow(target):
        # The background broker may start us without permission to take focus.
        # Move above regular windows and immediately return to the normal Z order.
        root.attributes("-topmost", True)
        root.attributes("-topmost", False)


def _watch_windows_activation(root, event):
    import _winapi

    if _winapi.WaitForSingleObject(event, 0) == _winapi.WAIT_OBJECT_0:
        _raise_windows_admin(root)
    root.after(100, _watch_windows_activation, root, event)


@contextlib.contextmanager
def _posix_activation(config_file: Path):
    """As _windows_activation: a locked file holds the owner's process ID, and SIGUSR1 signals it.

    Yields a threading.Event that is set at each signal, or None when another process owns the window.
    """
    import fcntl
    import signal
    import threading

    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file.parent / "admin.lock", "a+", encoding="ascii") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.seek(0)
            owner = lock.read().strip()
            if owner.isdigit():
                os.kill(int(owner), signal.SIGUSR1)
            yield None
            return
        event = threading.Event()
        # The handler first: the signal ends a process that has none.
        signal.signal(signal.SIGUSR1, lambda *_: event.set())
        lock.seek(0)
        lock.truncate()
        lock.write(str(os.getpid()))
        lock.flush()
        yield event


def _raise_posix_admin(root):
    if root.state() in ("iconic", "withdrawn"):
        root.deiconify()
    root.lift()
    # Started by a background program, the window opens behind the application in front.
    root.attributes("-topmost", True)
    root.attributes("-topmost", False)
    root.focus_force()


def _watch_posix_activation(root, event):
    if event.is_set():
        event.clear()
        _raise_posix_admin(root)
    root.after(100, _watch_posix_activation, root, event)


def _run_window(model: AdminModel, dict_dir: Path | None, event=None) -> int:
    if dict_dir is not None:
        from yuragi.lattice import mozc_dict
        mozc_dict.DICT_DIR = dict_dir
    import tkinter as tk
    declare_dpi_aware()
    root = tk.Tk()
    AdminWindow(root, model)  # opens on 単語登録
    if event is not None:
        windows = sys.platform == "win32"
        root.update_idletasks()
        (_raise_windows_admin if windows else _raise_posix_admin)(root)
        root.after(100, _watch_windows_activation if windows else _watch_posix_activation, root, event)
    root.mainloop()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runtime-dir", type=Path, default=None)
    parser.add_argument("--dict-dir", type=Path, default=None)
    args = parser.parse_args(argv)
    model = AdminModel(args.runtime_dir)
    activation = _windows_activation if sys.platform == "win32" else _posix_activation
    with activation(model.config_file) as event:
        if event is None:
            return 0
        return _run_window(model, args.dict_dir, event)


if __name__ == "__main__":
    sys.exit(main())
