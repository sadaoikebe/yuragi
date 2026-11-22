#!/bin/sh
# Key sequences that need the order of keys or a picture of the candidate window.
#   sh seq.sh [name ...]      -> out/seq/<name>.txt (summary) and out/seq/<name>/win-<n>.png
cd "$(dirname "$0")"
J=com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese
A=com.apple.keylayout.ABC
run() {
    name=$1; src=$2; keys=$3
    [ -n "$ONLY" ] && case " $ONLY " in *" $name "*) ;; *) return ;; esac
    mkdir -p out/seq/$name
    rm -f out/seq/$name/*.png
    out/probe app $src "$keys" out/seq/$name 2>/dev/null | python3 summary.py > out/seq/$name.txt
    echo "== $name: $keys"; grep -v '^$' out/seq/$name.txt | grep -v "^ {'active'" | grep -v "^source<"
}
ONLY="$*"
run cand_tab $J "kanji {Space} {Space} {Tab} {Tab} {Tab} {Tab} {Tab} {Tab} {Esc} {Esc} {Esc}"
run cand_shift_tab $J "kanji {Space} {Space} {Shift+Tab} {Shift+Tab} {Esc} {Esc} {Esc}"
run cand_digit $J "kanji {Space} {Space} 3 {Wait} {Return} {Wait}"
run cand_digit_far $J "kanji {Space} {Space} {PageDown} 2 {Wait} {Esc} {Esc} {Esc}"
run cand_page $J "kanji {Space} {Space} {PageDown} {PageDown} {PageUp} {Shift+Down} {Shift+Up} {Ctrl+v} {Ctrl+r} {Esc} {Esc} {Esc}"
run cand_arrows $J "kanji {Space} {Space} {Right} {Left} {Up} {Down} {Esc} {Esc} {Esc}"
run conv_updown $J "kanji {Space} {Up} {Up} {Down} {Down} {Esc} {Esc} {Esc}"
run multi_cand_move $J "kyouhaamedesu {Space} {Space} {Right} {Space} {Return} {Return}"
run cand_return_twice $J "kyouhaamedesu {Space} {Space} {Return} {Wait} {Return}"
run pred_select $J "kanji {Tab} {Tab} {Shift+Tab} {Up} {Return} {Wait}"
run pred_digit $J "kanji {Tab} 2 {Wait} {Esc} {Esc}"
run pred_space $J "kanji {Tab} {Space} {Space} {Esc} {Esc} {Esc}"
run pred_right $J "kanji {Tab} {Right} {Right} {Esc} {Esc} {Esc}"
run eisu_twice_comp $J "kanji {Eisu} {Eisu} {Wait}"
run kana_twice_comp $J "kanji {Kana} {Kana} {Wait} {Esc} {Esc} {Esc}"
run kana_twice_commit $J "kanji {Space} {Return} {Kana} {Kana} {Wait} {Esc} {Esc} {Esc}"
run kana_twice_abc $A "watashi {Kana} {Kana} {Wait} {Esc} {Esc} {Esc}"
run eisu_twice_abc $A "watashi {Eisu} {Eisu} {Wait}"
run eisu_twice_after_kana $J "kanji {Return} {Eisu} {Eisu} {Wait} {Esc} {Esc} {Esc}"
run reconv_ctrl_shift_r $J "kanji {Space} {Return} {Ctrl+Shift+r} {Wait} {Space} {Esc} {Esc} {Esc}"
run reconv_opt_shift_r $J "kanji {Space} {Return} {Opt+Shift+r} {Wait} {Esc} {Esc} {Esc}"
run undo_ctrl_delete $J "kanji {Space} {Return} {Ctrl+Delete} {Wait} {Esc} {Esc} {Esc}"
run undo_ctrl_z $J "kanji {Space} {Return} {Ctrl+z} {Cmd+z} {Wait} {Esc} {Esc} {Esc}"
run esc_steps $J "kyouhaamedesu {Space} {Right} {Space} {Space} {Esc} {Esc} {Esc} {Esc}"
run delete_conv_multi $J "kyouhaamedesu {Space} {Delete} {Wait}"
run comp_type_after_conv $J "kyouhaamedesu {Space} {Right} {Ctrl+k} {Return} {Wait}"
run punct_conv $J "kyouhaame , desu . {Wait} {Esc} {Esc} {Esc}"
run shift_letters $J "kanji {Shift+a} b c {Wait} {Space} {Return} {Wait}"
run number_conv $J "1234 {Space} {Space} {Space} {Esc} {Esc} {Esc}"
run z_keys $J "zh zj zk zl z. z, z- z/ z[ z] {Wait} {Esc} {Esc} {Esc}"
run x_small $J "la xa ltu xtu lya {Wait} {Esc} {Esc} {Esc}"
run nn $J "kan'i ninngen {Wait} {Esc} {Esc} {Esc}"
run ctrl_1 $J "kanji {Space} {Return} {Ctrl+1} {Wait} {Esc} {Esc}"
run ctrl_2 $J "kanji {Space} {Return} {Ctrl+2} {Wait} {Esc} {Esc}"
