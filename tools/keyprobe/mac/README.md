# macOS の日本語入力プログラムの実機確認（試作）

試験用の窓にキーを入れ、macOS の日本語入力プログラムがそのキーをどう扱ったかを記録する道具の試作。
方法と、これで確かめたこと・まだ確かめていないことは [docs/keybind/macos-probe.md](../../../docs/keybind/macos-probe.md)。

ここにあるのは、キーの列を 1 回送って記録を出すところまで。状態 × キーの表を採るスクリプトは、まだ無い。

## 中身

| ファイル | 中身 |
|---|---|
| `probe.swift` | 試験アプリ。窓のビューが `NSTextInputClient` を実装し、日本語入力プログラムからの呼び出しを JSON の行で標準出力に書く。キーは同じプロセスの中で合成して入れる |
| `summary.py` | `probe` の出力を、1 キー 1 行に縮めて表示する |

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
