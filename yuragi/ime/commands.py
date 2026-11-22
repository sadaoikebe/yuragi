"""IME commands and the phases they can be assigned to (KEYBIND §3)."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .session import ImeSession


GLOBAL = frozenset({"global"})
EMPTY = frozenset({"empty"})
COMPOSING = frozenset({"composing"})
RESIZING = frozenset({"resizing"})
EDITING = frozenset({"editing"})
CONVERTED = frozenset({"converting", "selecting"}) | RESIZING | EDITING
SELECTING = frozenset({"selecting", "predicting"})
INPUT = COMPOSING | CONVERTED | SELECTING
KANA = EMPTY | INPUT
LOCAL = KANA | {"direct"}


@dataclass(frozen=True, slots=True)
class Command:
    id: str
    label: str
    phases: frozenset[str]
    key: str = "eat"
    where: str = "engine"
    run: Callable[[ImeSession], str | None] | None = None
    keeps_resizing: bool = False
    until: str | None = None


COMMANDS = MappingProxyType({c.id: c for c in (
    Command("ime_toggle", "IME オン／オフ", GLOBAL | {"predicting"}, where="tip"),
    Command("ime_on", "IME オン", GLOBAL, where="tip"),
    Command("ime_off", "IME オフ", GLOBAL, where="tip"),
    Command("mode_hiragana", "ひらがな入力", GLOBAL, where="tip"),
    Command("mode_katakana", "カタカナ入力", GLOBAL, where="tip"),
    Command("open_settings", "設定を開く", GLOBAL, where="tip"),
    Command("open_word_register", "単語登録を開く", GLOBAL | EMPTY, where="tip"),
    Command("open_menu", "IME メニューを開く", EMPTY, where="tip"),
    Command("insert_space", "空白", EMPTY | COMPOSING, run=lambda s: s._insert_space("　")),
    Command("insert_alt_space", "別幅空白", EMPTY, run=lambda s: s._insert_space(" ")),
    Command("insert_full_space", "全角空白", KANA, run=lambda s: s._add_space("　")),
    Command("insert_half_space", "半角空白", KANA, run=lambda s: s._add_space(" ")),
    Command("undo_commit", "確定取り消し", EMPTY),
    Command("reconvert", "再変換", EMPTY | {"direct"}),
    Command("convert", "変換", COMPOSING, run=lambda s: s._convert()),
    Command("convert_segment", "文節を変換", RESIZING, run=lambda s: s._end_resize()),
    Command("convert_edited_segment", "入力中の文節を変換", EDITING,
            run=lambda s: s._convert_edited_segment()),
    Command("predict", "予測候補", COMPOSING, run=lambda s: s._predict_key()),
    Command("commit", "全確定", INPUT, run=lambda s: s._commit()),
    Command("commit_first_segment", "先頭の文節を確定", INPUT, run=lambda s: s._commit_prefix()),
    Command("commit_one_char", "先頭の一字を確定", COMPOSING, run=lambda s: s._commit_one_char()),
    Command("commit_to_focus", "注目文節まで確定", CONVERTED),
    Command("delete_before", "前字削除", COMPOSING | CONVERTED, run=lambda s: s._delete_before()),
    Command("alnum_mode", "英数の続き", INPUT, run=lambda s: s._hold_alnum(), keeps_resizing=True),
    Command("delete_after", "後字削除", COMPOSING, until="noop"),
    Command("cursor_left", "カーソルを左へ", COMPOSING, until="noop"),
    Command("cursor_right", "カーソルを右へ", COMPOSING, until="noop"),
    Command("cursor_home", "カーソルを先頭へ", COMPOSING, until="noop"),
    Command("cursor_end", "カーソルを末尾へ", COMPOSING, until="noop"),
    Command("cancel", "全消去", COMPOSING, run=lambda s: s._cancel()),
    Command("cancel_conversion", "変換を取り消す", CONVERTED | {"predicting"},
            run=lambda s: s._cancel_conversion()),
    Command("segment_revert", "文節戻し", {"converting", "selecting"},
            run=lambda s: s._segment_revert()),
    Command("cancel_resize", "文節長変更を取り消す", RESIZING,
            run=lambda s: s._cancel_resize()),
    Command("to_hiragana", "ひらがなに変換", INPUT, run=lambda s: s._to_script("hiragana")),
    Command("to_katakana", "カタカナに変換", INPUT, run=lambda s: s._to_script("katakana")),
    Command("to_half_katakana", "半角カタカナに変換", INPUT,
            run=lambda s: s._to_script("half_katakana")),
    Command("to_full_alnum", "全角英数に変換", INPUT, run=lambda s: s._to_script("full_alnum")),
    Command("to_half_alnum", "半角英数に変換", INPUT, run=lambda s: s._to_script("half_alnum")),
    Command("close_candidates", "候補窓を閉じる", {"selecting"}, run=lambda s: s._clear_cands()),
    Command("next_candidate", "次の候補", CONVERTED | SELECTING, run=lambda s: s._cycle(1)),
    Command("prev_candidate", "前の候補", CONVERTED | SELECTING, run=lambda s: s._cycle(-1)),
    Command("candidate_first", "先頭の候補", SELECTING, run=lambda s: s._select(0)),
    Command("candidate_last", "最後の候補", SELECTING, run=lambda s: s._select_last()),
    Command("next_page", "次の候補ページ", SELECTING, run=lambda s: s._page(1)),
    Command("prev_page", "前の候補ページ", SELECTING, run=lambda s: s._page(-1)),
    *(Command(f"select_candidate_{n}", f"候補 {n} を選ぶ", SELECTING,
              run=lambda s, row=n - 1: s._select_row(row)) for n in range(1, 10)),
    Command("segment_left", "前の文節へ", CONVERTED, run=lambda s: s._move_segment(-1)),
    Command("segment_right", "次の文節へ", CONVERTED, run=lambda s: s._move_segment(1)),
    Command("segment_first", "先頭の文節へ", CONVERTED,
            run=lambda s: s._move_segment(-len(s.segments))),
    Command("segment_last", "末尾の文節へ", CONVERTED,
            run=lambda s: s._move_segment(len(s.segments))),
    Command("segment_shrink", "文節を縮める", CONVERTED, run=lambda s: s._resize(-1),
            keeps_resizing=True),
    Command("segment_expand", "文節を伸ばす", CONVERTED, run=lambda s: s._resize(1),
            keeps_resizing=True),
    Command("forget_candidate", "候補の学習を忘れる", SELECTING,
            run=lambda s: s.forget_candidate()),
    Command("noop", "何もしない", LOCAL, run=lambda s: None, keeps_resizing=True),
    Command("pass_through", "そのまま通す", LOCAL, key="pass", run=lambda s: None,
            keeps_resizing=True),
    Command("commit_and_pass", "確定して通す", INPUT, key="commit_pass", run=lambda s: s._commit()),
)})

for command in COMMANDS.values():
    if command.until is not None:
        assert command.run is None and command.where == "engine", command.id
        assert command.until in ("noop", "pass_through") and command.until in COMMANDS, command.id
