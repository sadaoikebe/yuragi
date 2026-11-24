# JIS 106 対応の実装仕様

## 1. 対象

| プロファイル | 物理キーボードと Windows 設定 | かな配列 |
|---|---|---|
| `ansi101` | ANSI 101 と英語キーボード設定（`kbd101`） | NICOLA-A |
| `jis106` | JIS 106 と日本語キーボード設定（`kbd106`） | NICOLA-J |

選択単位はこの二組。Space を唯一の親指キーとし、同時打鍵では左右の面から変換が選ぶ。変換・無変換は IME の機能キー。物理位置、刻印名、文字面、局面ごとの既定は [JIS-LAYOUT.md](JIS-LAYOUT.md) を実装基準とする。

## 2. プロファイル、入力、設定

1. **Windows 設定から選ぶ。** エンジンと設定画面は `GetKeyboardLayoutList` から日本語の HKL（言語 ID `0x0411`）を取得する。TIP はキーを受けるスレッドの HKL を使う。`MapVirtualKeyExW(..., MAPVK_VSC_TO_VK_EX, hkl)` で次表の組が一致するプロファイルを選ぶ。日本語 HKL が複数ある場合は判定が一致することを条件にする。判定不能なら TIP は元の打鍵を通す。設定画面は配列が確定してから対応するキー表を開く。エンジン単体試験ではプロファイルを明示でき、指定がない既存の呼び出しは ANSI として扱う。[GetKeyboardLayoutList](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getkeyboardlayoutlist) [MapVirtualKeyExW](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-mapvirtualkeyexw)
2. **打鍵データをプロファイルに束ねる。** `yuragi/chord/keys.py` と `data/` に VK とキー ID、刻印名、単独・親指・Shift・英数面を持たせる。`yuragi/engine.py` は選択した一組を各セッションに渡す。`yuragi/ime/session.py` は既存の同時打鍵 FSM で単独か同時かを判定し、面を変換エンジンに渡す。空欄面の打鍵は消費し、未確定文字列と候補窓は保持する。F9/F10 ではかなトークンから元のキーの英数面を引く。リテラルの幅変換では、円記号キーから入った U+005C の由来を保持する。
3. **局面ごとのコマンドを実装する。** `yuragi/ime/keymap.py` で MS-IME プリセットを共通行と配列別の差分から組み立てる。JIS では半角/全角・英数による入力中の英数継続を `alnum_mode` に接続する。候補選択・文節長変更中は次の文字面入力で変換を確定し、その打鍵を消費して直接入力へ移る。予測候補選択中は次の文字面入力で候補を確定し、その打鍵の半角英数も文書に挿入して直接入力へ移る。候補番号など局面での割り当ては文字面入力に先行する。英数面の Caps Lock は打鍵時の状態を TIP から渡す。
4. **利用者のキー表を保存する。** ANSI は従来の `keymap.json` と旧 `tip.json` の互換処理を使う。JIS は同じ JSON 形式を `keymap-jis106.json` に保存する。設定画面とエンジンは同じプロファイルの刻印名、検証、プリセットを使う。macOS プリセットは共通の割り当てに加え、ANSI の Alt+バッククォートを `Alt+半角/全角`、CapsLock を `Shift+英数` に置き換える。プリセット名、利用者の差分、壊れた行の扱いは [キー設定の規則](KEYBIND.md#5-設定ファイル) に従う。

| スキャンコード | ANSI の VK | JIS の VK |
|---|---:|---:|
| `0x1A` | `0xDB` | `0xC0` |
| `0x27` | `0xBA` | `0xBB` |
| `0x29` | `0xC0` | `0xF3` |

## 3. TIP とエンジンの接続

- `tip_logic.h` と `yuragi_tip.cpp` のキー正規化と文字キー判定をプロファイルで引く。JIS の通常の文字キーは Windows の VK で識別し、`VK_OEM_102` を含める。半角/全角（`0x29`）、英数（`0x3A`）、カタカナひらがなローマ字（`0x70`）、変換（`0x79`）、無変換（`0x7B`）は、スキャンコード・打鍵時の修飾・生 VK から論理キーへ戻す。和音は基底 VK と修飾の組で表す。Windows の Caps Lock、かなロック、その他の専用ショートカットが、単独の IME キーとして再解釈されないようにする。[WDK の NLS 表](https://github.com/microsoft/Windows-driver-samples/blob/main/input/layout/fe_kbds/jpn/106/kbd106.c#L467-L571)
- 特殊キーの解放は押下時に決めた論理キーに対応させる。押下と解放で異なる DBE の VK が届くため、対応付けにはスキャンコードと拡張ビットを使う。普通のキーでスキャンコードがない場合は VK を使う。識別できない特殊イベントは通す。JIS の Alt+半角/全角は `VK_KANJI` の PreservedKey を使い、`keyprobe` で受け取れる登録形を確定する。登録が機能する経路では同じ打鍵を通常のキーコールバックから重ねて実行しない。対象外の入力欄、フォーカス移動、キーの送り直しには既存の規則を適用する。[PreserveKey](https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfkeystrokemgr-preservekey) [Windows のキー入力](keybind/windows.md)
- CMake がプロファイルごとの既定キー表と文字キー集合を Python の表から生成する。TIP は接続前から自分の配列の既定表を使い、動作できる範囲を既存の準備中の規則で決める。JIS のキー処理はエンジンと配列が一致してから有効にする。
- プロトコル 1 の `keymap` に `layout` を加え、`rev` に含める。ブローカーは既存の hello と更新通知でオブジェクトを運ぶ。JIS の打鍵・タイマー・モード変更要求には `layout: "jis106"` を付ける。ANSI の既存メッセージでは省略時を `ansi101` と扱う。配列が異なる要求は入力状態を変更せず、打鍵には `eat: false` を返す。Caps Lock は `caps_lock` を打鍵に付け、省略時はオフとする。JIS を利用するには新しい TIP とエンジンを組み合わせ、更新時は開いているアプリを再起動する。[通信の互換規則](DESIGN.md#互換の規則)

## 4. 検証

| 段階 | 確認すること |
|---|---|
| エンジンとキー表 | ANSI の既存テストに加え、JIS の文字キー 48 個の全ての面、106 キーの分類、刻印名の読み書き、設定ファイルの切り替えを確認する。`;` の `ん`・`っ`、`@` の読点と空欄面、`[` の濁点・半濁点、数字段の親指面、`Shift+0`、`¥` と `\` の幅、Caps Lock と F9/F10 を確認する。候補番号とテンキー、Space の単独・前押し・後押し、空欄面が未確定を保つことも含める |
| Windows と TIP | `kbd101` と `kbd106` で配列の判定値、TIP とエンジンの一致・不一致、旧版混在時の扱いを確認する。`kbd106` の TSF RichEdit と IMM の対象窓で、修飾を先に押す場合と本体を先に押す場合を二通りの解放順で試し、特殊キーの down/up と PreservedKey を確認する。通す修飾付き打鍵が別のモード切替に化けないこと、フォーカス切り替え、IME オフからの起動も確認する。新 MS-IME の標準テンプレートを参照し、半角/全角と英数の直後の確定・挿入をキー表と照合する |
| JIS 実機での受け入れ | JIS 固有キーを実際に打ち、自動リピート、Space の同時打鍵、各キーの打ち心地を確認する。JIS でも通常の [DESIGN の実地試験](DESIGN.md#9-実地試験) を通す |

Windows 側の確認には、ANSI 101 を接続して Windows を 106 設定にし、`keyprobe` で JIS 専用キーのスキャンコードを送る方法を使える。合成打鍵は対象窓を確認してから送る。NLS の仮想キーが押下状態に残る場合は、検証窓を英語入力に切り替え、残っている VK に解放を送ってから終了する。[keyprobe の使い方](../tools/keyprobe/README.md)

配列を追加したら、暖機・自己診断・かなから打鍵を作る評価・記録の配列名を同じプロファイルに通す。配布物に JIS の表が入り、32/64 ビットの TIP がそれぞれ既定表を読めることを確認する。利用者向けの README・USAGE には対象配列、Windows の設定、JIS の打ち方を記載する。
