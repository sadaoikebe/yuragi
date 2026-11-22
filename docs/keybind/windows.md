# Windows のキー入力（TSF の IME から見た事実）

キーバインドの設計（[../KEYBIND.md](../KEYBIND.md)）が前提にする、Windows のキー入力の動き。既存の IME がこれをどう扱っているかは [ime-impl.md](ime-impl.md)。

- 対象は Windows 10/11、日本語の入力言語に US キーボードの配列ドライバ（`kbd101.dll`。設定の「言語のオプション」→ キーボードでは「英語キーボード（101/102 キー）」、英語の表示では English Keyboard (101/102 key)）。
- 「実測」は Windows 11（10.0.26300）での測定。§7 のとおり、`SendInput` で送ったキーと本物のキーボードの両方で測り、特に断らなければ同じ結果。
- 修飾キーと、修飾するキーを押す・離す順序を、次の記号で書く。

| 順 | 押す | 離す |
|---|---|---|
| A | 修飾 → キー | キー → 修飾 |
| B | 修飾 → キー | 修飾 → キー |
| C | キー → 修飾 | キー → 修飾 |
| D | キー → 修飾 | 修飾 → キー |

---

## 1. TIP にキーが届く道

TIP（テキストサービス）は、`ITfKeyEventSink` の `OnTestKeyDown`・`OnKeyDown`・`OnTestKeyUp`・`OnKeyUp`（以下「キーの呼び出し」）と、
PreservedKey に登録した和音の `OnPreservedKey` でキーを受け取る。

### 1.1 アプリによる 2 通りの呼び方

| 呼び方 | アプリ（実測） | 食べたかを決めるもの |
|---|---|---|
| `OnKeyDown` だけを呼ぶ | メモ帳、Edge（Chromium）、conhost、Windows Terminal | `OnKeyDown` の答え |
| 先に `OnTestKeyDown` を呼び、TRUE のときだけ `OnKeyDown` を呼ぶ | Word、Tk（IMM 経由のアプリ） | `OnTestKeyDown` の答え |

- 後者で `OnTestKeyDown` に TRUE と答えると、`OnKeyDown` で FALSE を返しても**キーはアプリに届かない**（実測: Ctrl+A、F5、K）。
- `OnTestKeyDown` に FALSE と答えると `OnKeyDown` は呼ばれない（[TESTKEY]）。前者のアプリでは、`OnKeyDown` の FALSE でキーはアプリに届く。

### 1.2 Ctrl 付きのキー

- TIP が食べた Ctrl 付きのキーでは、アプリのショートカットは動かない（実測: メモ帳、Edge のページ内の Ctrl+A/C とブラウザの Ctrl+T、Word、conhost、Windows Terminal、Tk）。
- Ctrl+Alt の和音は、ふつうのキーと同じくキーの呼び出しに届く。

### 1.3 Alt 付きのキー（Ctrl なし）

- Alt+F などは、キーの呼び出しに**届かない**（`WM_SYSKEYDOWN`・`WM_SYSKEYUP`）。届くのは Alt キーそのものだけで、メモ帳（WinUI）では Alt キーも届かない。順序によらない。
- 受け取る道は PreservedKey だけ。登録した Alt+F を `OnPreservedKey` で食べると、メニューは開かず、Alt を離したときにメニューバーにも入らない（実測: Tk）。
  登録しない Alt+F は、アプリのメニューを開く。
- Alt を押してから離すまでに別のキーの down が無いと、Windows は Alt の単独打鍵とみなし、アプリの窓のメニューに入る。
  キーを先に押してから Alt を押した場合（順 C・D）もそうなる。メニューに入ったあとのキーはメニューに吸われ、TSF にも届かない（実測: Tk で `GetGUIThreadInfo` が `GUI_INMENUMODE`）。
- Microsoft の資料に、Alt の和音がキーの呼び出しに届くかの記述は無い。資料のメッセージループの例は `WM_KEYDOWN` だけを TSF に渡している（[TESTKEY]）。

### 1.4 PreservedKey

- 1 つの GUID に 1 つの和音を登録する。1 スレッドで 40 個を登録できた（実測。それ以上は試していない）。
  アクティブなまま外して登録し直せ、すぐ効く。外した和音は、すぐキーの呼び出しに届くようになる。
- 修飾の指定（[TFMOD]）: `TF_MOD_SHIFT`・`TF_MOD_CONTROL`・`TF_MOD_ALT` など。`TF_MOD_IGNORE_ALL_MODIFIER`（0x0400）は「Alt・Ctrl・Shift の状態を問わず、
  仮想キーが押されたときに発火する」。`TF_MOD_ON_KEYUP`（0x0200）は「キーを離したときに発火する。付けなければ押したとき」。`TF_MOD_ON_KEYDOWN` という定数は無い。
- 登録済みの和音を登録すると `TF_E_ALREADY_EXISTS`（[PRESERVEKEY]）。同じキーを 2 つの GUID に登録すると、先に登録した GUID に届く（CorvusSKK のコメントと作り。[ime-impl.md](ime-impl.md) §2）。
- 食べるのは down だけ。up はキーの呼び出しとアプリに届く。Alt 付き（Ctrl なし）の和音の up は、順 A では何も届かず、順 B では修飾なしのキーの up として届く
  （実測: Ctrl+Shift+F1 は up が届き、Alt+F は順 B のときだけ `F` の up が届いた）。
- **押し続けると、繰り返しのたびに `OnPreservedKey` が呼ばれる**（実測: Alt+`` ` `` を 2 秒押すと 26〜37 回）。`OnPreservedKey` には `lParam` が無いので、
  繰り返しか押し直しかは分からない。Alt+F は up も届かないので、「Alt を押したまま F を押し続ける」と「Alt を押したまま F を 2 回押す」は同じ列に見える。
- Microsoft の資料（`TF_PRESERVEDKEY`、`PreserveKey`、`OnPreservedKey`）は、繰り返しについて何も書いていない。

### 1.5 キーの呼び出しの `lParam`

| ビット | 中身 |
|---|---|
| 0–15 | 繰り返し回数。ふつうは 1。アプリの処理が追いつかないと、まとめられて 2 以上になる（[KBDIN]） |
| 16–23 | スキャンコード |
| 24 | 拡張キー |
| 30 | 前の状態。繰り返しの down で 1、up では 1（[KBDIN]）。ただし §3.3 の、仮想キーコードが変わって届く up では 0、押されたままに見えるキーの押し直しでは 1 |
| 31 | up で 1 |

### 1.6 スレッドのキーボードフック

TIP が自分のスレッドに `SetWindowsHookEx(WH_KEYBOARD, …, nullptr, GetCurrentThreadId())` を掛けると、そのスレッドが取り出す
すべてのキーのメッセージ（`WM_SYSKEYDOWN`・`WM_SYSKEYUP` を含む）が、`wParam`（仮想キーコード）と `lParam` 付きで届く（実測: Tk）。

- フックは、ふつうはそのキーの `OnPreservedKey`・`OnTestKeyDown` より先に呼ばれる。同じメッセージで 2 回呼ばれることがある（`PeekMessage` の、取り出さない覗き見と取り出し）。
- ただし、すべての down で呼ばれるとは限らない。Alt+F の down を 3 回続けて送ると、3 回目はフックが呼ばれずに `OnPreservedKey` だけが呼ばれた（実測。2 回の測定で同じ）。
- 押し続けた繰り返しは bit 30 が 1、押し直しの down は bit 30 が 0 で、その前に up が来る。キーの呼び出しに届かない Alt 付きの up も届く。

### 1.7 メッセージを取り出す順序

`GetMessage`・`PeekMessage` は、絞り込みを指定しなければ、次の順でメッセージを処理する（[GETMSG]）。

1. 送られたメッセージ（`SendMessage`）
2. 投函されたメッセージ（`PostMessage`）
3. 入力（キーボード・マウス）のメッセージと、システム内部の出来事
4. 送られたメッセージ（もう一度）
5. `WM_PAINT`
6. `WM_TIMER`

- したがって、TIP がキーの呼び出しの中で自分のウィンドウに投函したメッセージは、そのあとに届く入力のメッセージより先に取り出される。
- この順序は絞り込みが無いときのもの。資料は「入力のメッセージを投函されたメッセージより先に取り出すには、`wMsgFilterMin`・`wMsgFilterMax` を使う」と書いている。
  `PeekMessage` には、入力だけ（`PM_QS_INPUT`）や投函だけ（`PM_QS_POSTMESSAGE`）を処理する指定もある（[GETMSG]）。そういう取り出し方をするアプリでは、この順序は成り立たない。

---

## 2. 押しっぱなしの繰り返し

| キーボード | 繰り返しを作る所 |
|---|---|
| PS/2（多くのノート PC の内蔵キーボードは、組み込みコントローラが PS/2 として出す） | キーボード側（typematic）（[CHEN-REPEAT]、[EC]） |
| USB・Bluetooth・I2C・SPI の HID キーボード | `kbdhid.sys` のタイマー（[KB2618535]、[HIDDRV]） |
| `SendInput` | 繰り返さない |

- どれも、`lParam` の bit 30 が 1 の down の連続と、最後の 1 回の up として届く（[KBDIN]）。
- **繰り返すのは、最後に押したキーだけ**。押し続けている途中で別のキー（修飾キーを含む）を押すと、そのキーの繰り返しは止まり、別のキーを離しても再開しない。
  最後に押したキーを離すと、ほかのキーを押していても繰り返しは止まる（[IBMXT]、[HT82K28]、[FREEBSD]。実測: `` ` `` を押したまま Alt・Ctrl を押すと、`` ` `` の繰り返しが止まった）。
  したがって、繰り返しの途中に別のキーの down が挟まることはない。
- 繰り返しの down も、§3 の読み替えはそのときの修飾で引かれる。

---

## 3. `kbd101` の読み替え（NLS 表）

### 3.1 仕組み

日本語の配列ドライバは、一部のキーに `KBDSPECIAL`（NLS のキー）の印を付け、修飾の組み合わせ 8 通りごとに、送る仮想キーコードを表で決めている（[KBD101]、[KBDH]）。

- 表は**キーの出来事（down と up）ごとに、その瞬間の修飾で**引かれる。
- 組み合わせごとに「離したときも、押したときの表を使う」印（`NLSFEProcSwitch`）を付けられる。印があると、押したあとの最初の up だけ別の表（`NLSFEProcAlt`）を使い、
  そのあと元に戻る（[KBDEDIT]。実測と一致）。
- 印が無いと、押す・離す順序によっては（§3.3 の順 B・C）、押したときの仮想キーコードが押されたままになる。きれいに押して離すまで、OS はそのキーを押されたままとみなす（[KBDEDIT]）。

`kbd101` で NLS のキーは `` ` ``（スキャンコード 0x29）と CapsLock（0x3A）の 2 つ。印があるのは CapsLock の Shift+Ctrl だけ。

| キー | なし | Shift | Ctrl | Shift+Ctrl | Alt | Shift+Alt | Ctrl+Alt | Shift+Ctrl+Alt |
|---|---|---|---|---|---|---|---|---|
| `` ` `` (0x29) | `VK_OEM_3` | `VK_OEM_3` | 半角／全角（`VK_DBE_SBCSCHAR`／`VK_DBE_DBCSCHAR`） | `VK_OEM_3` | **`VK_KANJI`** | `VK_OEM_3` | `VK_OEM_3` | `VK_OEM_3` |
| CapsLock (0x3A) | `VK_CAPITAL` | 英数（`VK_DBE_ALPHANUMERIC`） | ひらがな（`VK_DBE_HIRAGANA`） | `VK_KANA`（印あり） | カタカナ（`VK_DBE_KATAKANA`） | `VK_CAPITAL` | `VK_CAPITAL` | `VK_CAPITAL` |

### 3.2 順序ごとの届き方（実測）

修飾を先に押した場合（順 A・B）。

| 押したキー | 押したとき | 順 A の up | 順 B の up |
|---|---|---|---|
| Alt+`` ` `` | `VK_KANJI`。`OnKeyDown` だけ（`OnTestKeyDown` を通らない） | `VK_KANJI` の up（`OnKeyUp`） | **`VK_OEM_3` の up**（`OnTestKeyUp`。アプリにも届く） |
| Shift+Alt+`` ` `` | `VK_OEM_3`。PreservedKey だけ（§1.3） | 届かない | `VK_OEM_3` の up |
| Ctrl+Alt+`` ` ``、Ctrl+Shift+`` ` `` | `VK_OEM_3` | `VK_OEM_3` の up | `VK_OEM_3` の up |
| Ctrl+`` ` `` | 半角／全角の片方の up と、もう片方の down（§3.5） | 届かない | `VK_OEM_3` の up |
| Alt+CapsLock | `VK_DBE_KATAKANA`。`OnKeyDown` だけ（§3.5） | 届かない | `VK_CAPITAL` の up |
| Shift+CapsLock、Ctrl+CapsLock | 英数、ひらがな（§3.5） | 届かない | `VK_CAPITAL` の up |
| Shift+Alt+CapsLock、Ctrl+Alt+CapsLock | `VK_CAPITAL`（Shift+Alt は PreservedKey だけ） | Shift+Alt は届かない。Ctrl+Alt は `VK_CAPITAL` の up | `VK_CAPITAL` の up |
| Shift+Ctrl+CapsLock | `VK_KANA`。カナのロックが切り替わる（§3.7） | `VK_KANA` の up | `VK_KANA` の up |

キーを先に押した場合（順 C・D）。down は修飾なしの `VK_OEM_3`・`VK_CAPITAL`。本物のキーボードで確かめたのは `` ` `` → Alt の C・D、`` ` `` → Ctrl の C、CapsLock → Shift の C（ほかは送ったキーだけ）。

| キー → 修飾 | 順 C の up | 順 D の up |
|---|---|---|
| `` ` `` → Alt | `VK_KANJI` の up（`OnKeyUp`） | 届かない（Alt でメニューに入る。§1.3） |
| `` ` `` → Ctrl | **届かない** | `VK_OEM_3` の up |
| `` ` `` → Shift | `VK_OEM_3` の up | `VK_OEM_3` の up |
| CapsLock → Shift、CapsLock → Ctrl | **届かない** | `VK_CAPITAL` の up |
| CapsLock → Alt | 届かない | 届かない（メニューに入る） |

### 3.3 押されたままに見えるキー

読み替えで、down と同じ仮想キーコードの up が OS に来ないと、OS はその down の仮想キーコードを押されたままとみなす。
キーの down と up のあいだで修飾の有無が変わる順（B・C）で起きる。B は修飾ありの down（`VK_KANJI` などに読み替え）に修飾なしの up、
C は修飾なしの down に修飾ありの up（読み替えられる）が来る。A と D は down と up が同じ修飾なので、押されたままにはならない
（`` ` `` → Alt の順 D は、up が窓のメニューに入って TIP には届かないが、`GetKeyState` は離れている）。

| 起きる順序 | 押されたままに見えるもの |
|---|---|
| Alt+`` ` `` の順 B | `VK_KANJI`。`GetKeyState(VK_KANJI)` が押されたままで、システム全体の `GetAsyncKeyState` でも押されたままになることがある。`GetKeyState(VK_OEM_3)` は押されていない |
| `` ` `` → Alt・Ctrl の順 C | `VK_OEM_3`。次に `` ` `` を押すと bit 30 が 1 で届く |
| CapsLock → Shift・Ctrl・Alt の順 C | `VK_CAPITAL` |

- 別の仮想キーコードで届く up（Alt+`` ` `` の順 B の `VK_OEM_3` の up）は、bit 30 が 0 のことがある。
- 同じキーを、読み替えの起きない順序できれいに押して離すと戻る（[KBDEDIT]）。

### 3.4 押し続けたとき

- 修飾を先に押して押し続けると、繰り返しは修飾付きの列で引かれる。Alt+`` ` `` を押し続けると `VK_KANJI` の down が繰り返し、PreservedKey なら繰り返しのたびに呼ばれる（§1.4）。
- 順 B で修飾を離したあとも押し続けると、そこからの繰り返しは**修飾なしのキーの down** として届く。キーは最後に押したキーなので、繰り返しは止まらない（§2）。
  Alt+`` ` `` なら `` ` `` が、Alt+CapsLock なら `VK_CAPITAL` が繰り返し届き、アプリでは `` ` `` が打たれたり、大文字のロックが切り替わったりする。
- キーを押し続けている途中で修飾を押すと（順 C・D の途中）、キーの繰り返しは止まる（§2）。

### 3.5 IME 用のキー（半角／全角・英数・ひらがな・カタカナ）

- 今のモードのキーを押されたままにして、モードを変えるときに前のキーの up と新しいキーの down を出す。Ctrl+`` ` `` は押すたびに `VK_DBE_SBCSCHAR` と `VK_DBE_DBCSCHAR` が入れ替わり、
  CapsLock の組み合わせは、すでにそのモードなら down だけを出す。順 A で離したときには何も届かない。同じ観察が spice-gtk のソースの注記にもある（[SPICE]）。
  これを仕様として書いた資料は無い。
- Shift+Ctrl+CapsLock のあとに修飾なしの CapsLock を押すと `VK_CAPITAL` が出る（「離したときも」の印は次の down まで続かない）。

### 3.6 Alt+`` ` `` を PreservedKey で受け取る

| 登録 | 届くか（実測） |
|---|---|
| `{VK_KANJI, TF_MOD_IGNORE_ALL_MODIFIER}` | **届く**（順 A・B とも） |
| `{VK_KANJI, TF_MOD_ALT}`、`{VK_OEM_3, TF_MOD_ALT}` | 届かない |
| 登録しない | `OnKeyDown` に `VK_KANJI` として届く。`OnTestKeyDown` は呼ばれない |

### 3.7 カナのロック

Shift+Ctrl+CapsLock はカナのロックを切り替える。ロック中は、IME を通らない文字（直接入力など）が半角カナになる（J なら「ﾏ」）。

---

## 4. 日本語キーボード（JIS）と `kbd106`

- JIS の 半角／全角 キーは `` ` `` と同じ 0x29、英数 キーは CapsLock と同じ 0x3A を出す。仮想キーコードを決めるのはキーボードではなく配列ドライバで、
  `kbd101` なら 0x29 は `VK_OEM_3`、`kbd106` なら `VK_DBE_SBCSCHAR`（[KBDH] の `T29`、[CHROMIUM]）。`kbd101` のもとでは、JIS のキーボードも §3 のとおりに届く。
- 配列ドライバが `kbd106` のとき: 半角／全角キーは down と up で仮想キーコードが違う（down が `VK_OEM_ENLW`、up が `VK_OEM_AUTO` など、[SPICE-ML]）。
  Alt+半角／全角 は `VK_KANJI` の down だけで up が無い（[SPICE]、[SPICE-ML]）。IME が処理したときは、アプリには `VK_PROCESSKEY` の down だけが届く（[FLUTTER]）。

---

## 5. IMM の IME ホットキー

- IMM32 には、IME とは別にシステムが処理する IME ホットキーがある。日本語の `IME_JHOTKEY_CLOSE_OPEN`（0x30）は「IME を開閉する」（[IMEHOTKEY]）。
  修飾の指定に `MOD_ON_KEYUP`（離したときに効く）と `MOD_IGNORE_ALL_MODIFIER`（修飾を問わない）がある（[IMMHOTKEY]）。繰り返しの扱いを書いた資料は無い。
- `VK_KANJI` は、IMM32 では IME のキー割り当てにかかわらず OS 側で IME を開く。TSF ではこの自動の開閉は起きない（Mozc のコメント、[MOZC]）。
- ReactOS（Windows の再実装で、Windows のコードではない）は既定の表に `{IME_JHOTKEY_CLOSE_OPEN, VK_KANJI, MOD_IGNORE_ALL_MODIFIER}` を持ち、
  繰り返しのビットを見ずに down のたびに処理する（[REACTOS]）。

---

## 6. スキャンコードとキーボードの違い

- `` ` ``（HID の使用番号 0x35）は 0x29、CapsLock（0x39）は 0x3A、左 Ctrl・Shift・Alt は 0x1D・0x2A・0x38。どの接続でも同じ（[KBDIN] の表）。
- JIS 固有のキー: International1–5（0x87–0x8B）は 0x73・0x70・0x7D・0x79・0x7B、LANG1・LANG2（0x90・0x91）は 0x72・0x71（[KBDIN]）。
- Fn キーとその層はキーボードの中で処理され、Windows には届かない（[EC]）。

---

## 7. `SendInput` で送ったキーと本物のキー

- `KEYEVENTF_SCANCODE` を付けると、スキャンコードから配列ドライバで仮想キーコードが決まる（[KEYBDINPUT]）。付けないと仮想キーコードがそのまま使われ、§3 の読み替えは起きない。
- 送ったキーは本物のキーと同じハードウェア入力のキューに入り、低レベルのフックを通ったあとでキーの状態が変わる。`SendInput` から戻った直後には、まだ変わっていない（[CHEN-SENDINPUT]）。
- 違い: 低レベルフックで `LLKHF_INJECTED` が付く（[KBDLLHOOK]）。繰り返しが作られない。最後に押したキーだけが繰り返す、という制約も無いので、
  本物のキーボードでは起きない列（繰り返しの途中に別のキーの down）を作れる。管理者権限のアプリには送れず、失敗は戻り値で分からない（UIPI、[SENDINPUT]）。
- §3 の読み替えは、送ったキーと本物のキーで同じだった（実測）。NLS 表を通ることを明記した資料は無い。

---

## 8. 失敗する作り方

| 作り方 | 起きること |
|---|---|
| `OnTestKeyDown` でとりあえず TRUE と答え、あとで `OnKeyDown` で FALSE を返して通す | Word・IMM 経由のアプリでキーが消える（§1.1） |
| Alt+文字 を、キーの呼び出しで受けようとする | 届かない（§1.3） |
| Alt+`` ` `` を `{VK_OEM_3, ALT}` や `{VK_KANJI, ALT}` で PreservedKey に登録する | 届かない（§3.6） |
| PreservedKey が呼ばれるたびに切り替えなどを実行する | 押し続けると、繰り返しのたびに実行される（§1.4） |
| 食べた down と up を仮想キーコードで対応させる | 順 B の up（`VK_OEM_3`）を取りこぼし、アプリに down の無い up が届く（§3.2） |
| 食べた down の up が必ず来ると考える | `` ` `` → Ctrl・CapsLock → Shift・CapsLock → Ctrl の順 C と、Alt でメニューに入ったあと（`` ` `` → Alt の順 D、CapsLock → Alt の順 C・D など）の up は来ない（§3.2） |
| 同じキーの down が up 無しで続いたら、必ず繰り返しとみなす | up が失われたあとの押し直しを、繰り返しと取り違える（§3.3）。繰り返しの途中に別のキーの down は挟まらない（§2） |
| down を食べたあと、修飾が変わった down をふつうのキーとして扱う | 順 B で押し続けると、`` ` `` が打たれたり大文字のロックが切り替わったりする（§3.4） |
| 押されているかを `GetKeyState(VK_KANJI)`・`GetKeyState(VK_OEM_3)` で判定する | 押されたままに見える（§3.3） |
| `lParam` の bit 30 だけで、繰り返しと up の対応を判定する | 仮想キーコードが変わって届く up では 0、押されたままに見えるキーの押し直しでは 1（§1.5） |
| 繰り返し回数（bit 0–15）を 1 と決めつける | まとめられた繰り返しを数え落とす（§1.5） |
| 仮想キーコードを指定して `SendInput` で試験する | §3 の読み替えが起きず、本物のキーと違う結果になる（§7） |
| `SendInput` で、繰り返しの途中に修飾の down を挟んで試験する | 本物のキーボードでは起きない列で判断する（§2、§7） |

---

## 9. 確かめていないこと

- `OnPreservedKey` で FALSE を返したとき、キーがアプリに通るか。
- スレッドのキーボードフック（§1.6）を、ストアアプリ（AppContainer）・Chromium・コンソールのスレッドでも掛けられ、同じ順序で呼ばれるか。
  フックが呼ばれない down があるのはなぜか、本物のキーボードの繰り返しでも起きるか。
- `SendInput` で送ったキーの `dwExtraInfo` を、TIP のキーの呼び出しの中で `GetMessageExtraInfo` で読めるか。
- `VK_KANJI` が押されたままのとき、何をきっかけにシステム全体の状態（`GetAsyncKeyState`）が戻るか。
- Electron のアプリ（Chromium の Edge とは別に）。
- アプリが Tab などでフォーカスを移すとき、そのキーのメッセージの処理の中で TSF のフォーカスの通知（`ITfThreadMgrEventSink::OnSetFocus` など）が届くか、処理が終わったあとで届くか。
  アプリごとに（Win32 のダイアログ、Word、Chromium、WPF・WinUI）。
- §1.7 の順序が成り立たない取り出し方（入力だけを選んで取り出す）をするアプリがあるか。
- フォーカスが移った直後に、同期の読み取り専用の編集セッション（`TF_ES_SYNC | TF_ES_READ`）が通るアプリと通らないアプリ。通らないとき、非同期のセッションが呼ばれるまでの時間。
- パスワード欄（Win32 の `ES_PASSWORD`、ブラウザの `type=password`、Windows の資格情報の入力）が、`SendInput` で送ったキーを受け付けるか。
- フォーカスが TSF の文書を持たないコントロール（ボタンなど）にあるとき、キーの呼び出しが来るか。

---

## 10. 出典

| 略号 | 資料 | URL |
|---|---|---|
| TESTKEY | `ITfKeystrokeMgr::TestKeyDown`・`KeyDown` | https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfkeystrokemgr-testkeydown 、https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfkeystrokemgr-keydown |
| PRESERVEKEY | `ITfKeystrokeMgr::PreserveKey` | https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfkeystrokemgr-preservekey |
| TFMOD | TF_MOD_ constants | https://learn.microsoft.com/en-us/windows/win32/tsf/tf-mod--constants |
| KBDIN | Keyboard Input Overview（`lParam`、繰り返し、スキャンコードの表） | https://learn.microsoft.com/en-us/windows/win32/inputdev/about-keyboard-input |
| CHEN-REPEAT | Raymond Chen「How does the keyboard autorepeat setting work?」 | https://devblogs.microsoft.com/oldnewthing/20091228-00/?p=15503 |
| EC | ノート PC の組み込みコントローラと PS/2 | https://8051enthusiast.github.io/2021/07/05/001-EC_legacy.html |
| KB2618535 | kbdhid.sys の自動繰り返しのタイマー | https://mskb.pkisolutions.com/kb/2618535 |
| HIDDRV | Keyboard and mouse HID client drivers | https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/keyboard-and-mouse-hid-client-drivers |
| IBMXT | IBM Personal Computer XT Technical Reference（最後に押したキーだけが繰り返す） | https://www.manualslib.com/manual/1016278/Ibm-Xt-5160.html?page=119 |
| HT82K28 | Holtek HT82K28（PS/2 キーボード用コントローラ）のデータシート | https://datasheetq.com/pdf-html/407717/Holtek/5page/HT82K28.html |
| FREEBSD | FreeBSD の USB キーボードドライバの変更（最後に押したキーだけを繰り返す） | https://lists.freebsd.org/pipermail/svn-src-stable/2020-February/052250.html |
| KBD101 | `kbd101.c`（Microsoft Windows-driver-samples、日本語 101 配列） | https://github.com/microsoft/Windows-driver-samples/blob/main/input/layout/fe_kbds/jpn/101/kbd101.c |
| KBDH | `kbd.h`（Windows SDK。`KBDNLS_*`、`T29`・`T3A`） | https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/kbd.h |
| KBDEDIT | KbdEdit マニュアル「Special NLS functions」「NLS functions editor」 | http://www.kbdedit.com/manual/low_level_special_nls_functions.html 、http://www.kbdedit.com/manual/low_level_special_nls_functions_editor.html |
| SPICE | spice-gtk `src/spice-widget.c`（日本語キーの down/up の注記） | https://gitlab.freedesktop.org/spice/spice-gtk/-/blob/master/src/spice-widget.c |
| SPICE-ML | spice-devel「Handle JP keyboard with spice-gtk from Windows client」（2016） | https://spice-devel.freedesktop.narkive.com/Gi1Jb7vL/handle-jp-keyboard-with-spice-gtk-from-windows-client |
| FLUTTER | Flutter issue #73967（全角／半角 キーの keydown に keyup が無い） | https://github.com/flutter/flutter/issues/73967 |
| CHROMIUM | Chromium `ui/events/keycodes/dom/dom_code_data.inc` | https://chromium.googlesource.com/chromium/src/+/lkgr/ui/events/keycodes/dom/dom_code_data.inc |
| IMEHOTKEY | IME Hot Key Identifiers | https://learn.microsoft.com/en-us/windows/win32/intl/ime-hot-key-identifiers |
| IMMHOTKEY | `ImmGetHotKey`（Windows CE 5.0 の資料） | https://learn.microsoft.com/en-us/previous-versions/windows/embedded/ms906010(v=msdn.10) |
| MOZC | Mozc `src/win32/base/keyevent_handler.cc`（commit 1527a4cd） | https://github.com/google/mozc/blob/1527a4cd1217cec4611cd4bc8d46f8c66ea79e6a/src/win32/base/keyevent_handler.cc |
| REACTOS | ReactOS `win32ss/user/ntuser/ime.c`・`user32/windows/input.c`（commit 303d27d6） | https://github.com/reactos/reactos/blob/303d27d62f801f1d27a056b9f296b9a5baead3a3/win32ss/user/ntuser/ime.c |
| KEYBDINPUT | `KEYBDINPUT` | https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-keybdinput |
| SENDINPUT | `SendInput` | https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput |
| KBDLLHOOK | `KBDLLHOOKSTRUCT` | https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-kbdllhookstruct |
| CHEN-SENDINPUT | Raymond Chen「GetAsyncKeyState immediately after SendInput」 | https://devblogs.microsoft.com/oldnewthing/20140213-00/?p=1773 |
| GETMSG | `GetMessage`・`PeekMessage`（Remarks の取り出し順、`PM_QS_*`） | https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmessagew 、https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-peekmessagew |
