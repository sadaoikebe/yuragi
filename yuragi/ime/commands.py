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
PREDICTING = frozenset({"predicting"})
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
    passes_at_edge: bool = False
    starts_input: bool = False  # with no input, puts text in the document as a typed key does


COMMANDS = MappingProxyType({c.id: c for c in (
    Command("ime_toggle", "IME オン／オフ", GLOBAL | {"predicting"}, where="tip"),
    Command("ime_on", "IME オン", GLOBAL, where="tip"),
    Command("ime_off", "IME オフ", GLOBAL, where="tip"),
    Command("mode_hiragana", "ひらがな入力", GLOBAL, where="tip"),
    Command("mode_katakana", "カタカナ入力", GLOBAL, where="tip"),
    Command("mode_full_alnum", "全角英数入力", GLOBAL, where="tip"),
    Command("open_settings", "設定を開く", GLOBAL, where="tip"),
    Command("open_word_register", "単語登録を開く", GLOBAL | EMPTY, where="tip"),
    Command("open_menu", "IME メニューを開く", EMPTY, where="tip"),
    Command("insert_space", "空白", EMPTY | COMPOSING, run=lambda s: s._insert_space("　"),
            starts_input=True),
    Command("insert_alt_space", "別幅空白", EMPTY, run=lambda s: s._insert_space(" "),
            starts_input=True),
    Command("insert_full_space", "全角空白", KANA, run=lambda s: s._add_space("　"),
            starts_input=True),
    Command("insert_half_space", "半角空白", KANA, run=lambda s: s._add_space(" "),
            starts_input=True),
    Command("undo_commit", "確定取り消し", EMPTY),
    Command("reconvert", "再変換", EMPTY | {"direct"}),
    Command("convert", "変換", COMPOSING | PREDICTING, run=lambda s: s._convert()),
    Command("convert_segment", "文節を変換", RESIZING, run=lambda s: s._end_resize()),
    Command("convert_edited_segment", "入力中の文節を変換", EDITING,
            run=lambda s: s._convert_edited_segment()),
    Command("predict", "予測候補", COMPOSING, run=lambda s: s._predict_key()),
    Command("commit", "全確定", INPUT, run=lambda s: s._commit()),
    Command("commit_with_half_space", "全確定して半角空白を入れる", PREDICTING,
            run=lambda s: s._commit(suffix=" ")),
    Command("commit_at_cursor_and_pass", "カーソルを保って確定して通す", COMPOSING, key="commit_pass",
            run=lambda s: s._commit_at_cursor()),
    Command("commit_inside_and_pass", "カーソルが途中にあれば確定して通す", COMPOSING, key="commit_pass",
            run=lambda s: s._commit_at_cursor(only_inside=True)),
    Command("commit_first_segment", "先頭の文節を確定", INPUT, run=lambda s: s._commit_prefix()),
    Command("commit_one_char", "先頭の一字を確定", COMPOSING, run=lambda s: s._commit_one_char()),
    Command("delete_before", "前字削除", COMPOSING | CONVERTED, run=lambda s: s._delete_before()),
    Command("delete_last_and_commit", "末尾の一字を消して全確定", CONVERTED | PREDICTING,
            run=lambda s: s._delete_last_and_commit()),
    Command("delete_before_or_pass", "前字削除（文全体の先頭で確定して通す）", EDITING,
            run=lambda s: s._delete_at_cursor(before=True, pass_at_edge=True), passes_at_edge=True),
    Command("alnum_mode", "英数の続き", INPUT, run=lambda s: s._hold_alnum(), keeps_resizing=True),
    Command("cycle_kana_mode", "かな入力の字種を切り替え", EMPTY,
            run=lambda s: s._cycle_kana_mode()),
    Command("toggle_alnum_width", "英数入力の幅を切り替え", EMPTY,
            run=lambda s: s._toggle_alnum_width()),
    Command("cycle_kana_script", "かなの字種を切り替え", INPUT,
            run=lambda s: s._cycle_jis_script(alnum=False)),
    Command("cycle_alnum_width", "英数の幅を切り替え", INPUT,
            run=lambda s: s._cycle_jis_script(alnum=True)),
    Command("delete_after", "後字削除", COMPOSING | EDITING,
            run=lambda s: s._delete_at_cursor(before=False, pass_at_edge=True), passes_at_edge=True),
    Command("cursor_left", "カーソルを左へ", COMPOSING | EDITING, run=lambda s: s._move_cursor(-1)),
    Command("cursor_right", "カーソルを右へ", COMPOSING | EDITING, run=lambda s: s._move_cursor(1)),
    Command("cursor_left_or_pass", "カーソルを左へ（文全体の先頭で確定して通す）", EDITING,
            run=lambda s: s._move_cursor(-1, pass_at_edge=True), passes_at_edge=True),
    Command("cursor_right_or_pass", "カーソルを右へ（文全体の末尾で確定して通す）", EDITING,
            run=lambda s: s._move_cursor(1, pass_at_edge=True), passes_at_edge=True),
    Command("cursor_home", "カーソルを先頭へ", COMPOSING | EDITING, run=lambda s: s._cursor_edge(end=False)),
    Command("cursor_end", "カーソルを末尾へ", COMPOSING | EDITING, run=lambda s: s._cursor_edge(end=True)),
    Command("cancel", "全消去", COMPOSING, run=lambda s: s._cancel()),
    Command("cancel_conversion", "変換を取り消す", CONVERTED | {"predicting"},
            run=lambda s: s._cancel_conversion()),
    Command("restore_reading", "全体を読みに戻す", CONVERTED | PREDICTING,
            run=lambda s: s._cancel_conversion(show_reading=True)),
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
    *(Command(f"input_to_{script}", f"入力中の字種を{label}にする", COMPOSING,
              run=lambda s, script=script: s._set_input_script(script))
      for script, label in (("hiragana", "ひらがな"), ("katakana", "カタカナ"),
                            ("full_alnum", "全角英数"), ("half_alnum", "半角英数"))),
    Command("close_candidates", "候補窓を閉じる", {"selecting"}, run=lambda s: s._clear_cands()),
    Command("accept_candidate", "候補を選んで次の文節へ", {"selecting"},
            run=lambda s: s._accept_candidate()),
    Command("open_candidates", "候補窓を開く", {"converting"}, run=lambda s: s._open_cands()),
    Command("next_candidate", "次の候補", CONVERTED | SELECTING, run=lambda s: s._cycle(1)),
    Command("prev_candidate", "前の候補", CONVERTED | SELECTING, run=lambda s: s._cycle(-1)),
    Command("prev_prediction", "前の予測候補（先頭で止まる）", PREDICTING,
            run=lambda s: s._cycle(-1, wrap_start=False)),
    Command("candidate_first", "先頭の候補", SELECTING, run=lambda s: s._select(0)),
    Command("candidate_last", "最後の候補", SELECTING, run=lambda s: s._select_last()),
    Command("next_page", "次の候補ページ", SELECTING, run=lambda s: s._page(1)),
    Command("prev_page", "前の候補ページ", SELECTING, run=lambda s: s._page(-1)),
    Command("prev_page_wrap", "前の候補ページ（先頭から最後へ）", {"selecting"},
            run=lambda s: s._page(-1, wrap_start=True)),
    *(Command(f"select_candidate_{n}", f"候補 {n} を選ぶ", SELECTING,
              run=lambda s, row=n - 1: s._select_row(row)) for n in range(1, 10)),
    *(Command(f"pick_candidate_{n}", f"候補 {n} を選んで候補窓を閉じる", {"selecting"},
              run=lambda s, row=n - 1: s._select_row(row, close=True)) for n in range(1, 10)),
    Command("segment_left", "前の文節へ", CONVERTED, run=lambda s: s._move_segment(-1)),
    Command("segment_right", "次の文節へ", CONVERTED, run=lambda s: s._move_segment(1)),
    Command("segment_right_or_pass", "次の文節へ（最後の文節で確定して通す）", frozenset({"converting"}),
            run=lambda s: s._move_segment_or_pass(1), passes_at_edge=True),
    Command("segment_first", "先頭の文節へ", CONVERTED,
            run=lambda s: s._move_segment(-len(s.segments))),
    Command("segment_last", "末尾の文節へ", CONVERTED,
            run=lambda s: s._move_segment(len(s.segments))),
    Command("segment_shrink", "文節を縮める", CONVERTED, run=lambda s: s._resize(-1),
            keeps_resizing=True),
    Command("segment_expand", "文節を伸ばす", CONVERTED, run=lambda s: s._resize(1),
            keeps_resizing=True),
    Command("segment_shrink_and_convert", "文節を縮めて変換", CONVERTED,
            run=lambda s: s._resize(-1, convert=True)),
    Command("segment_expand_and_convert", "文節を伸ばして変換", CONVERTED,
            run=lambda s: s._resize(1, convert=True)),
    Command("forget_candidate", "候補の学習を忘れる", SELECTING,
            run=lambda s: s.forget_candidate()),
    Command("noop", "何もしない", LOCAL, run=lambda s: None, keeps_resizing=True),
    Command("pass_through", "そのまま通す", LOCAL, key="pass", run=lambda s: None,
            keeps_resizing=True),
    Command("commit_and_pass", "確定して通す", INPUT, key="commit_pass", run=lambda s: s._commit()),
)})
