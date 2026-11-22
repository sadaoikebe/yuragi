# macOS の日本語入力プログラムの実機確認（試作）

試験用の窓にキーを入れ、macOS の日本語入力プログラムがそのキーをどう扱ったかを記録する道具の試作。
方法と、これで確かめたこと・まだ確かめていないことは [docs/keybind/macos-probe.md](../../../docs/keybind/macos-probe.md)。

結果は [docs/keybind/macos.md](../../../docs/keybind/macos.md) §10、[macos-table.md](../../../docs/keybind/macos-table.md)、[macos-vs-windows.md](../../../docs/keybind/macos-vs-windows.md)。

## 中身

| ファイル | 中身 |
|---|---|
| `probe.swift` | 試験アプリ。窓のビューが `NSTextInputClient` を実装し、日本語入力プログラムからの呼び出しを JSON の行で標準出力に書く。キーは同じプロセスの中で合成して入れる |
| `summary.py` | `probe` の出力を、1 キー 1 行に縮めて表示する |
| `table.py <タグ> [状態 ...]` | 状態 × キーの表。1 つの状態のキーを全部、1 つの `probe table` で採る。`out/table-<タグ>.jsonl`。`--redo` で前面でなかった件を採り直す |
| `analyze.py` | 表を状態ごとに 1 キー 1 行で読む（作業用） |
| `report.py` | 表から `docs/keybind/macos-table.md` を作る |
| `seq.sh [名前 ...]` | 順序や画像が要る確認（候補ウインドウのタブ、英数・かな 2 回、再変換など）。`out/seq/<名前>.txt` と画像 |
| `guide.py <タグ> [手順 ...]` | 人が本物のキーを押す手順（窓に赤字で押すキーが出る）。`out/guide-<タグ>.jsonl` |

## 使い方

入力ソースに「日本語 - ローマ字入力」を足してある Mac で動かす。Xcode（`swiftc`）が要る。

```sh
cd tools/keyprobe/mac
mkdir -p out/shots
swiftc -O probe.swift -o out/probe
J=com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese
out/probe app $J "kyouhaamedesu {Space} {Space} {Shift+Left} {Esc} {Esc}" out/shots 2>/dev/null | python3 summary.py
```

```
[u] marked<*きょうはあめです> sel=[8, 0] handled=True => text<> src=Japanese panels=1
[{Space}] marked<*今日は|雨です> sel=[0, 3] handled=True => text<> src=Japanese panels=0
[{Shift+Left}] marked<*今日|は|雨です> sel=[0, 2] handled=True => text<> src=Japanese panels=0
```

- **引数:** `probe <入れ方> <入力ソースの ID> "<キー>" [画像のフォルダ]`。入れ方は `app` を使う（ほかの 3 つは比べるために残してある。`probe.swift` の頭のコメント）。
- **キーの書き方:** 空白で区切る。`{Name}`・`{Ctrl+Shift+Name}` が和音 1 つ、ほかの語は 1 字ずつ打つ（ローマ字）。`{Wait}` は何も押さずに記録だけする。
  `{Sel:n}` は確定済みの文字の末尾 n 字を選ぶ（再変換の確認用）。`ShiftKey`・`CtrlKey`・`OptKey`・`CmdKey`・`Fn` は修飾キーだけを押して離す。
  修飾は `Shift`・`Ctrl`・`Opt`・`Cmd`。名前は `probe.swift` の `KEY`（`Space`、`Left`、`Eisu`、`Kana`、`F1`〜`F12` など）。
- **画像のフォルダ:** 付けると、候補ウインドウが開いているキーごとに `win-<キーの番号>.png` を撮る。初回は「画面収録」の許可を求められる。付けなければ許可は何も要らない。
- **表示の読み方:** `summary.py` の頭のコメント。`|` が文節の区切り、`*` が注目文節。
- 実行中はキーボードとマウスに触らない。窓は、キーの列が終わると閉じる。
- 結果は `out/`（git に入れない）。

## 注意

| 注意 | 理由 |
|---|---|
| キーの列の最後は `{Esc}` で片付け、`{Return}` で確定しない | 日本語入力プログラムは確定した変換を学習する。試作中に「辮かん」を 1 回確定しただけで、「へんかん」の第 1 候補が変わった |
| 終わったあとの入力ソースは、最後に押したキーしだい | 始める前の入力ソースに戻す処理は入っていない |
| `2>/dev/null` を付ける | 標準エラーに `error messaging the mach port for IMKCFRunLoopWakeUpReliable` が出る（記録には影響しなかった） |
| 許可のダイアログなど、ほかの窓が前に出たら、その回の記録は捨てる | その間のキーは試験の窓に届かず、変換中の文字列が変わらなくなる。`press` の行の `front`（試験アプリが前面か）で見分けられるかは確かめていない |

## 表を採る・設定を切り替える

```sh
python3 table.py default                      # 既定の設定。11 状態 × 147 キーで 95 分ほど
python3 table.py default --redo               # 前面でなかった件を採り直す
python3 report.py out/table-default.jsonl out/table-windows.jsonl out/table-live.jsonl > ../../../docs/keybind/macos-table.md
```

- 長く走らせるときは `caffeinate -d -i` を付ける（画面がロックされると、その間の件は使えない）。
- 学習を止める: `defaults write com.apple.inputmethod.Kotoeri JIMPrefPrivNoLearningKey -int 1`。終わったら `defaults delete` で消す。
- 設定を切り替える: `defaults write com.apple.inputmethod.Kotoeri <キー> -int <値>` のあと `pkill -9 -f JapaneseIM-RomajiTyping.appex`（次に使うときに起動し直して読む）。キーの一覧は macos.md §10.9。
- 環境変数 `PROBE_GAP`（キーの間の秒。既定 0.45）、`PROBE_KBTYPE`（イベントのキーボードの種類）。かな 2 回は `PROBE_GAP=0.15` で効いた。
