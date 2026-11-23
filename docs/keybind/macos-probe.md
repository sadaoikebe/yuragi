# macOS 日本語入力プログラムを実機で調べる方法

macOS の日本語入力プログラムの動きを、Mac の実機で調べる方法。Windows の [tools/keyprobe](../../tools/keyprobe/README.md) に当たる道具が `tools/keyprobe/mac/` にある。
結果は [macos.md](macos.md)、[macos-table.md](macos-table.md)、[macos-vs-windows.md](macos-vs-windows.md)。道具の使い方は [tools/keyprobe/mac/README.md](../../tools/keyprobe/mac/README.md)。

---

## 1. 概要

| 項目 | 内容 |
|---|---|
| 方法 | 試験用の小さなアプリ（`probe.swift`、Swift の 1 ファイル）。窓の中のビューが `NSTextInputClient` を実装し、日本語入力プログラムからの呼び出しを JSON の行で記録する。キーは、同じアプリの中で `NSEvent` を合成して `NSApp.sendEvent` に渡す |
| 自動で採れるもの | 入力中・予測候補・変換中・候補ウインドウ・確定後・ライブ変換でのキーの大半。変換中の文字列、文節の区切り、注目文節、確定した文字、アプリに渡ったコマンド、入力ソースの切り替え、候補ウインドウの画像 |
| 設定の切り替え | `defaults write` と、日本語入力プログラムのプロセスの再起動で自動にできる（§6） |
| 要る許可 | 候補ウインドウを画像で撮るときの「画面収録」だけ（1 回）。キーを入れるのに許可は要らない |
| 人の手が要るもの | システムが先に取るキー（Control＋Space、Caps Lock、地球儀キー）、押し続け、修飾キーの単独打鍵を本物のキーボードで押すこと（§5） |
| Windows 版との違い | キーが試験アプリの外に出ないので、別の窓にキーが行く事故が起きない。前面の窓の確認（`lib.guard`）は、キーを入れる前の安全のためではなく、記録が使えるかの判定に使う |

---

## 2. Windows の道具との対応

| Windows（tools/keyprobe） | Mac（tools/keyprobe/mac） |
|---|---|
| `SendInput` でキーを送る | プロセス内で `CGEvent` → `NSEvent(cgEvent:)` → `NSApp.sendEvent` |
| `target_tsf.py` / `target_imm.py`（届いたキーと文字を記録する窓） | `probe.swift`: `NSTextInputClient` を最小限に実装したビュー。`setMarkedText`・`insertText`・`doCommand(by:)` を記録。`tv.swift`: AppKit の標準のテキスト欄（`NSTextView`）。キーごとに文書の文字・変換中の文字・選択範囲を記録 |
| 変換中の文字列と属性（IMM の `GCS_COMPATTR`） | `setMarkedText` の属性付き文字列。`NSMarkedClauseSegment`（文節の番号）、`NSUnderline`（2 は太い＝注目文節、1 は細い）、選択範囲 |
| 「アプリに届いた down」（IME が食べなかったキー） | `doCommand(by:)` に来るセレクタ（`insertNewline:`、`moveLeft:` など）と、IME を素通りした `insertText`（§3.2） |
| IME の開閉と入力モード（`status`） | `NSTextInputContext.selectedKeyboardInputSource` と `keyboardSelectionDidChangeNotification`。入力モードは入力ソース ID で区別される |
| Alt+\` で MS-IME をオンにする | `inputContext.selectedKeyboardInputSource = "com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese"` |
| `msime_tsf_seq.py`（キーの列と画面の撮影） | `probe app` と `seq.sh`。候補ウインドウは `screencapture -x -o -l <窓番号>` |
| `msime_tsf_table.py`（状態 × キーの表） | `table.py`。結果を `report.py` で表にする |
| `manual-start` / `manual-report`（本物のキーボードで押す） | `guide.py`（試験アプリが押すキーを窓に出し、人が押したキーを記録する） |
| 確認用の TIP（TSF が TIP をどう呼ぶか） | 無い。InputMethodKit の呼ばれ方を見ても、Apple の日本語入力プログラムの動きは分からない（§8） |

---

## 3. 仕組み

### 3.1 キーを入れる方式

| 方式 | やり方 | 許可 | 使えるか |
|---|---|---|---|
| A. プロセス内（アプリ経由） | `CGEvent(keyboardEventSource:virtualKey:keyDown:)` で作り、`NSEvent(cgEvent:)` にして `NSApp.sendEvent` に渡す | 不要 | **使う**。入力・変換・候補・英数/かなキーまで動く |
| B. プロセス内（ビューへ直接） | 同じイベントをビューの `keyDown(with:)` に直接渡す | 不要 | 使わない。英数/かなキーと Control＋Shift＋J などのモード切替が効かない |
| C. 自分のプロセスへ送る | `CGEvent.postToPid(getpid())` | アクセシビリティ | 許可が無いと黙って捨てられる |
| D. システム全体へ送る | `CGEvent.post(tap: .cghidEventTap)` | アクセシビリティ | 本物のキーと同じ道を通るので、システムが先に取るキーに使える見込み。前面が試験アプリのときだけ送る確認が要る |

- 矢印キーには `.maskNumericPad` と `.maskSecondaryFn`、ファンクションキーと Home/End/Page Up/Down には `.maskSecondaryFn` のフラグを付ける（本物のイベントに合わせる）。
- 修飾キーだけの打鍵は、イベントの種類を `flagsChanged` にして作る（`probe.swift` の `MODKEYS`）。Caps Lock はこれでは効かない（ロックの状態はシステムが持つ）。
- イベントのキーボードの種類は `PROBE_KBTYPE` で変えられる。キーの間の時間は `PROBE_GAP`（かなキーの 2 回押しは 0.15 秒なら効き、0.45 秒では効かない）。

### 3.2 記録するもの

1 つのキーごとに次を 1 行ずつ書く（主な項目だけを抜いた）。

```
{"ev":"press","key":"{Space}"}
{"ev":"setMarkedText","s":"今日は雨です","segs":[{"at":0,"len":3,"NSMarkedClauseSegment":0,"NSUnderline":2,"s":"今日は"},{"at":3,"len":3,"NSMarkedClauseSegment":1,"NSUnderline":1,"s":"雨です"}],"sel":[0,3]}
{"ev":"keyDown","code":49,"chars":" ","handled":true}
{"ev":"after","text":"","marked":"今日は雨です","sel":[0,3],"source":"com.apple.inputmethod.Kotoeri.RomajiTyping.Japanese"}
```

| 行 | 中身 |
|---|---|
| `setMarkedText` | 変換中の文字列、文節ごとの属性、選択範囲（入力中はカーソルの位置、変換中は注目文節の範囲）、置き換え範囲 |
| `insertText` | 確定した文字、または IME を素通りした文字 |
| `doCommand` | IME が食べずにアプリへ渡したキーのコマンド |
| `source` | 入力ソースが変わった（通知） |
| `after` | キーのあと 0.45 秒待ってからの、確定済みの文字・変換中の文字・入力ソース・開いている窓 |

- `handleEvent` の戻り値は、どのキーでも `true` になる。IME が食べたかどうかは、戻り値では分からない。
- IME が食べなかったキーは、`doCommand` か素通しの `insertText` で分かる。何も来なかったときは、同じキーを英字（ABC）で押した結果と比べる。ABC ではコマンドか文字が来るなら、IME が食べた。ABC でも何も来ないキー（Control＋Space、Control＋Tab、Control＋/、Command 付きのキーなど）は、食べたかどうかを区別できない。
- Command 付きのキーは `tv.swift` で見る。`tv.swift` はメインメニュー（編集・保存）を持ち、Command 付きの矢印・Delete のイベントを本物と同じ文字（← は U+F702 など）で作る。`probe.swift` にはメニューが無く、合成した Command＋矢印の文字は古い制御文字になるので、Command 付きのキーはテキスト欄に効かない。
- `tv.swift` は Command＋C / X でクリップボードを書き換えるので、起動時にクリップボードを退避し、終了時に戻す。

### 3.3 候補ウインドウ

- 候補ウインドウ（変換候補も推測候補も）は、別プロセスの窓ではなく**試験アプリ自身の窓**（クラス `NSPanel.ViewBridge.rendezvous`、中身は `NSRemoteView`）として出る。開いているか・大きさ・位置は `NSApp.windows` で分かる（許可不要）。
- 中身は別プロセスが描くので、アプリの中からは読めない（`cacheDisplay` では中身の無い画像になり、アクセシビリティの木は `NSAccessibilityRemoteUIElement` で止まる）。
- `screencapture -x -o -l <windowNumber> out.png` で、その窓だけを撮れる（画面収録の許可が要る）。番号、注目している候補、下のタブ（標準・読み・部首・名前・記号）、辞書の印まで写る。
- 候補の順序は、Space を押すたびに変わる注目文節の文字からも採れる。ただし窓の中の並び（番号）は Space で進む順と違うので、番号のキーを調べるときは画像で並びを見る。

### 3.4 状態を作る・片付ける

状態の作り方は `table.py` の `STATES`（`kanji`、`kanji {Space}`、`kyouhaamedesu {Space} {Shift+Left}` など。全部は [macos-table.md](macos-table.md) の冒頭）。

- 表の 1 件ごとに、変換中の文字を捨て（`discardMarkedText`）、確定済みの文字を空にし、試験の窓を前面に戻し、入力ソースを選び直してから状態を作る（`probe.swift` の `reset`）。
- キーのあとは Esc を 3 回押し、残った文字を「確定した文字」として記録する。
- 確定済みの文字の再変換・確定の取り消し・Control＋1 / 2 は、アプリが選択範囲・置き換え範囲（`replacementRange`）・確定済みの文字を返すかで動きが変わる。これらは `tv.swift`（`NSTextView`）で見る。`probe.swift` のビューは返す作りが最小限で、選んでいないときの再変換などが動かない。`{Sel:n}` で確定済みの末尾 n 字を選ぶ。

---

## 4. 速さ

- 1 件は状態作りを含めて 3.5 秒ほど。11 状態 × 147 キー（1617 件）で 95 分。
- 1 つの状態のキーを全部、1 つの試験アプリのプロセスで採る（プロセスの起動は 1 回 2 秒ほどかかる）。

---

## 5. この方法で採れないもの

| 採れないもの | 理由 | 代わりの方法 |
|---|---|---|
| Control＋Space、Control＋Option＋Space、Caps Lock、fn / 地球儀キー、Command＋Control＋Space | システムがアプリより先に取る。プロセス内で合成したキーはそこを通らない | 人が押す（`guide.py`）。方式 D |
| Caps Lock を点けたときの入力 | 日本語入力プログラムはイベントの印（`maskAlphaShift`）でなく本物のロックの状態を見るので、合成では採れない | 人が押す（`guide.py`） |
| 押し続け（キーリピート）、修飾キーの押し離しの順 | 合成では本物のキーボードの出方を再現しきれない | 人が押す（`guide.py`） |
| JIS キーボードに固有のキー（¥、_ など）の文字 | 本体が US 配列 | JIS キーボードをつなぐ |
| かな入力 | 入力ソース「日本語 - かな入力」が別にある | 有効にして同じ方法で |
| 入力メニュー（メニューバー）からの操作 | 別プロセスの UI | 人が操作する |
| ほかのアプリ（ブラウザ、Electron）での違い | 試験アプリは AppKit の標準の経路だけ | 方式 D ＋ 画面の撮影 |

**人が押す手順（`guide.py`）**: 試験アプリが状態を作り、ビープを鳴らし、押すキーを窓に赤字で出す。キーを離して 0.3 秒で次の手順に進む。キーが届かない手順は 4 秒で次へ進み、最初の手順でキーが届かなければ全体を止める。

- 1 手順は数秒で終わるようにする。キーを離したら次へ進み、待ちは結果が出るのに要る分だけにする。
- 手順は、メインのディスパッチキューの外（`RunLoop.main.perform`）から始める。キューの処理（`DispatchQueue.main.async` など）の中から始めると、システムがメインキューに積む仕事が待ちの間に動かず、地球儀キーで入力ソースが切り替わらない。
- 待つ間は `NSApp.nextEvent` でイベントを取り出してアプリに渡す。`RunLoop.run` で待つだけだと、本物のキーはキューに残ったまま、窓にもイベントの監視にも届かない。
- 本物のキーは、ローカルのイベント監視（`addLocalMonitorForEvents`）で取る。この監視は `NSApp.sendEvent` に渡した合成のキーも拾うので、合成している間（`injecting`）は記録しない。
- 地球儀キー・Control＋Space の行き先は、最近使った入力ソースの順（`com.apple.HIToolbox` の `AppleInputSourceHistory`）で決まる。押す前に順を決めておき（`pre_sources` で順に選ぶ）、記録の `history` で確かめる。
- Caps Lock を点けたときの入力は、人が Caps Lock を点けて打つ手順（`until_caps_off`）で見る。

---

## 6. 設定の切り替え

- 設定は `defaults` の `com.apple.inputmethod.Kotoeri` にある。キー名と値は [macos.md](macos.md) §10。
- `defaults write` で書いてから、日本語入力プログラムのプロセス（`JapaneseIM-RomajiTyping`）を SIGKILL で止めると（`pkill -9 -f JapaneseIM-RomajiTyping.appex`）、次に使うときに起動し直して読む。SIGTERM では止まらない。ライブ変換は止めなくても効く。
- 入力モード（カタカナ・全角英字など）の有効 / 無効は、入力ソースの有効 / 無効（`com.apple.HIToolbox` の `AppleEnabledInputSources`）。
- 終わったら、書いた設定を `defaults delete` で消し（初めから無かったキー）、元の値に戻し、プロセスを再起動する。入力ソースも始める前のものに戻す。

---

## 7. 注意

| 注意 | 理由 |
|---|---|
| 確定する前に、学習を止める（`JIMPrefPrivNoLearningKey=1`、プライベートモード） | 日本語入力プログラムは確定した変換を学習し、次から第 1 候補が変わる。学習を戻す手段は「変換学習: リセット」だけで、ふだんの学習も消える |
| 長く走らせるときは `caffeinate -d -i` を付ける | 画面が消えてロックされると、試験の窓が前面でなくなり、その間の件は使えない |
| 記録の `front` が false の件は捨てて採り直す（`table.py <タグ> --redo`） | 試験の窓が前面でない間は、日本語入力プログラムとのやり取りが正しくない |
| 実行中はキーボードとマウスに触らない | 試験アプリが前面でなくなる |
| 許可のダイアログ（画面収録など）が出る操作は、表を採る前に 1 回済ませておく | ダイアログが開いている間のキーは、試験の窓に届かない |
| 画面を撮る処理は、キーの処理が落ち着いてから呼ぶ | `screencapture` は別プロセス |
| 方式 D を使うときは、前面が試験アプリのときだけ送り、違えばその場で止まる | 別の窓にキーが行く（Windows 版の `lib.guard` と同じ） |
| `probe.swift`・`tv.swift` のトップレベルの変数は `app.run()` より前に宣言する | `app.run()` は戻らないので、後ろに書いた大域変数は初期化されず、使うと落ちる |
| 標準エラーの `error messaging the mach port for IMKCFRunLoopWakeUpReliable` は無視してよい | 記録には影響しない |

---

## 8. 採らなかった方法

| 方法 | 採らない理由 |
|---|---|
| AppleScript（System Events の `keystroke` / `key code`）、cliclick | アクセシビリティの許可が要り、前面の窓に送るので事故の余地がある。採れる情報は方式 A より少ない |
| テキストエディットなど既存のアプリを相手にする | 変換中の文字列・文節・注目文節を外から読む手段が画面の撮影しかない |
| システム全体のアクセシビリティ API で候補ウインドウを読む | 許可が要る。画像で足りる |
| Hammerspoon、Karabiner-Elements | キーを送る・見るだけで、IME の中の状態は見えない。常駐するものを入れることになる |
| XCUITest | Xcode のプロジェクトと試験の実行環境が要り、キーごとの細かい記録に向かない |
| InputMethodKit で確認用の IME を作る（Windows の確認用 TIP に当たる） | 見えるのは「IME がどう呼ばれるか」で、Apple の日本語入力プログラムの動きは分からない |
| Python（pyobjc） | 手元の Python に入っておらず、足すものが増える。Swift は Xcode に入っている |
