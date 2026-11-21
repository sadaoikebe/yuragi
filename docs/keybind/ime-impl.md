# 既存の IME のキーの受け取り方

オープンソースの Windows の IME（TSF のテキストサービス）が、キーをどう受け取り、食べるかをどう決め、繰り返しと up をどう扱っているか。
ソースを読んで分かること。Windows 側の事実は [windows.md](windows.md)。略号は §5 の出典。

---

## 1. 一覧

| IME | キーの受け取り | `OnTestKeyDown` と `OnKeyDown` | up | 繰り返し・`lParam` | PreservedKey |
|---|---|---|---|---|---|
| Mozc（Google 日本語入力）[MOZC] | キーの呼び出しと PreservedKey だけ | 同じ判定（`HandleKey`）を、テストはサーバーの `TestSendKey`、本番は `SendKey` に通す | 修飾キー単独の up（直前の down が同じ修飾キーのとき）だけ食べ、ほかの up は食べない。食べた down を覚えない | bit 30 を読む関数はあるが使わない。bit 31 で up/down を見る。スキャンコードは `ToUnicode` に渡すだけ | `{VK_OEM_3, ALT}` と `{VK_KANJI, 修飾を問わない}`（同じ GUID、どちらも半角／全角として扱う）、`VK_DBE_ROMAN`・`VK_DBE_NOROMAN`（修飾を問わない）、F10 |
| CorvusSKK [CORVUS] | 同上 | 4 つの呼び出しすべてで同じ関数 `_IsKeyEaten`（そのときの状態だけで決める） | down と同じ関数で、そのときの状態で決める（入力中は up も食べる）。キーごとの記録は無い | `lParam` を読まない。`ToUnicode` のスキャンコードは 0 | オン用とオフ用の GUID に、同じ `{VK_OEM_3, ALT}`・`{VK_KANJI}`・`{0xF3}`・`{0xF4}`（修飾を問わない）と `VK_IME_ON`/`VK_IME_OFF` |
| tsf-tutcode [TUTCODE] | 同上 | 4 つの呼び出しで同じ `_IsKeyEaten`（down/up とテストかを引数で渡す） | 仮想キーコードごとに down と同じ規則 | bit 31 だけ（Mozc のコード） | CorvusSKK と同じ。設定で修飾を付けないと「修飾を問わない」になる |
| Microsoft SampleIME [SAMPLEIME] | 同上 | 4 つで同じ `_IsKeyEaten` | down と同じ判定（仮想キーコードごと） | **bit 30 を使う唯一の例**: Shift の最初の down（bit 30 が 0）でだけ「Shift だけ押した」印を立てる。スキャンコード 0x36 で右 Shift、bit 24 で右 Alt/Ctrl を見る | `{VK_SHIFT, TF_MOD_ON_KEYUP}`（Shift 単独で入力モードを切り替え）、`{VK_SPACE, SHIFT}`、`{VK_OEM_PERIOD, CTRL}` |
| Weasel（RIME）[WEASEL] | キーの呼び出しだけ（PreservedKey の登録は無効にしてある） | 同じ関数 `_ProcessKeyEvent`。`OnTestKeyDown` の答えを覚え、同じキーの `OnKeyDown` ではそれを返す（「`OnKeyDown` だけを呼ぶアプリ」「`OnTestKeyDown` を何度も呼ぶ Word」への対策とコメントにある） | up もエンジンに送り、エンジンが決める（CapsLock だけ、食べた down の up を食べる） | bit 30 は読まない。スキャンコード 0x36 で右 Shift | 無し |
| PIME [PIME] | キーの呼び出しと PreservedKey | 同じ `filterKeyDown`（`OnKeyDown` で「呼ばれないアプリがあるので、もう一度確かめる」とコメント） | `filterKeyUp` で down と対称 | 使わない（スキャンコードの取り出しは誤りで常に 0） | Shift+Space（全角/半角の切り替え。押し続けると呼ばれるたびに切り替わる） |
| azooKey-Windows [AZOOKEY] | キーの呼び出しだけ | 同じ `process_key` | 食べない | 読まない | 登録しない。半角／全角（0xF3・0xF4）の down で切り替える |
| windows-chewing-tsf [CHEWING] | キーの呼び出しだけ | `OnKeyDown` の最初で `OnTestKeyDown` の判定を呼ぶ | `OnTestKeyUp` が `OnKeyUp` を呼ぶ | スキャンコードを使う（0 のアプリ（WPF）では `MapVirtualKey` で補う） | 登録しない |
| win-mcbopomofo [MCBOPOMOFO] | キーの呼び出しだけ | 一致しない（単独の Shift・Ctrl で `OnTestKeyDown` は FALSE、`OnKeyDown` は TRUE のことがある） | `OnTestKeyUp` は常に FALSE、`OnKeyUp` は TRUE のことがある | スキャンコードを `ToUnicode` に渡すだけ | 登録しない |

- **キーボードフック・Raw Input を使う IME は無い。** どれも、修飾の状態を呼び出しの中で `GetKeyboardState`／`GetKeyState` で読む。
- **PreservedKey の繰り返しを見分ける IME は無い。** `OnPreservedKey` が呼ばれるたびに実行する。
- **離すときに仮想キーコードが変わること（`VK_KANJI` の down と `VK_OEM_3` の up）を扱う IME は無い。** Mozc・azooKey・chewing は up を食べないので問題にならず、
  CorvusSKK・tsf-tutcode・SampleIME は up をそのときの状態で決める。
- `TF_MOD_ON_KEYUP` を使うのは SampleIME だけ（Shift 単独）。

## 2. オン/オフのキーを押し続けたとき

| IME | 動き（ソースから） |
|---|---|
| Mozc | `OnPreservedKey` は偽の `lParam`（繰り返し回数 1、bit 30 は 0、スキャンコードは常に F10 のもの）を作って通常の down として処理する。キー表では半角／全角が「入力なし→オフ」「直接入力→オン」なので、繰り返しのたびにオンとオフが入れ替わる |
| CorvusSKK・tsf-tutcode | オン/オフが変わるたびに、PreservedKey を「次に押したら逆になる側の GUID が先」になるよう登録し直す（同じキーを後から登録した GUID は上書きしない、とコメントにある）。繰り返しのたびにオンとオフが入れ替わる。`VK_IME_ON`・`VK_IME_OFF` は片方の GUID にしか無いので、押し続けても変わらない |
| PIME | Shift+Space は呼ばれるたびに全角/半角を切り替える |
| SampleIME | Shift 単独の切り替えは、Shift の最初の down で印を立て、`TF_MOD_ON_KEYUP` で離したときに 1 回だけ切り替える |
| MS-IME、ATOK | ソースが無く、押し続けたときの動きを書いた資料も無い |

## 3. 修飾キーの単独打鍵（Shift を押して離すだけ）

| IME | やり方 |
|---|---|
| SampleIME | PreservedKey `{VK_SHIFT, TF_MOD_ON_KEYUP}`。キーの呼び出しのたびに印を更新し、Shift の最初の down（bit 30 が 0、Ctrl・Alt なし）で立て、ほかのキーで消す。`OnPreservedKey` では印が立っているときだけ切り替える |
| Mozc | 直前の down が同じ修飾キーのときだけ、その up をサーバーに送る（例: Shift↓ A↓ Shift↑ A↑ では A だけ、Shift↓ Shift↑ A↓ A↑ では Shift と A） |
| PIME | 最後の down が Shift で、押していた時間が 0.5 秒未満なら、up で切り替える。押した時刻は、仮想キーコードが変わったときだけ記録し直す（Shift の繰り返しでは更新しない） |
| windows-chewing-tsf | Shift の down で時刻を記録（状態が「離れている」ときだけ）、ほかのキーと同時なら取り消し、up で設定の時間未満なら切り替える |
| win-mcbopomofo | Shift だけの down で印を立て、ほかのキーの down やフォーカスの移動で消し、up で印があれば切り替える（時間は見ない） |

## 4. そのほか

- **Mozc の F10**: `OnPreservedKey` で F10 を食べなかったときは、`WM_SYSKEYDOWN` を自分でフォーカスの窓に送る。コメントに
  「`*eaten` に FALSE を入れるだけでは、アプリが F10 を扱うときに足りない」とある [MOZC]。
- **Mozc のカナのロック**: アクティブになったときとフォーカスを得たときに、カナのロックを外す（`EnsureKanaLockUnlocked`。コメントは「パスワードを打てるように」）[MOZC]。
  CorvusSKK は、文字を作るときに一部のモードでキーの状態のカナのロックを消してから `ToUnicode` を呼ぶ [CORVUS]。
- **Mozc の `VK_KANJI`**: IMM32 では OS 側で IME を開くので、IMM32 版ではサーバーに送らず、TSF 版では半角／全角として扱う（[windows.md](windows.md) §5）[MOZC]。
- **Weasel のコメント**: 「`OnKeyDown` だけを送るアプリ（QQ2012）」「1 つのキーに `OnTestKeyDown` を何度も送るアプリ（MS Word 2010 x64）」がある [WEASEL]。

## 5. 出典

| 略号 | 資料 | URL |
|---|---|---|
| MOZC | Mozc `src/win32/tip/`・`src/win32/base/`（commit 1527a4cd）。`tip_text_service.cc`（PreservedKey、`OnPreservedKey`）、`tip_keyevent_handler.cc`、`base/keyevent_handler.cc`（up の規則、VK_KANJI の注記）、`base/keyboard.cc` | https://github.com/google/mozc/tree/1527a4cd1217cec4611cd4bc8d46f8c66ea79e6a/src/win32 |
| MOZC-IMM | Mozc の IMM32 版（2023 年に削除。commit 08ef9a0c） `src/win32/ime/` | https://github.com/google/mozc/tree/08ef9a0c6267a41e2c8774c960c9b9d4cf3a62dc/src/win32/ime |
| CORVUS | CorvusSKK `imcrvtip/`（commit a7f1cf08）。`KeyEventSink.cpp`、`ConfigTip.cpp`、`KeyHandler.cpp` | https://github.com/nathancorvussolis/corvusskk/tree/a7f1cf083ba7c9f0866e7dd4decb3e91c8f18794/imcrvtip |
| TUTCODE | tsf-tutcode `imcrvtip/`（commit df1847ab） | https://github.com/deton/tsf-tutcode/tree/df1847aba25a560a857bf4f69849c1101bd1cc3f/imcrvtip |
| SAMPLEIME | Microsoft Windows-classic-samples SampleIME（commit 434f6002）。`KeyEventSink.cpp`、`CompositionProcessorEngine.cpp`、`Globals.cpp`、`Define.h` | https://github.com/microsoft/Windows-classic-samples/tree/434f6002bdf9cf9829406c3ff2b33387982d6168/Samples/IME/cpp/SampleIME |
| WEASEL | Weasel `WeaselTSF/KeyEventSink.cpp`、`include/KeyEvent.h`（commit f96ed24a） | https://github.com/rime/weasel/tree/f96ed24a8a535961b6ffc7160d98851a69cee4f8 |
| PIME | PIME（commit 1911328a）と libIME2（commit 70d41ec0）`src/TextService.cpp`、`src/KeyEvent.h` | https://github.com/EasyIME/PIME/tree/1911328aac38cc117961a1945fa578316a77f4ff 、https://github.com/EasyIME/libIME2/tree/70d41ec0a901df1b4f470683d801ff84e50a8016 |
| AZOOKEY | azooKey-Windows `crates/client/src/tsf/key_event_sink.rs`（commit 65835aa1） | https://github.com/fkunn1326/azooKey-Windows/tree/65835aa1afd9ae7fafd7c58a86ea017877ebc58f |
| CHEWING | windows-chewing-tsf `tip/src/text_service/`（commit 181b9e0f） | https://github.com/chewing/windows-chewing-tsf/tree/181b9e0f34519026ad84a147aeab78aa844d701d |
| MCBOPOMOFO | win-mcbopomofo `src/Client/McBopomofoTIP.cpp`（commit 7f7ae3a0） | https://github.com/openvanilla/win-mcbopomofo/tree/7f7ae3a0c8dfcc3764df1999d87df083136b9337 |
