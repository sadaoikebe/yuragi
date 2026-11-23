# IME トランスクリプト

実行: `python3 -m unittest tests.test_transcripts -v`

`*.json` 一つを1ケースとし、`tests/test_transcripts.py` が自動発見する。キー操作は本番と同じ
`server.dispatch()` を通る。試験は各操作が例外なく終わり、確定を累積した文がファイルの `committed` と
一致することを確かめる。ステップに `commit` を指定すると、その打鍵（`event`）で確定する文字列も検査する。

`lexicon` に小さな決定的辞書を書く（各行は reading/surface と任意の cost/lid/rid、
既定 100/1/1。`connection` に連接行列も書ける）。

`t` はミリ秒、単調非減少。`op` は down/up/timeout/reset。`mods` は省略可能な
`["shift", "ctrl", "alt", "win"]` の部分集合で、イベント時点の修飾スナップショット。
