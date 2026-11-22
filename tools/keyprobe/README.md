# キー入力の実機確認の道具（keyprobe）

アプリの窓に `SendInput` でキーを送り、IME がそのキーをどう扱ったか（食べたか、アプリに届いたか、文字がどうなったか）を記録する道具。
[docs/keybind/ms-ime.md](../../docs/keybind/ms-ime.md) §1.5 の MS-IME の表は、これで採った。

TIP のキーの呼び出しを直に記録するプローブ（TIP の確認用の分岐）と、[docs/keybind/windows.md](../../docs/keybind/windows.md) を測り直す `checks.py` は、
製品の TIP を変えるので、ブランチ `keyprobe` にだけ置く。

## 中身

| ファイル | 中身 |
|---|---|
| `lib.py` | `SendInput`（仮想キーコード、スキャンコード、Unicode）、前面の窓の確認、窓を探す・前に出す・閉じる |
| `target_tsf.py` | TSF の RichEdit（`SES_USECTF`。メモ帳と同じ）の窓。届いたキーのメッセージ、文字（変換中の文字を含む）、IME の開閉と入力モードを JSON の行で書く |
| `target_imm.py` | IMM の窓。届いたキー、変換中の文字列と属性、確定した文字、候補ウィンドウの通知を書く |
| `msime.py` | キーの書き方（下）と、IMM の窓にキーの列を送って記録を出すコマンド |

## MS-IME の動きを見る

入力方式を MS-IME にしてから動かす（ゆらぎの登録は要らない）。実行中はキーボードとマウスに触らない。MS-IME は試験の変換を学習する。

| スクリプト | 中身 |
|---|---|
| `msime_tsf_table.py [状態 ...]` | 状態 × キーの表（TSF のアプリ）。`target_tsf.py` の窓に送り、アプリに届いた down、キーの直後の文字、Esc を 3 回押したあとに残る文字を `out/msime_tsf_table.jsonl` に書く。全部で 70 分ほど |
| `msime_tsf_seq.py <名前> "<キー>" ...` | キーの列を `target_tsf.py` の窓に送り、名前の付いたキーごとに、届いた down、文字、IME の状態を出し、画面を `out/shots/` に撮る（窓全体と、1 行目を 4 倍にしたもの）。候補ウィンドウと下線はこれで見る |
| `msime_table.py [状態 ...]` | 同じ表を IMM のアプリで採る。`out/msime_table.jsonl` |
| `msime_hold.py` | 押し続けと、修飾とキーを離す 4 つの順序（IMM の窓）。`out/msime_hold.txt` |
| `msime_notepad.py` | 押し続けをメモ帳で確かめ、保存したファイルから読む。`out/msime_notepad.txt` |
| `msime.py "<キー>" ...` | キーの列を 1 つずつ新しい IMM の窓に送って、記録を出す |

```powershell
python -m tools.keyprobe.msime_tsf_seq a "kyouhaamedesu {Space} {Shift+Left} {Space}"
python -m tools.keyprobe.msime_tsf_table composing converted
```

- **キーの書き方:** 空白で区切る。`{Name}`・`{Ctrl+Shift+Name}` が和音 1 つ、ほかの語は 1 字ずつ打つ（ローマ字）。`{Wait}` は何も押さずに記録だけする（`msime_tsf_seq.py`）。
  名前は `msime.py` の `NAMES`（`Space`、`Left`、`` ` ``、`CapsLock`、`F1`〜`F24`、`Numpad0` など）。`` ` `` と CapsLock はスキャンコードで送る（配列が仮想キーコードを決める）。
- 状態の名前と作り方、キーの一覧は `msime_table.py` の `STATES` と `keys()`。危ないキー（単語登録や IME パッドを開くもの、Ctrl+Esc など）は `UNSAFE` で除く。
- 表の 1 件ごとに、大文字のロックが切れていること、MS-IME がひらがなであること、文書が空であることを確かめ、違えば止まる。
- 新 MS-IME の候補ウィンドウは「Windows Input Experience」の全画面の窓に描かれるので、窓の一覧からは開いているか分からない。画面を撮って見る。
- 結果は `out/`（git に入れない）。作業の窓の記録は一時フォルダの `yuragi-keyprobe`。

## してはいけないこと

| してはいけないこと | 理由 |
|---|---|
| 新しいプロファイル（`--user-data-dir`）で Edge・Chrome を開く | 起動すると Windows のアカウントで自動的にサインインし、同期を始める。アカウントのデータが手元に落ち、試験の閲覧がアカウントに上がる |
| Word・Office など、起動時にダイアログ（サインイン・ライセンス・同意）を出しうるアプリで試す | ダイアログに試験のキーが行くおそれがある |
| 前面の窓の確認（`lib.guard`）を通さずにキーを送る | 別の窓にキーが行く。キーは、前面の窓が試験の窓そのもののときだけ送り、違えばその場で止まる |
| 管理者権限で動いているアプリで試す | `SendInput` が届かず、失敗も分からない（UIPI） |
| Alt を先に離す順の確認のあと、後始末をしない | `VK_KANJI` がシステム全体で押されたままになることがある（[windows.md](../../docs/keybind/windows.md) §3.3） |
| `SendInput` で、押し続けの途中に修飾キーを挟み、そのあとも繰り返しを送る | 本物のキーボードは最後に押したキーしか繰り返さないので、その列は起きない |
