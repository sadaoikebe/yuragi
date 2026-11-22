# キー入力の実機確認の道具（keyprobe）

アプリの窓に `SendInput` でキーを送り、IME がそのキーをどう扱ったか（食べたか、アプリに届いたか、文字がどうなったか）を記録する道具。
[docs/keybind/ms-ime.md](../../docs/keybind/ms-ime.md) §1.5 の MS-IME の表は、これで採った。

TSF が TIP をどう呼ぶか（[docs/keybind/windows.md](../../docs/keybind/windows.md)）は、ゆらぎとは別の確認用の TIP で測る（下の「TSF のキーの届き方を見る」）。
どちらの道具も、ゆらぎ本体のコードには手を入れない。

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

## TSF のキーの届き方を見る（確認用の TIP）

[docs/keybind/windows.md](../../docs/keybind/windows.md) の Windows・TSF のキー入力の動きを、TIP の側から測り直す。
ゆらぎとは別の、小さな TIP（`tip/keyprobe_tip.cpp`）を入力方式「キーの確認（keyprobe）」として登録して使う。ゆらぎの登録とコードには触らない。
TSF がキーボードの TIP をどう呼ぶかは TIP の中身に依らないので、ここで測った事実はゆらぎにも当てはまる（TIP の登録の種類はゆらぎと同じにしてある）。

### 仕組み

- **確認用の TIP**: `%USERPROFILE%\.yuragi-ime\probe.json` があり `"on": true` のとき、
  ファイルに書いたキーだけを食べ、すべてのキーの呼び出しを `%USERPROFILE%\.yuragi-ime\probe.log` に 1 行ずつ書く。ファイルは 200 ms ごとに読み直す。
  ```json
  {"on": true, "seq": 1, "eat": [[85, 2]], "test_only": [[116, 0]], "preserve": [[25, 16]]}
  ```
  和音は `[仮想キーコード, 修飾]`（Shift=1、Ctrl=2、Alt=4。`preserve` だけ 16 ＝ 修飾を問わない）。
  `eat` は `OnTestKeyDown` と `OnKeyDown` で食べる、`test_only` は `OnTestKeyDown` だけ TRUE、`preserve` は PreservedKey に登録する。
  ファイルが無いか `"on": false` のときは、何も食べず、何も書かない。日本語の入力はできないので、ふだんはほかの入力方式に切り替えておく。
- **ログの 1 行**: `tick pid tid exe 呼び出し vk lp scan ext prev rep mods ret ctx ks_oem3 ks_kanji ks_capital ks_kana ks_menu`。
  `ks_*` はその呼び出しの中での `GetKeyState` の値。
- **フックの行**: `"on": true` の間、TIP はスレッドに `WH_KEYBOARD` のフックを掛け、取り出されたキーのメッセージを
  `Hook code vk lp scan prev up` として書く（Alt 付きの up など、TSF の呼び出しに来ないものも見える）。
- **スクリプト**: `probe.py`（`probe.json` の書き込み、`probe.log` の読み取り、Tk の窓、クリップボード。`lib.py` の上に乗る）、`checks.py`（確認の一覧）、
  `target_tk.py`（受け取ったキーを記録する Tk の窓）、`tip/build.ps1`（ビルド）、`tip/register.ps1`（登録と取り外し）。

### 準備

1. ビルド: `powershell -ExecutionPolicy Bypass -File .\tools\keyprobe\tip\build.ps1`（出力は `out\tip\keyprobe_tip.dll`。64 ビットのアプリ用だけ）
2. 登録: `powershell -ExecutionPolicy Bypass -File .\tools\keyprobe\tip\register.ps1`（UAC 1 回）。入力方式の一覧に「キーの確認（keyprobe）」が足される。
3. Win+Space で「キーの確認（keyprobe）」を選ぶ。試験の窓はスクリプトが開き、選んだ入力方式のまま使われる。
4. 登録し直したときは、開いていたメモ帳を閉じる（メモ帳は 1 つのプロセスで窓を開くので、古い DLL のままになる）。

### 使い方

```powershell
python -m tools.keyprobe.checks list            # 確認の一覧
python -m tools.keyprobe.checks run all         # 全部（数分。窓が次々に開く）
python -m tools.keyprobe.checks run codes kanji # 一部だけ
```

- 実行中はキーボードとマウスに触らない。キーは前面の窓が試験の窓そのもののときだけ送り、違えばその場で止まる。
- `OK` / `NG` の行は windows.md の該当の節と比べた結果、`--` の行は届いたものの記録（表と見比べる）。結果は `out/<確認>.txt` にも残る。
- 終わると `probe.json` を消す。試験で変わりうる状態（押されたままの `VK_KANJI`、大文字とカナのロック）は、各確認の中で戻す。

**本物のキーボードで押す**（繰り返しと、送ったキーとの差を見るとき）:

```powershell
python -m tools.keyprobe.checks manual-start codes    # 窓を開く。登録する PreservedKey の組: none / codes / late / hold / corvusskk
# 窓をクリックして、決めた順序でキーを押す
python -m tools.keyprobe.checks manual-report         # TIP とアプリに届いたもの
```

押す順序は、修飾を先に押す 2 つ（修飾 down → キー down → キー up → 修飾 up、修飾 down → キー down → 修飾 up → キー up）と、
キーを先に押す 2 つ（キー down → 修飾 down → キー up → 修飾 up、キー down → 修飾 down → 修飾 up → キー up）を、必ず全部やる。
押し続け（2 秒ほど）も試す。Alt を使う順序では窓のメニューに入ることがあるので、1 回ごとに Esc を 2 回押す。
Ctrl+Shift+CapsLock を押したらもう一度押して、カナのロックを戻す。

**取り外す**: Win+Space でふだんの入力方式に戻し、`powershell -ExecutionPolicy Bypass -File .\tools\keyprobe\tip\register.ps1 -Remove`（UAC 1 回）。

## してはいけないこと

| してはいけないこと | 理由 |
|---|---|
| 新しいプロファイル（`--user-data-dir`）で Edge・Chrome を開く | 起動すると Windows のアカウントで自動的にサインインし、同期を始める。アカウントのデータが手元に落ち、試験の閲覧がアカウントに上がる |
| Word・Office など、起動時にダイアログ（サインイン・ライセンス・同意）を出しうるアプリで試す | ダイアログに試験のキーが行くおそれがある |
| 前面の窓の確認（`lib.guard`）を通さずにキーを送る | 別の窓にキーが行く。キーは、前面の窓が試験の窓そのもののときだけ送り、違えばその場で止まる |
| 管理者権限で動いているアプリで試す | `SendInput` が届かず、失敗も分からない（UIPI） |
| Alt を先に離す順の確認のあと、後始末をしない | `VK_KANJI` がシステム全体で押されたままになることがある（[windows.md](../../docs/keybind/windows.md) §3.3） |
| `SendInput` で、押し続けの途中に修飾キーを挟み、そのあとも繰り返しを送る | 本物のキーボードは最後に押したキーしか繰り返さないので、その列は起きない |
| 仮想キーコードで `SendInput` する確認（`scan` を付けない `chord`）で配列の読み替えを調べる | 読み替えは起きない。`` ` ``・CapsLock の確認は必ずスキャンコードで送る |
