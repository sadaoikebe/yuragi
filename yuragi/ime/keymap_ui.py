"""The management window's key editor."""

from __future__ import annotations

from yuragi.chord.keys import ALT, CTRL, SHIFT, Chord
from . import keymap
from .commands import COMMANDS
from .keyboard_setting import system_keyboard

PHASES = {
    "global": "常時", "empty": "入力なし", "composing": "入力中", "converting": "変換中",
    "selecting": "候補選択中", "resizing": "文節長変更中", "predicting": "予測の候補",
    "editing": "文節内入力",
}
MODIFIERS = {
    "なし": 0, "Shift": SHIFT, "Ctrl": CTRL, "Ctrl+Shift": CTRL | SHIFT, "Alt": ALT,
    "Alt+Shift": ALT | SHIFT, "Ctrl+Alt": CTRL | ALT, "Ctrl+Alt+Shift": CTRL | ALT | SHIFT,
}


class KeyTab:
    def __init__(self, window, frame):
        self.window = window
        tk, ttk = window.tk, window.ttk
        self.settings: keymap.KeymapSettings | None = None
        self.added: set[Chord] = set()
        self.chords: dict[str, Chord] = {}
        # The keys offered by キー追加 are this keyboard's (docs/JIS.md §2).
        self.keyboard = system_keyboard()

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, window.px(6)))
        ttk.Label(top, text="キー設定").pack(side="left")
        self.preset_box = window._combobox(top, tk.StringVar(), (), 30)
        self.preset_box.pack(side="left", padx=window.px(6))
        self.preset_box.bind("<<ComboboxSelected>>", self._select_preset)
        self.rename_button = ttk.Button(top, text="名前を変更…", command=self._rename,
                                        state="disabled")
        self.rename_button.pack(side="left")
        self.notes_button = ttk.Button(top, command=self._show_notes, text="読み込みの記録",
                                       state="disabled")
        self.notes_button.pack(side="right")

        bottom = ttk.Frame(frame)
        bottom.pack(side="bottom", fill="x", pady=(window.px(6), 0))
        self.phase = tk.StringVar(value=PHASES["composing"])
        ttk.Label(bottom, text="局面").pack(side="left")
        window._combobox(bottom, self.phase, tuple(PHASES.values()), 15
                         ).pack(side="left", padx=window.px(6))
        ttk.Button(bottom, text="変更", command=self._edit).pack(side="left")
        ttk.Button(bottom, text="キー追加", command=self._add).pack(side="left", padx=window.px(6))
        self.save_button = ttk.Button(bottom, text="保存", command=self._save, state="disabled")
        self.save_button.pack(side="right")
        ttk.Label(frame, text="旧版の DLL が残っているアプリは、開き直すと変更が反映されます。"
                  ).pack(side="bottom", anchor="w", pady=(window.px(6), 0))

        self.tree = window._table(frame, ("キー", *PHASES.values()),
                                  (108, 108, 115, 125, 125, 125, 125, 125, 125), horizontal=True)
        self.tree.bind("<Button-1>", self._pick_cell)
        self.tree.bind("<Double-1>", self._double_click)
        self.tree.bind("<Return>", lambda _event: self._edit())

    def open(self):
        if self.settings is not None:
            return
        try:
            self.settings = self.window.model.key_settings()
        except (OSError, ValueError):
            self.window.message.set("同梱の MS-IME プリセットを読めません。再インストールしてください")
            return
        if self.settings.error or self.settings.notes:
            self.save_button.configure(state="normal")
        self._draw()

    def _draw_presets(self):
        settings = self.settings
        self.presets = list(settings.presets)
        labels = [preset.label for preset in settings.presets.values()]
        if settings.legacy:
            self.presets.append(None)
            labels.append(settings.presets[keymap.DEFAULT_PRESET].label + "（従来の切り替えキー）")
        if settings.base is not None:
            self.presets.append(keymap.CUSTOM)
            label = settings.custom_name or "ユーザー定義"
            labels.append(label + "（ユーザー定義）" if label in labels else label)
        self.preset_box.configure(values=labels)
        self.preset_box.current(self.presets.index(None if settings.legacy else settings.use))
        self.rename_button.configure(state="normal" if settings.use == keymap.CUSTOM else "disabled")

    def _draw(self, chord=None):
        self._draw_presets()
        settings = self.settings

        count = len(settings.notes) + bool(settings.error)
        self.notes_button.configure(text=f"読み込みの記録（{count}）",
                                    state="normal" if count else "disabled")
        rows = settings.bindings()
        keys = self.added | {key for _, key in rows}
        self.chords = {str(i): key for i, key in enumerate(sorted(keys, key=lambda k: str(k).casefold()))}
        self.tree.delete(*self.tree.get_children())
        for iid, key in self.chords.items():
            cells = [self._cell(rows, phase, key) for phase in PHASES]
            self.tree.insert("", "end", iid=iid, values=(str(key), *cells))
        iid = next((iid for iid, key in self.chords.items() if key == chord), None)
        if iid is not None:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

    @staticmethod
    def _cell(rows, phase, chord):
        current = phase
        while current:
            command_id = rows.get((current, chord))
            if command_id is not None:
                command = COMMANDS[command_id]
                if keymap.implemented(command):
                    return command.label if current == phase else command.label + "（継承）"
                if current == phase:
                    return command.label + "（未実装）"
            current = keymap.PARENT.get(current)
        return "–"

    def _select_preset(self, _event):
        use = self.presets[self.preset_box.current()]
        if use is not None and (use != self.settings.use or self.settings.legacy):
            self.settings.use = use
            self.settings.legacy.clear()
            self.save_button.configure(state="normal")
            self._draw()

    def _rename(self):
        dialog, body = self._dialog("キー設定の名前を変更")
        name = self.window.tk.StringVar(value=self.settings.custom_name)
        self.window.ttk.Label(body, text="表示名（空欄なら「ユーザー定義」）").pack(anchor="w")
        entry = self.window.ttk.Entry(body, textvariable=name, width=30)
        entry.pack(fill="x", pady=(0, self.window.px(8)))

        def apply():
            text = name.get().strip()
            dialog.destroy()
            if text != self.settings.custom_name:
                self.settings.custom_name = text
                self.save_button.configure(state="normal")
                self._draw_presets()

        self.window.ttk.Button(body, text="変更", command=apply).pack(side="right")
        dialog.bind("<Return>", lambda _event: apply())
        entry.selection_range(0, "end")
        entry.focus_set()
        self.window._keep_committed_text(dialog)
        self._show_dialog(dialog)

    def _pick_cell(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            column = int(self.tree.identify_column(event.x)[1:])
            if column > 1:
                self.phase.set(tuple(PHASES.values())[column - 2])

    def _double_click(self, event):
        if self.tree.identify_region(event.x, event.y) == "cell":
            self._pick_cell(event)
            self._edit()
            return "break"

    def _phase_id(self):
        return next(phase for phase, label in PHASES.items() if label == self.phase.get())

    def _dialog(self, title):
        dialog = self.window.tk.Toplevel(self.window.root)
        dialog.withdraw()
        dialog.title(title)
        dialog.transient(self.window.root)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        body = self.window.ttk.Frame(dialog, padding=self.window.px(12))
        body.pack(fill="both", expand=True)
        return dialog, body

    def _show_dialog(self, dialog):
        """Show the filled dialog next to the selected row: below it, or above it when
        the monitor ends first. Windows alone would put it at the screen's top."""
        tree, gap = self.tree, self.window.px(4)
        dialog.attributes("-alpha", 0.0)  # measured while shown, then moved
        dialog.deiconify()
        dialog.update()  # mapped: the frame around the client area can be measured
        title = dialog.winfo_rooty() - dialog.winfo_y()
        border = dialog.winfo_rootx() - dialog.winfo_x()
        width = dialog.winfo_width() + 2 * border
        height = dialog.winfo_height() + title + border
        selection = tree.selection()
        box = tree.bbox(selection[0]) if selection else ""
        if box:
            x, y, _, row = box
            left = tree.winfo_rootx() + x + self.window.px(24)
            top, bottom = tree.winfo_rooty() + y, tree.winfo_rooty() + y + row
        else:
            root = self.window.root
            left = root.winfo_rootx() + (root.winfo_width() - width) // 2
            top = bottom = root.winfo_rooty() + root.winfo_height() // 3
        area_left, area_top, area_right, area_bottom = self.window.work_area(left, bottom)
        y = bottom + gap
        if y + height > area_bottom:
            y = top - gap - height
        y = max(area_top, min(y, area_bottom - height))
        x = max(area_left, min(left, area_right - width))
        dialog.geometry(f"+{x}+{y}")
        dialog.attributes("-alpha", 1.0)
        dialog.grab_set()

    def _edit(self):
        selection = self.tree.selection()
        if self.settings is None or not selection:
            return
        chord = self.chords[selection[0]]
        phase = self._phase_id()
        label = str(chord)
        if not keymap.chord_allowed(phase, chord):
            self.window.message.set(f"{label} は「{PHASES[phase]}」に割り当てられません")
            return

        preset = "プリセットに従う"
        remove = "この局面の割り当てを外す"
        choices = {cmd.label: cmd.id for cmd in COMMANDS.values()
                   if keymap.command_allowed(phase, chord, cmd)
                   and keymap.implemented(cmd)}
        key = phase, chord
        active = self.settings.overrides if self.settings.use == keymap.CUSTOM else self.settings.legacy
        picked = preset
        if key in active:
            picked = remove
            if active[key] is not None:
                picked = COMMANDS[active[key]].label
        dialog, body = self._dialog(f"{label} ／ {PHASES[phase]}")
        choice = self.window.tk.StringVar(value=picked)
        box = self.window._combobox(body, choice, (preset, remove, *choices), 44)
        box.pack(fill="x", pady=(0, self.window.px(8)))
        box.focus_set()

        def apply():
            new = choice.get()
            dialog.destroy()
            if new == picked:
                return
            self.settings.begin_custom()
            if new == preset:
                self.settings.overrides.pop(key, None)
            else:
                self.settings.overrides[key] = choices.get(new)
            self.save_button.configure(state="normal")
            self._draw(chord)

        self.window.ttk.Button(body, text="変更", command=apply).pack(side="right")
        dialog.bind("<Return>", lambda _event: apply())
        self._show_dialog(dialog)

    def _add(self):
        if self.settings is None:
            return
        dialog, body = self._dialog("キー追加")
        tk, ttk = self.window.tk, self.window.ttk
        modifier, key = tk.StringVar(value="なし"), tk.StringVar()
        mods_box = self.window._combobox(body, modifier, tuple(MODIFIERS), 20)
        key_box = self.window._combobox(body, key, (), 16)
        for label, widget in (("修飾", mods_box), ("キー", key_box)):
            ttk.Label(body, text=label).pack(side="left")
            widget.pack(side="left", padx=self.window.px(6))
        existing = set(self.chords.values())

        def update(_event=None):
            mods = MODIFIERS[modifier.get()]
            values = [name for name in self.keyboard.names() if Chord(name, mods) not in existing
                      and any(keymap.chord_allowed(phase, Chord(name, mods)) for phase in PHASES)]
            key_box.configure(values=values)
            key.set(values[0] if values else "")

        def add():
            if not key.get():
                return
            chord = Chord(key.get(), MODIFIERS[modifier.get()])
            if not keymap.chord_allowed(self._phase_id(), chord):
                self.phase.set(PHASES["global" if chord.alt_only else "converting"])
            self.added.add(chord)
            dialog.destroy()
            self._draw(chord)

        mods_box.bind("<<ComboboxSelected>>", update)
        ttk.Button(body, text="追加", command=add).pack(side="left")
        dialog.bind("<Return>", lambda _event: add())
        update()
        mods_box.focus_set()
        self._show_dialog(dialog)

    def _show_notes(self):
        dialog, body = self._dialog("キー設定の読み込みの記録")
        text = self.window.tk.Text(body, width=68, height=10, wrap="word")
        bar = self.window.ttk.Scrollbar(body, orient="vertical", command=text.yview)
        bar.pack(side="right", fill="y")
        text.configure(yscrollcommand=bar.set)
        text.pack(side="left", fill="both", expand=True)
        errors = [self.settings.error] if self.settings.error else []
        text.insert("1.0", "\n".join(errors + self.settings.notes))
        text.configure(state="disabled")
        self._show_dialog(dialog)

    def _save(self):
        outcome = self.window.model.save_keys(self.settings)
        if outcome.ok:
            self.settings.error = None
            self.settings.notes.clear()
            self.save_button.configure(state="disabled")
            selection = self.tree.selection()
            self._draw(self.chords[selection[0]] if selection else None)
        self.window._show(outcome)
