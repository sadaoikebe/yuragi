# IME トランスクリプト

実行: `python3 -m unittest tests.test_transcripts -v`

`*.json` 一つを1ケースとし、`tests/test_transcripts.py` が自動発見する。キー操作は本番と同じ
`server.dispatch()` を通る。試験が確かめるのは、どの操作でも例外が出ないことと、commit を累積した文が
ファイルの `committed` と一致することだけ。各ステップの `expect`（表示・候補・文節など）は照合しない。

`lexicon` を指定すると小さな決定的辞書を使う（各行は reading/surface と任意の cost/lid/rid、
既定 100/1/1。`connection` に連接行列も書ける）。省略すると実 Mozc 辞書を使う。

`acceptance_real_dictionary.json` は、実辞書で「今日は、機関の校正をした。」を打って確定するまでの記録。
`packaging/smoke.py` もこれを読み、インストールした木で同じ確かめをする。

`t` はミリ秒、単調非減少。`op` は down/up/timeout/reset。`mods` は省略可能な
`["shift", "ctrl", "alt", "win"]` の部分集合で、イベント時点の修飾スナップショット。
