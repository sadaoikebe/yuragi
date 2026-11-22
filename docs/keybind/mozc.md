# Google 日本語入力 / Mozc のキー設定

Google 日本語入力とそのオープンソース版 Mozc の、キー設定（keymap）の仕組み・コマンド・プリセットの内容と、プロパティ画面の設定項目・機能の一覧。
ソースは github.com/google/mozc の master。キーマップの TSV へのリンクは、それぞれのファイルを最後に変更したコミットに固定してある（§8）。
出典に無いものは「資料に無い」と書く。出典は §8 の略号で示す。

## 1. キー設定のプリセット

### 1.1 プリセットの一覧

| 内部名（`Config::SessionKeymap`） | 値 | ファイル | GUI の名前 | GUI で選べるか | 既定になる OS | 出典 |
|---|---|---|---|---|---|---|
| CUSTOM | 0 | `user://keymap.tsv`（実体は設定の `custom_keymap_table`） | カスタム | 選べる | — | [PROTO][KEYMAP-CC][CFG-CC] |
| ATOK | 1 | `system://atok.tsv` | ATOK | 選べる | — | 同上 |
| MSIME | 2 | `system://ms-ime.tsv` | MS-IME | 選べる | Windows・Linux など（下の 2 つ以外） | [HANDLER] |
| KOTOERI | 3 | `system://kotoeri.tsv` | ことえり | 選べる | macOS | [HANDLER] |
| MOBILE | 4 | `system://mobile.tsv` | — | 選べない（モバイル用） | — | [KM-README] |
| CHROMEOS | 5 | `system://chromeos.tsv` | — | 選べない | ChromeOS | [HANDLER] |
| OVERLAY_HENKAN_MUHENKAN_TO_IME_ON_OFF | 100 | `system://overlay_henkan_muhenkan_to_ime_on_off.tsv` | — | プロパティ画面には無い [CFG-CC] | — | [PROTO][OVL-COMMIT] |
| NONE | -1 | （OS の既定に置き換わる） | — | — | — | [PROTO] |

- 「旧ことえり」という別のプリセットは無い。ことえりは 1 つだけ。
- GUI の「キー設定の選択」には「カスタム / ATOK / MS-IME / ことえり」の 4 つが並ぶ [CFG-CC]。
- キー設定エディタの「定義済みのキーマップからインポート」で読み込めるのは ATOK / MS-IME / ことえり の 3 つ [EDITOR]。
- **overlay** は、基本のキーマップの上に重ねて一部だけ上書きする仕組み（`Config.overlay_keymaps`、複数を指定できる）。2023 年に、「デスクトップには編集画面があるが、モバイルには大げさすぎる。overlay でほとんどの要望をまかなう」という目的で入った [OVL-COMMIT][PROTO]。
- ChromeOS 版は MS-IME から、日本語キー（Eisu, Hankaku/Zenkaku, Henkan, Muhenkan, Hiragana, Katakana, Kanji, ON, OFF, F13）の行を**消しただけ**のもの（§4.3）。mobile は MS-IME と Ctrl+Backspace の 2 行だけ違う（§4.4）。

### 1.2 TSV の形式と読み込みの規則（[KEYMAP-CC]）

- 1 行目は見出し（`status\tkey\tcommand`）で、読み飛ばす。空行と `#` で始まる行も読み飛ばす。
- 各行はタブ区切りの 3 列: `状態 キー コマンド`。列が 3 つでない行はエラーとして無視する。
- 知らないコマンド名やキー名の行はエラーとして記録し、その行だけ無視する。
- 読み込みが終わると、次の規則が**暗黙に追加**される（TSV に書かなくても入る）:
  - Precomposition / Composition / Conversion の `TextInput`（＝印字できる文字キー）→ `InsertCharacter`
  - Composition の `Shift`（Shift 単独）→ `InsertCharacter`
  - Precomposition の `IME_ACTION` キー → IME_ACTION（モバイルの検索ボタン用）

  このため atok.tsv や kotoeri.tsv には `ASCII InsertCharacter` の行が無いが、文字は入力できる。
- 同じ（状態, キー）が 2 回出てきたときにどちらが効くかは資料に無い。kotoeri.tsv には `Composition Ctrl m Commit` がまったく同じ行で 2 回ある。
- 旧コマンド名 `InputModeHiragana` などは、読み込み時に `CompositionModeHiragana` などへ読み替えられる（後方互換）。旧名 `EditInsert` はエディタで非表示にする扱い [EDITOR]。
- `ReportBug` はリリースビルドでは読み込んでも無視される（デバッグ用）。
- 適用の順序: 基本のキーマップ（`session_keymap`。CUSTOM のときは設定に保存された表、空なら OS の既定）→ `overlay_keymaps` を順に重ねる。

### 1.3 状態（status）の一覧と、引けなかったときのフォールバック

| 状態名（TSV） | 和名（エディタ表示）[KM-JA] | 意味 [KM-README][DOC-CFG] | 使えるコマンドの集合 | 引けなかったときに見る表 [KEYMAP-CC] | エディタで選べるか |
|---|---|---|---|---|---|
| `DirectInput`（別名 `Direct`） | 直接入力 | IME がオフで、英字をそのまま打つ状態 | DirectInputState | （無し） | 選べる |
| `Precomposition` | 入力文字なし | IME はオンだが、まだ何も入力していない状態 | PrecompositionState | （無し） | 選べる |
| `ZeroQuerySuggestion` | — | 確定直後などに入力なしでサジェストが出ている状態（エディタの状態一覧には無い） | PrecompositionState | Precomposition | **選べない**（TSV に直接書けば効く） |
| `Composition` | 変換前入力中 | ひらがなを入力中（未変換） | CompositionState | （無し） | 選べる |
| `Suggestion` | サジェスト表示中 | Composition の一種。サジェストが出ているが、まだどの候補にもフォーカスしていない | CompositionState | Composition | 選べる |
| `Conversion` | 変換中 | Space で完全一致の候補を作り、漢字を選んでいる状態 | ConversionState | （無し） | 選べる |
| `Prediction` | サジェスト選択中 | Conversion の一種。Tab で前方一致（予測）の候補を作った状態 | ConversionState | Conversion | 選べる |

状態の遷移図は [MODES]（画面例は同じ場所の input_modes.png）[KM-README]。

## 2. コマンドの一覧（全コマンド）

状態の略号: **D**=DirectInput、**P**=Precomposition（ZeroQuerySuggestion を含む）、**C**=Composition（Suggestion を含む）、**V**=Conversion（Prediction を含む）。
「使える状態」は keymap.cc の `Register*Command` で登録されている状態。状態ごとに使えるコマンドが決まっていて、エディタはこれを検証する。和名は [KM-JA]、説明は keymap.h のコメント [KEYMAP-H] と和名による。

| コマンド名 | 和名（GUI） | 使える状態 | 説明 |
|---|---|---|---|
| `IMEOn` | IME を有効化 | D P C V | IME をオンにする。macOS では、エディタで非表示（ソースのコメントは「Mac では IME オン/オフのキー割り当てを変えられない」） |
| `IMEOff` | IME を無効化 | P C V | IME をオフにする。入力中の文字を確定するか消すかは資料に無い。macOS ではエディタで非表示 |
| `CancelAndIMEOff` | キャンセル後 IME を無効化 | P C V | 入力中の文字を捨ててから IME をオフにする（ATOK 風） |
| `CompositionModeHiragana` | ひらがなに入力切替 | D P C V | 入力モードをひらがなにする（D から使ったときに IME もオンになるかは資料に無い）。**Apple 系では何もしない（NONE）** |
| `CompositionModeFullKatakana` | 全角カタカナに入力切替 | D P C V | 同上（全角カタカナ） |
| `CompositionModeHalfKatakana` | 半角カタカナに入力切替 | D P C V | 同上（半角カタカナ） |
| `CompositionModeFullAlphanumeric` | 全角英数に入力切替 | D P C V | 同上（全角英数） |
| `CompositionModeHalfAlphanumeric` | 半角英数に入力切替 | D P C V | 同上（半角英数） |
| `CompositionModeSwitchKanaType` | 次のかな文字種に入力切替 | P | 入力モードを順に切り替える（ひらがな→カタカナ→…）。Apple 系では何もしない |
| `ToggleAlphanumericMode` | 英数入力切り替え | P C V | 英数モードとひらがなモードを切り替える |
| `Reconvert` | 再変換 | D P | 確定済みの文字（選んだ範囲）を再変換する |
| `InsertCharacter` | （非表示） | P C V | 文字を入力する。P では Composition へ移る。V では今の変換を確定してから入力を始める。エディタには出ない |
| `InsertSpace` | 空白を入力 | P C V | スペースを入力する（全角か半角かは「スペースの入力」の設定に従う） |
| `InsertAlternateSpace` | 代替空白文字を入力 | P C V | 設定と逆の幅のスペース（Shift+Space 用） |
| `InsertHalfSpace` | 半角空白を入力 | P C V | 必ず半角スペース |
| `InsertFullSpace` | 全角空白を入力 | P C V | 必ず全角スペース |
| `LaunchConfigDialog` | プロパティを起動 | P | 設定画面を開く |
| `LaunchDictionaryTool` | 辞書ツールを起動 | P | 辞書ツールを開く |
| `LaunchWordRegisterDialog` | 単語登録を起動 | P | 単語登録の画面を開く |
| `Revert` | 最後の学習をキャンセル | P | 直前の操作を取り消す。入力中の文字は戻らない（"preedit still remains"）。何の学習を取り消すかは資料に無い |
| `Undo` | 確定取り消し | P C V | 直前の確定を取り消し、確定前の入力中の文字に戻す（"preedit is restored"） |
| `Cancel` | キャンセル | P C V | C → 入力を捨てて Precomposition へ。V → 変換をやめて Composition へ戻る。P では ZeroQuerySuggestion 用（keymap.h のコメントは「Back to Composition status」。P での動作は資料に無い） |
| `CommitFirstSuggestion` | 最初の予測候補を確定 | P C | 最初のサジェスト候補を確定する（ATOK の Shift+Enter 風） |
| `PredictAndConvert` | 予測変換 | P C V | 予測候補（前方一致）を出して Prediction 状態に入る（Tab） |
| `Delete` | 右の文字を削除 | C | カーソルの右の 1 文字を消す |
| `Backspace` | 左の文字を削除 | C | カーソルの左の 1 文字を消す |
| `MoveCursorLeft` | カーソルを左に移動 | C | |
| `MoveCursorRight` | カーソルを右に移動 | C | |
| `MoveCursorToBeginning` | カーソルを左端に移動 | C | |
| `MoveCursorToEnd` | カーソルを右端に移動 | C | |
| `Commit` | 確定 | C V | 全部確定して Precomposition へ |
| `CommitOnlyFirstSegment` | 最初の文節のみを確定 | V | 先頭の文節だけ確定する（ATOK の ↓） |
| `Convert` | 変換 | C | 変換して Conversion へ移る |
| `ConvertWithoutHistory` | 学習を使わずに変換 | C | 学習結果を使わずに変換する（F2） |
| `ConvertToHiragana` | ひらがなに変換 | C V | ひらがなに変換して Conversion 状態にする（F6） |
| `ConvertToFullKatakana` | 全角カタカナに変換 | C V | 同上（F7） |
| `ConvertToHalfKatakana` | 半角カタカナに変換 | C V | 同上 |
| `ConvertToHalfWidth` | 半角に変換 | C V | 同上（F8）。押すたびに文字種が変わるかは資料に無い |
| `ConvertToFullAlphanumeric` | 全角英数に変換 | C V | 同上（F9） |
| `ConvertToHalfAlphanumeric` | 半角英数に変換 | C V | 同上（F10） |
| `SwitchKanaType` | ひらがな・カタカナを切替 | C V | 入力中の文字の文字種を順に切り替える（MS-IME の無変換キー） |
| `DisplayAsHiragana` | ひらがなに表示切替 | C V | C では**状態を Composition のまま**表示だけひらがなにする（Mac のことえり風 Ctrl+J）。V では ConvertTo* と同じ動作 |
| `DisplayAsFullKatakana` | 全角カタカナに表示切替 | C V | 同上 |
| `DisplayAsHalfKatakana` | 半角カタカナに表示切替 | C V | 同上 |
| `DisplayAsHalfWidth` | 半角に表示切替 | C V | 同上 |
| `DisplayAsFullAlphanumeric` | 全角英数に表示切替 | C V | 同上 |
| `DisplayAsHalfAlphanumeric` | 半角英数に表示切替 | C V | 同上 |
| `SegmentFocusLeft` | 文節を左に移動 | V | 注目する文節を 1 つ左へ |
| `SegmentFocusRight` | 文節を右に移動 | V | 注目する文節を 1 つ右へ |
| `SegmentFocusFirst` | 文節を左端に移動 | V | |
| `SegmentFocusLast` | 文節を右端に移動 | V | |
| `SegmentWidthExpand` | 文節を伸ばす | V | |
| `SegmentWidthShrink` | 文節を縮める | V | |
| `ConvertNext` | 次候補を選択 | V | |
| `ConvertPrev` | 前候補を選択 | V | |
| `ConvertNextPage` | 次候補ページを選択 | V | |
| `ConvertPrevPage` | 前候補ページを選択 | V | |
| `DeleteSelectedCandidate` | 選択候補を履歴から削除 | V | 選んでいる候補を学習・入力履歴から消す（Prediction の Ctrl+Delete） |
| `ReportBug` | （非表示） | V | デバッグビルドだけ。エディタには出ない |

内部コマンド: `IME_ACTION`（P。`imeaction` キー。TSV のコマンド名としては登録されておらず、暗黙で追加される）。

### 2.1 ConvertTo* と DisplayAs* の違い（[KEYMAP-H] のコメント）

- CompositionState の enum は、`CONVERT_TO_*` を「Switching to ConversionState」（Conversion に移る）、`DISPLAY_AS_*` / `TRANSLATE_*` を「Remaining CompositionState」（Composition のまま）と分けている。
- ConversionState では「CONVERT_TO と TRANSLATE は同じ動作」とコメントがある。
- MS-IME は F6〜F10 / Ctrl+U/I/O/P/T、ATOK は F6〜F10 / Ctrl+U/I/O/P/@ を ConvertTo* に、ことえりは F6〜F10 / Ctrl+J/K/L/;/: を DisplayAs* に割り当てている。

## 3. キーの表記（[KEYPARSER]）

キーの欄は、空白で区切った語の並び（例: `Ctrl Shift Space`）。大文字小文字は区別しない。1 文字の語は文字キー（その文字のコードポイント）として扱う。1 つの欄に書ける文字キーと特殊キーは、それぞれ 1 つまで。

| 種類 | 書き方（別名） |
|---|---|
| 修飾キー | `Ctrl`(`Control`), `Alt`(`Option`, `Meta`, `Super`, `Hyper` はすべて ALT 扱い), `Shift`, `Caps`, `LeftCtrl`, `RightCtrl`, `LeftAlt`, `RightAlt`, `LeftShift`, `RightShift`（左右つきは汎用のフラグも立てる）, `KeyDown`, `KeyUp`（エディタでは非表示） |
| 文字入力全般 | `TextInput`（`ASCII` は非推奨の別名）＝印字できる文字キーすべて |
| 文字キー | `a`, `;`, `:`, `'`, `[`, `@` など 1 文字（kotoeri.tsv の `Ctrl ;`、atok.tsv の `Ctrl [` `Ctrl @` など） |
| 移動・編集 | `Left` `Right` `Up` `Down` `Home` `End` `PageUp` `PageDown` `Insert` `Delete`(`Del`) `Backspace`(`BS`) `Enter`(`Return`) `ESC`(`Escape`) `Tab` `Space` `Clear` |
| 日本語キー | `Henkan`, `Muhenkan`, `Kana`(`Hiragana`), `Katakana`, `Eisu`, `Hankaku/Zenkaku`(`Hankaku`, `Zenkaku`), `Kanji`, `ON`, `OFF` |
| ファンクション | `F1`〜`F24` |
| テンキー | `Numpad0`〜`Numpad9`, `Multiply`, `Add`, `Separator`, `Subtract`, `Decimal`, `Divide`, `Equals`, `Comma` |
| 仮想キー（モバイル用） | `VirtualLeft`, `VirtualRight`, `VirtualEnter`, `VirtualUp`, `VirtualDown`, `IMEAction`, `UndefinedKey` |

書き出すときの正規の名前: DEL は `delete`、KANA は `hiragana`、HANKAKU は `hankaku/zenkaku`。そのほかは enum 名から `_` を除いて小文字にしたもの（例: PAGE_UP → `pageup`）。

エディタで**表示されない**キー: `Kanji`, `ON`, `OFF`, `TextInput`、および修飾キーに `KeyDown`/`KeyUp` を含むもの [EDITOR]。表示されない行は捨てずに保持され、保存するときに書き戻される（`invisible_keymap_table_`）。

## 4. 各プリセットの内容

### 4.1 3 プリセットの比較表（MS-IME / ATOK / ことえり）

[MSIME][ATOK][KOTO] の全行を状態ごとに並べたもの。「—」はそのプリセットに割り当てが無いことを表す（Suggestion/Prediction では、その場合 Composition/Conversion の割り当てが使われる）。TextInput→InsertCharacter の暗黙規則は表に入れていない。MS-IME の `ASCII` の行は ms-ime.tsv に明示されている行。

#### DirectInput

| キー | MS-IME | ATOK | ことえり |
|---|---|---|---|
| `Ctrl Shift r` | — | — | Reconvert |
| `Eisu` | IMEOn | — | — |
| `F13` | IMEOn | — | — |
| `Hankaku/Zenkaku` | IMEOn | IMEOn | IMEOn |
| `Henkan` | Reconvert | IMEOn | — |
| `Hiragana` | IMEOn | — | — |
| `Kanji` | IMEOn | IMEOn | IMEOn |
| `Katakana` | IMEOn | — | — |
| `Muhenkan` | — | IMEOn | — |
| `ON` | IMEOn | IMEOn | IMEOn |
| `Shift Henkan` | — | Reconvert | — |

#### Precomposition

| キー | MS-IME | ATOK | ことえり |
|---|---|---|---|
| `ASCII` | InsertCharacter | — | — |
| `Backspace` | Revert | Revert | Revert |
| `Ctrl Backspace` | Undo | Undo | Undo |
| `Ctrl F12` | — | LaunchConfigDialog | — |
| `Ctrl F7` | — | LaunchWordRegisterDialog | — |
| `Ctrl Shift r` | — | — | Reconvert |
| `Ctrl Shift Space` | InsertFullSpace | — | — |
| `Eisu` | ToggleAlphanumericMode | ToggleAlphanumericMode | ToggleAlphanumericMode |
| `F10` | — | ToggleAlphanumericMode | — |
| `Hankaku/Zenkaku` | IMEOff | CancelAndIMEOff | IMEOff |
| `Henkan` | Reconvert | CancelAndIMEOff | — |
| `Hiragana` | CompositionModeHiragana | — | — |
| `Kana` | — | ToggleAlphanumericMode | — |
| `Kanji` | IMEOff | CancelAndIMEOff | IMEOff |
| `Katakana` | CompositionModeFullKatakana | — | — |
| `Muhenkan` | CompositionModeSwitchKanaType | CancelAndIMEOff | — |
| `OFF` | IMEOff | CancelAndIMEOff | IMEOff |
| `ON` | IMEOn | IMEOn | IMEOn |
| `Shift Henkan` | — | Reconvert | — |
| `Shift Muhenkan` | ToggleAlphanumericMode | ToggleAlphanumericMode | — |
| `Shift Space` | InsertAlternateSpace | InsertAlternateSpace | InsertAlternateSpace |
| `Space` | InsertSpace | InsertSpace | InsertSpace |

#### Composition

| キー | MS-IME | ATOK | ことえり |
|---|---|---|---|
| `ASCII` | InsertCharacter | — | — |
| `Backspace` | Backspace | Backspace | Backspace |
| `Ctrl '` | — | — | DisplayAsHalfAlphanumeric |
| `Ctrl :` | — | — | DisplayAsHalfAlphanumeric |
| `Ctrl ;` | — | — | DisplayAsHalfWidth |
| `Ctrl @` | — | ConvertToHalfAlphanumeric | — |
| `Ctrl [` | — | Cancel | — |
| `Ctrl a` | MoveCursorToBeginning | — | MoveCursorToBeginning |
| `Ctrl b` | — | — | MoveCursorLeft |
| `Ctrl Backspace` | Backspace | — | — |
| `Ctrl d` | MoveCursorRight | — | Delete |
| `Ctrl Down` | MoveCursorToEnd | — | — |
| `Ctrl e` | MoveCursorToBeginning | — | MoveCursorToEnd |
| `Ctrl Enter` | Commit | — | — |
| `Ctrl f` | MoveCursorToEnd | — | MoveCursorRight |
| `Ctrl g` | Delete | Delete | Cancel |
| `Ctrl h` | Backspace | Backspace | Backspace |
| `Ctrl i` | ConvertToFullKatakana | ConvertToFullKatakana | — |
| `Ctrl j` | — | — | DisplayAsHiragana |
| `Ctrl k` | MoveCursorLeft | MoveCursorLeft | DisplayAsFullKatakana |
| `Ctrl l` | MoveCursorRight | MoveCursorRight | DisplayAsFullAlphanumeric |
| `Ctrl Left` | MoveCursorToBeginning | MoveCursorToBeginning | MoveCursorToBeginning |
| `Ctrl m` | Commit | Commit | Commit |
| `Ctrl n` | MoveCursorToEnd | Commit | — |
| `Ctrl o` | ConvertToHalfWidth | ConvertToHalfWidth | — |
| `Ctrl p` | ConvertToFullAlphanumeric | ConvertToFullAlphanumeric | — |
| `Ctrl Right` | MoveCursorToEnd | MoveCursorToEnd | MoveCursorToEnd |
| `Ctrl s` | MoveCursorLeft | — | — |
| `Ctrl Shift Space` | InsertFullSpace | — | — |
| `Ctrl Space` | InsertHalfSpace | Convert | — |
| `Ctrl t` | ConvertToHalfAlphanumeric | — | — |
| `Ctrl u` | ConvertToHiragana | ConvertToHiragana | — |
| `Ctrl Up` | MoveCursorToBeginning | — | — |
| `Ctrl x` | MoveCursorToEnd | — | — |
| `Ctrl z` | Cancel | — | — |
| `Delete` | Delete | Delete | Delete |
| `Down` | MoveCursorToEnd | Commit | — |
| `Eisu` | ToggleAlphanumericMode | ToggleAlphanumericMode | ToggleAlphanumericMode |
| `End` | MoveCursorToEnd | — | MoveCursorToEnd |
| `Enter` | Commit | Commit | Commit |
| `ESC` | Cancel | Cancel | Cancel |
| `F10` | ConvertToHalfAlphanumeric | ConvertToHalfAlphanumeric | DisplayAsHalfAlphanumeric |
| `F2` | ConvertWithoutHistory | ConvertWithoutHistory | ConvertWithoutHistory |
| `F6` | ConvertToHiragana | ConvertToHiragana | DisplayAsHiragana |
| `F7` | ConvertToFullKatakana | ConvertToFullKatakana | DisplayAsFullKatakana |
| `F8` | ConvertToHalfWidth | ConvertToHalfWidth | DisplayAsHalfWidth |
| `F9` | ConvertToFullAlphanumeric | ConvertToFullAlphanumeric | DisplayAsFullAlphanumeric |
| `Hankaku/Zenkaku` | IMEOff | CancelAndIMEOff | IMEOff |
| `Henkan` | Convert | Convert | — |
| `Hiragana` | CompositionModeHiragana | ToggleAlphanumericMode | — |
| `Home` | MoveCursorToBeginning | — | MoveCursorToBeginning |
| `Kana` | — | ToggleAlphanumericMode | — |
| `Kanji` | IMEOff | CancelAndIMEOff | IMEOff |
| `Katakana` | CompositionModeFullKatakana | — | — |
| `Left` | MoveCursorLeft | MoveCursorLeft | MoveCursorLeft |
| `Muhenkan` | SwitchKanaType | ToggleAlphanumericMode | — |
| `OFF` | IMEOff | CancelAndIMEOff | IMEOff |
| `ON` | IMEOn | IMEOn | IMEOn |
| `Option a` | — | — | DisplayAsHalfWidth |
| `Option c` | — | — | DisplayAsFullAlphanumeric |
| `Option F1` | — | — | DisplayAsHiragana |
| `Option F2` | — | — | DisplayAsFullKatakana |
| `Option F3` | — | — | DisplayAsFullAlphanumeric |
| `Option F4` | — | — | DisplayAsHalfWidth |
| `Option F5` | — | — | DisplayAsHalfAlphanumeric |
| `Option j` | — | — | MoveCursorLeft |
| `Option l` | — | — | MoveCursorRight |
| `Option s` | — | — | DisplayAsHalfAlphanumeric |
| `Option Space` | — | — | InsertFullSpace |
| `Option x` | — | — | DisplayAsFullKatakana |
| `Option z` | — | — | DisplayAsHiragana |
| `Right` | MoveCursorRight | MoveCursorRight | MoveCursorRight |
| `Shift Backspace` | Backspace | — | — |
| `Shift ESC` | Cancel | — | — |
| `Shift Henkan` | — | Convert | — |
| `Shift Left` | MoveCursorLeft | — | — |
| `Shift Muhenkan` | ConvertToFullAlphanumeric | ToggleAlphanumericMode | — |
| `Shift Right` | MoveCursorRight | — | — |
| `Shift Space` | Convert | Convert | — |
| `Space` | Convert | Convert | Convert |
| `Tab` | PredictAndConvert | PredictAndConvert | PredictAndConvert |
| `VirtualEnter` | Commit | Commit | Commit |
| `VirtualLeft` | MoveCursorLeft | MoveCursorLeft | MoveCursorLeft |
| `VirtualRight` | MoveCursorRight | MoveCursorRight | MoveCursorRight |

#### Suggestion

| キー | MS-IME | ATOK | ことえり |
|---|---|---|---|
| `Ctrl Down` | — | PredictAndConvert | — |
| `Ctrl Enter` | — | CommitFirstSuggestion | — |
| `Ctrl n` | — | — | PredictAndConvert |
| `Down` | PredictAndConvert | PredictAndConvert | PredictAndConvert |
| `Shift Enter` | CommitFirstSuggestion | CommitFirstSuggestion | CommitFirstSuggestion |

#### Conversion

| キー | MS-IME | ATOK | ことえり |
|---|---|---|---|
| `Backspace` | Cancel | Cancel | Cancel |
| `Ctrl '` | — | — | DisplayAsHalfAlphanumeric |
| `Ctrl :` | — | — | DisplayAsHalfAlphanumeric |
| `Ctrl ;` | — | — | DisplayAsHalfWidth |
| `Ctrl @` | — | ConvertToHalfAlphanumeric | — |
| `Ctrl [` | — | Cancel | — |
| `Ctrl a` | SegmentFocusFirst | — | SegmentFocusFirst |
| `Ctrl b` | — | — | SegmentFocusLeft |
| `Ctrl Backspace` | Cancel | — | — |
| `Ctrl d` | SegmentFocusRight | — | SegmentFocusRight |
| `Ctrl Down` | CommitOnlyFirstSegment | — | — |
| `Ctrl e` | ConvertPrev | — | ConvertPrev |
| `Ctrl Enter` | Commit | — | — |
| `Ctrl f` | SegmentFocusLast | — | SegmentFocusRight |
| `Ctrl g` | Cancel | — | — |
| `Ctrl h` | Cancel | Cancel | Cancel |
| `Ctrl i` | ConvertToFullKatakana | ConvertToFullKatakana | SegmentWidthShrink |
| `Ctrl j` | — | — | DisplayAsHiragana |
| `Ctrl k` | SegmentWidthShrink | SegmentWidthShrink | DisplayAsFullKatakana |
| `Ctrl l` | SegmentWidthExpand | SegmentWidthExpand | DisplayAsFullAlphanumeric |
| `Ctrl Left` | SegmentFocusFirst | SegmentFocusFirst | SegmentFocusFirst |
| `Ctrl m` | Commit | Commit | Commit |
| `Ctrl n` | CommitOnlyFirstSegment | CommitOnlyFirstSegment | ConvertNext |
| `Ctrl o` | ConvertToHalfWidth | ConvertToHalfWidth | SegmentWidthExpand |
| `Ctrl p` | ConvertToFullAlphanumeric | ConvertToFullAlphanumeric | ConvertPrev |
| `Ctrl q` | — | — | SegmentWidthShrink |
| `Ctrl Right` | SegmentFocusLast | SegmentFocusLast | SegmentFocusLast |
| `Ctrl s` | SegmentFocusLeft | — | SegmentFocusLeft |
| `Ctrl Shift Left` | — | SegmentWidthShrink | — |
| `Ctrl Shift Right` | — | SegmentWidthExpand | — |
| `Ctrl Shift Space` | InsertFullSpace | — | — |
| `Ctrl Space` | InsertHalfSpace | ConvertNext | — |
| `Ctrl t` | ConvertToHalfAlphanumeric | — | — |
| `Ctrl u` | ConvertToHiragana | ConvertToHiragana | — |
| `Ctrl Up` | ConvertPrev | — | — |
| `Ctrl w` | — | — | SegmentWidthExpand |
| `Ctrl x` | ConvertNext | — | ConvertNext |
| `Ctrl z` | Cancel | — | — |
| `Delete` | Cancel | — | — |
| `Down` | ConvertNext | CommitOnlyFirstSegment | ConvertNext |
| `Eisu` | ToggleAlphanumericMode | ToggleAlphanumericMode | — |
| `End` | SegmentFocusLast | — | SegmentFocusLast |
| `Enter` | Commit | Commit | Commit |
| `ESC` | Cancel | Cancel | Cancel |
| `F1` | ReportBug | ReportBug | ReportBug |
| `F10` | ConvertToHalfAlphanumeric | ConvertToHalfAlphanumeric | DisplayAsHalfAlphanumeric |
| `F3` | ReportBug | ReportBug | ReportBug |
| `F6` | ConvertToHiragana | ConvertToHiragana | DisplayAsHiragana |
| `F7` | ConvertToFullKatakana | ConvertToFullKatakana | DisplayAsFullKatakana |
| `F8` | ConvertToHalfWidth | ConvertToHalfWidth | DisplayAsHalfWidth |
| `F9` | ConvertToFullAlphanumeric | ConvertToFullAlphanumeric | DisplayAsFullAlphanumeric |
| `Hankaku/Zenkaku` | IMEOff | CancelAndIMEOff | IMEOff |
| `Henkan` | ConvertNext | ConvertNextPage | — |
| `Hiragana` | CompositionModeHiragana | ToggleAlphanumericMode | — |
| `Home` | SegmentFocusFirst | — | SegmentFocusFirst |
| `Insert` | — | Cancel | — |
| `Kanji` | IMEOff | CancelAndIMEOff | IMEOff |
| `Katakana` | CompositionModeFullKatakana | — | — |
| `Left` | SegmentFocusLeft | SegmentWidthShrink | SegmentFocusLeft |
| `Muhenkan` | SwitchKanaType | — | — |
| `OFF` | IMEOff | CancelAndIMEOff | IMEOff |
| `ON` | IMEOn | IMEOn | IMEOn |
| `Option a` | — | — | DisplayAsHalfWidth |
| `Option c` | — | — | DisplayAsFullAlphanumeric |
| `Option F1` | — | — | DisplayAsHiragana |
| `Option F2` | — | — | DisplayAsFullKatakana |
| `Option F3` | — | — | DisplayAsFullAlphanumeric |
| `Option F4` | — | — | DisplayAsHalfWidth |
| `Option F5` | — | — | DisplayAsHalfAlphanumeric |
| `Option i` | — | — | ConvertPrev |
| `Option k` | — | — | ConvertNext |
| `Option s` | — | — | DisplayAsHalfAlphanumeric |
| `Option x` | — | — | DisplayAsFullKatakana |
| `Option z` | — | — | DisplayAsHiragana |
| `PageDown` | ConvertNextPage | — | ConvertNextPage |
| `PageUp` | ConvertPrevPage | — | ConvertPrevPage |
| `Right` | SegmentFocusRight | SegmentWidthExpand | SegmentFocusRight |
| `Shift Backspace` | Cancel | — | — |
| `Shift Down` | ConvertNextPage | — | ConvertNextPage |
| `Shift ESC` | Cancel | — | — |
| `Shift Henkan` | ConvertPrev | ConvertPrevPage | — |
| `Shift Left` | SegmentWidthShrink | SegmentFocusLeft | SegmentWidthShrink |
| `Shift Muhenkan` | ConvertToFullAlphanumeric | — | — |
| `Shift Right` | SegmentWidthExpand | SegmentFocusRight | SegmentWidthExpand |
| `Shift Space` | ConvertPrev | ConvertNext | ConvertPrev |
| `Shift Tab` | ConvertPrev | ConvertPrev | ConvertPrev |
| `Shift Up` | ConvertPrevPage | — | ConvertPrevPage |
| `Space` | ConvertNext | ConvertNext | ConvertNext |
| `Tab` | PredictAndConvert | PredictAndConvert | PredictAndConvert |
| `Up` | ConvertPrev | ConvertPrev | ConvertPrev |
| `VirtualEnter` | CommitOnlyFirstSegment | CommitOnlyFirstSegment | CommitOnlyFirstSegment |
| `VirtualLeft` | SegmentWidthShrink | SegmentWidthShrink | SegmentWidthShrink |
| `VirtualRight` | SegmentWidthExpand | SegmentWidthExpand | SegmentWidthExpand |

#### Prediction

| キー | MS-IME | ATOK | ことえり |
|---|---|---|---|
| `Ctrl Delete` | DeleteSelectedCandidate | DeleteSelectedCandidate | DeleteSelectedCandidate |
| `Ctrl Down` | — | ConvertNext | — |
| `Ctrl Up` | — | ConvertPrev | — |
| `Down` | — | ConvertNext | — |
| `Up` | — | ConvertPrev | — |

### 4.2 ファイル

ファイルはすべて [KM-DIR] にある。各略号のリンクは、そのファイルを最後に変更したコミットに固定してある（§8）。

| プリセット | ファイル | 備考 |
|---|---|---|
| MS-IME | [MSIME] | Windows・Linux の既定 |
| ATOK | [ATOK] | |
| ことえり | [KOTO] | macOS の既定 |
| ChromeOS | [CROS] | §4.3 |
| mobile | [MOB] | §4.4 |
| overlay | [OVL] | §4.5 |

### 4.3 chromeos.tsv（MS-IME との差分）[CROS]

chromeos.tsv は ms-ime.tsv から次の 39 行を**消した**もの。追加・変更した行は無い。

```tsv
Composition	Eisu	ToggleAlphanumericMode
Composition	Hankaku/Zenkaku	IMEOff
Composition	Henkan	Convert
Composition	Hiragana	CompositionModeHiragana
Composition	Kanji	IMEOff
Composition	Katakana	CompositionModeFullKatakana
Composition	Muhenkan	SwitchKanaType
Composition	OFF	IMEOff
Composition	ON	IMEOn
Composition	Shift Muhenkan	ConvertToFullAlphanumeric
Conversion	Eisu	ToggleAlphanumericMode
Conversion	Hankaku/Zenkaku	IMEOff
Conversion	Henkan	ConvertNext
Conversion	Hiragana	CompositionModeHiragana
Conversion	Kanji	IMEOff
Conversion	Katakana	CompositionModeFullKatakana
Conversion	Muhenkan	SwitchKanaType
Conversion	OFF	IMEOff
Conversion	ON	IMEOn
Conversion	Shift Henkan	ConvertPrev
Conversion	Shift Muhenkan	ConvertToFullAlphanumeric
DirectInput	Eisu	IMEOn
DirectInput	F13	IMEOn
DirectInput	Hankaku/Zenkaku	IMEOn
DirectInput	Henkan	Reconvert
DirectInput	Hiragana	IMEOn
DirectInput	Kanji	IMEOn
DirectInput	Katakana	IMEOn
DirectInput	ON	IMEOn
Precomposition	Eisu	ToggleAlphanumericMode
Precomposition	Hankaku/Zenkaku	IMEOff
Precomposition	Hiragana	CompositionModeHiragana
Precomposition	Henkan	Reconvert
Precomposition	Kanji	IMEOff
Precomposition	Katakana	CompositionModeFullKatakana
Precomposition	Muhenkan	CompositionModeSwitchKanaType
Precomposition	OFF	IMEOff
Precomposition	ON	IMEOn
Precomposition	Shift Muhenkan	ToggleAlphanumericMode
```

### 4.4 mobile.tsv（MS-IME との差分）[MOB]

変わるのは次の 2 行だけ。ほかは ms-ime.tsv と同じ。

| 状態 | キー | MS-IME | mobile |
|---|---|---|---|
| Composition | `Ctrl Backspace` | Backspace | Undo |
| Conversion | `Ctrl Backspace` | Cancel | Undo |

### 4.5 overlay_henkan_muhenkan_to_ime_on_off.tsv [OVL]

ファイルの中身は次のとおり。

```tsv
# Overlay to use Henkan as IMEOn key, and Muhenkan as IMEOff key
Composition	Henkan	IMEOn
Conversion	Henkan	IMEOn
DirectInput	Henkan	IMEOn
Precomposition	Henkan	IMEOn

Composition	Muhenkan	IMEOff
Conversion	Muhenkan	IMEOff
Precomposition	Muhenkan	IMEOff
```

## 5. キー設定エディタ（GUI）の仕様

| 項目 | 内容 | 出典 |
|---|---|---|
| 開き方 | プロパティ › 一般 › キー設定 › 「キー設定の選択」で選び、「編集...」を押す | [H-GEN][CFG-JA][DOC-CFG] |
| ウインドウ名 | 「[ProductName] キー設定」 | [KM-JA] |
| 列 | 「モード」（状態）／「入力キー」／「コマンド」。モードとコマンドはコンボボックスで選び、キーは「キーバインディング 設定」ダイアログで実際に押して入れる（「割り当てるキーの入力:」） | [EDITOR][CFG-JA] |
| 選べる状態 | DirectInput, Precomposition, Composition, Conversion, Suggestion, Prediction の 6 つ（ZeroQuerySuggestion は無い） | [EDITOR] |
| メニュー | 新しいエントリー／選択されたエントリーを削除／定義済みのキーマップからインポート（ATOK・MS-IME・ことえり）／インポート...／エクスポート... | [EDITOR][H-GEN] |
| プリセットを編集したとき | ATOK などを選んだ状態で「編集...」を押すと、その内容を元に編集が始まり、保存すると「カスタム」になる（@IT の手順では、ベースを選んでから編集） | [ITM]（細かい動作は資料に無い） |
| インポート/エクスポートの形式 | 上の TSV と同じ（見出し行 `status\tkey\tcommand` ＋ 行）。インポートできるファイルは 100KB 未満 | [EDITOR][CFG-JA]「ファイルサイズが大きすぎて読み込めません」 |
| 保存先 | 設定（`config1.db`、protobuf）の `custom_keymap_table` に TSV のまま入る。Linux では `~/.config/mozc/config1.db` | [PROTO][DOC-CFG] |
| 検証 | 無効なキーは「無効な入力キーです: %1」。カスタムの表が空だと「有効なキー設定がありません」と警告する | [CFG-JA] |
| DirectInput の注意 | 「直接入力モードに対するキーマップの変更は、新しいアプリケーションから有効になります」 | [CFG-JA] |
| 非表示のコマンド | `InsertCharacter`, `ReportBug`, `EditInsert`（旧名）。macOS ではさらに `IMEOn`/`IMEOff` | [EDITOR] |
| 登録できる行数の上限 | 「%1 個以上のエントリーは登録できません」というメッセージがある。上限の値は資料に無い | [CFG-JA] |

## 6. プロパティ画面（設定）の全項目

タブの構成は「一般 / 辞書 / 入力補助 / サジェスト / プライバシー / その他」（Windows の場合）[H-GEN][H-DIC][H-ASSIST][H-SUG][H-PRIV][H-MISC][CFG-JA]。
config.proto の項目名と既定値は [PROTO] による。

### 6.1 一般

| 項目（GUI） | 選択肢 [CFG-CC][CFG-JA] | config.proto（既定値） |
|---|---|---|
| ローマ字入力・かな入力 | ローマ字入力 / かな入力 / ローマ字入力（切替可）/ かな入力（切替可）。「切替可」は Windows だけで、かなキーで入力方法を切り替えられる [H-GEN] | `preedit_method`（ROMAN）、`use_keyboard_to_change_preedit_method`（false） |
| 句読点 | 、。 / ，． / 、． / ，。 | `punctuation_method`（TOUTEN_KUTEN） |
| 記号 | 「」・ / []／ / 「」／ / []・ | `symbol_method`（CORNER_BRACKET_MIDDLE_DOT） |
| スペースの入力 | 入力モードに従う / 全角 / 半角 | `space_character_form`（FUNDAMENTAL_INPUT_MODE） |
| ¥キーで入力する文字（Mac のみ） | 円記号(¥) / バックスラッシュ(\) | `yen_sign_character`（YEN_SIGN） |
| 候補選択ショートカット | なし / 1 -- 9 / A -- L | `selection_shortcut`（SHORTCUT_123456789） |
| テンキーからの入力 | 入力モードに従う / 全角 / 半角 / 直接入力 | `numpad_character_form`（NUMPAD_HALF_WIDTH） |
| キー設定の選択 | カスタム / ATOK / MS-IME / ことえり ＋「編集...」 | `session_keymap`（NONE → OS の既定）、`custom_keymap_table` |
| 日本語入力では常に日本語キー配列を使う（Mac） | チェック | `use_japanese_layout`（false） |
| ローマ字テーブル | 「編集...」で表を編集（列は「入力」「出力」「次の入力」。インポート/エクスポート/初期値に戻す） | `custom_roman_table` |
| （画面に出ない） | — | `overlay_keymaps`（空） |

### 6.2 辞書

| 項目 | 内容 [H-DIC] | config.proto（既定値） |
|---|---|---|
| 学習機能 | 有効 / 有効（新規学習はしない）/ 無効 ＋「学習履歴のクリア」 | `history_learning_level`（DEFAULT_HISTORY） |
| ユーザ辞書の編集... | 辞書ツールを開く | — |
| 単漢字変換 | 単漢字辞書 | `use_single_kanji_conversion`（true） |
| 記号変換 | 記号辞書 | `use_symbol_conversion`（true） |
| 顔文字変換 | 顔文字辞書 | `use_emoticon_conversion`（true） |
| 絵文字変換 | | `use_emoji_conversion`（false。OS によっては true） |
| カタカナ英語変換 | 「ぐーぐる」→ Google | `use_t13n_conversion`（true） |
| 郵便番号変換 | | `use_zip_code_conversion`（true） |
| 日付変換 | 「きょう」「あした」 | `use_date_conversion`（true） |
| 特殊数字変換 | 「１２３」→ 壱百弐拾参 など | `use_number_conversion`（true） |
| 計算機機能 | 「1+1=」→ 2 | `use_calculator`（true） |
| 「もしかして」変換 | 誤入力の訂正候補 | `use_spelling_correction`（true） |
| 用例辞書 / 同音異義語辞書 | | `information_list_config.use_local_usage_dictionary`（true） |

### 6.3 入力補助

| 項目 | 内容 [H-ASSIST] | config.proto（既定値） |
|---|---|---|
| 自動英数変換を有効にする | 「ｈっｔｐ」→ http | `auto_switch_composition_mode`（true） |
| 句読点変換を有効にする（、 。 ？ ！ を個別に選ぶ） | 句読点の入力で変換する | `use_auto_conversion`（false）、`auto_conversion_key`（13 ＝ KUTEN(1)＋？(4)＋！(8)。ビットの組み合わせ） |
| シフトキーでの入力切替 | オフ / 英数字（MS-IME・ATOK 風）/ カタカナ（ことえり風） | `shift_key_mode_switch`（ASCII_INPUT_MODE） |
| 半角・全角 | 文字グループごとに「変換前文字列」「変換中文字列」を 全角/半角/学習 から選ぶ | `character_form_rules` |
| カーソル周辺に入力モードを表示する | | `use_mode_indicator`（true） |
| （画面に出ない） | 「かつこう→学校」のようなかなの修飾を無視する変換、タイプミスの訂正 | `use_kana_modifier_insensitive_conversion`（false）、`use_typing_correction`（false） |

### 6.4 サジェスト

| 項目 | 内容 [H-SUG] | config.proto（既定値） |
|---|---|---|
| 入力履歴からのサジェスト自動表示 | ＋「未使用の履歴を削除」「全入力履歴を削除」 | `use_history_suggest`（true） |
| システム辞書からのサジェスト自動表示 | | `use_dictionary_suggest`（true） |
| リアルタイム変換を有効にする | 入力途中で変換した結果をサジェストに出す | `use_realtime_conversion`（true） |
| サジェストの最大候補数 | | `suggestions_size`（3） |

### 6.5 プライバシー・その他

| 項目 | 内容 | config.proto（既定値） |
|---|---|---|
| シークレットモード | 一時的に、学習・入力履歴からのサジェスト・ユーザ辞書を無効にする [CFG-JA][H-PRIV] | `incognito_mode`（false） |
| プレゼンテーションモード | 一時的にすべてのサジェストを無効にする [CFG-JA] | `presentation_mode`（false） |
| 使用統計情報と障害レポート | 送信の可否 [H-PRIV] | （`general_config.upload_usage_stats` は Android だけ） |
| 起動時に既定の IME か確認する | [H-MISC] | `check_default`（true） |
| ホットキー(Ctrl+Shift)による IME の切り替えを無効化する（Windows） | [H-MISC] | （config.proto には無い） |
| オンメモリ辞書と UAC の設定（管理者） | 辞書を物理メモリに置く／UAC で昇格したアプリでは無効にする [H-MISC] | — |
| ログイン時に変換エンジンを起動する、ログレベル | [CFG-JA] | `verbose_level` |
| 初期値に戻す | 学習履歴・入力履歴・使用統計・管理者設定は戻らない [CFG-JA] | — |

## 7. Google 日本語入力の機能一覧

| 機能 | 内容 | 出典 |
|---|---|---|
| サジェスト | 入力の途中で、入力履歴・システム辞書・リアルタイム変換から候補を出す。Tab または ↓ で選び、Enter で確定するか、そのまま入力を続けて確定する | [H-SUG][H-BASIC] |
| Tab で予測 | 入力中に Tab で予測（`PredictAndConvert`）を始め、より多くの候補を出す | [H-BASIC] |
| 変換 | Space で変換し、候補を出す | [H-BASIC] |
| Web 由来の辞書 | Google の検索技術から作った大きな辞書と、「もしかして」の訂正 | [FEAT][H-ABOUT] |
| 特殊変換 | 絵文字・顔文字・カタカナ英語・郵便番号→住所・日付（「きょう」）・計算（「=」で終える）・特殊数字・記号・単漢字 | [FEAT][H-DIC] |
| 日付の書式の追加（Mozc） | ユーザ辞書に `DATE_FORMAT` / `DATETIME_FORMAT` を登録して増やす（試験的な機能） | [DOC-CFG] |
| バージョン表示 | 「ばーじょん」を変換する | [H-FAQ] |
| 自動英数変換 | URL などを自動で英字にする | [H-ASSIST][H-ABOUT] |
| 句読点変換 | 、。？！ の入力で変換する | [H-ASSIST] |
| ローマ字テーブル編集 | 入力 / 出力 / 次の入力 の 3 列（Mozc の preedit テーブル形式） | [CFG-JA] |
| 句読点・記号の種類 | 4 通りずつ（§6.1） | [CFG-CC] |
| 確定取り消し | `Undo`（MS-IME 系は Precomposition の Ctrl+Backspace） | [MSIME] |
| 選択候補を履歴から削除 | Prediction の Ctrl+Delete（`DeleteSelectedCandidate`） | [MSIME] |
| シークレットモード / プレゼンテーションモード | §6.5 | [CFG-JA][FEAT] |
| 単語登録 | `LaunchWordRegisterDialog`（ATOK 風では Ctrl+F7）。Mozc のソースでは `src/gui/word_register_dialog` | [ATOK][GUI-DIR] |
| 辞書ツール | ユーザ辞書の編集・インポート/エクスポート。`src/gui/dictionary_tool` | [H-DIC][GUI-DIR] |
| 同期 | 設定とユーザ辞書の同期（古い FAQ にある）。config.proto では `sync_config` は「obsolete（廃止）」として reserved になっている | [H-FAQ][PROTO] |
| 手書き入力・文字パレット | 2011 年に追加された [MADO]。現在の Mozc master の `src/gui` には手書き・文字パレットの部品が無く、config.proto でも `allow_cloud_handwriting` は reserved。削除の時期は資料に無い | [PROTO][MADO] |
| マウス・候補ウインドウ | 候補ウインドウの細かい仕様（マウス操作、ページ表示の数など）は資料に無い | — |
| 入力モードの表示 | カーソルの近くに入力モードを表示する | [CFG-JA] |

## 8. 出典

| 略号 | 資料名 | URL |
|---|---|---|
| [KM-DIR] | keymap 定義ファイルのディレクトリ | https://github.com/google/mozc/tree/master/src/data/keymap |
| [KM-README] | keymap の README（状態の説明） | https://github.com/google/mozc/blob/master/src/data/keymap/README.md |
| [MSIME] | ms-ime.tsv | https://github.com/google/mozc/blob/b4bbc42ff5524ec16a53cb4914166f6aed45056a/src/data/keymap/ms-ime.tsv |
| [ATOK] | atok.tsv | https://github.com/google/mozc/blob/bc9eab5b11e1ad9fcf863ff0c8a2736dc10f64b0/src/data/keymap/atok.tsv |
| [KOTO] | kotoeri.tsv | https://github.com/google/mozc/blob/bc9eab5b11e1ad9fcf863ff0c8a2736dc10f64b0/src/data/keymap/kotoeri.tsv |
| [CROS] | chromeos.tsv | https://github.com/google/mozc/blob/a1dcadabd3a1c604e8beff1e45830c1d9adfce84/src/data/keymap/chromeos.tsv |
| [MOB] | mobile.tsv | https://github.com/google/mozc/blob/b4bbc42ff5524ec16a53cb4914166f6aed45056a/src/data/keymap/mobile.tsv |
| [OVL] | overlay_henkan_muhenkan_to_ime_on_off.tsv | https://github.com/google/mozc/blob/93ba2474dedad201e3805037ed22a90653c6b455/src/data/keymap/overlay_henkan_muhenkan_to_ime_on_off.tsv |
| [KEYMAP-CC] | コマンド名の登録・ファイル読み込み・状態のフォールバック | https://github.com/google/mozc/blob/master/src/session/keymap.cc |
| [KEYMAP-H] | 状態ごとのコマンド enum とコメント | https://github.com/google/mozc/blob/master/src/session/keymap.h |
| [KEYPARSER] | キー名の表記（パーサ） | https://github.com/google/mozc/blob/master/src/composer/key_parser.cc |
| [EDITOR] | キー設定エディタ（GUI） | https://github.com/google/mozc/blob/master/src/gui/config_dialog/keymap_editor.cc |
| [KM-JA] | キー設定エディタの日本語訳（コマンド名・状態名の和名） | https://github.com/google/mozc/blob/master/src/gui/config_dialog/keymap_ja.qtts |
| [CFG-JA] | プロパティ画面の日本語訳 | https://github.com/google/mozc/blob/master/src/gui/config_dialog/config_dialog_ja.qtts |
| [CFG-CC] | プロパティ画面の選択肢 | https://github.com/google/mozc/blob/master/src/gui/config_dialog/config_dialog.cc |
| [PROTO] | 設定項目の定義 config.proto | https://github.com/google/mozc/blob/master/src/protocol/config.proto |
| [HANDLER] | 既定のキーマップ（OS ごと） | https://github.com/google/mozc/blob/master/src/config/config_handler.cc |
| [DOC-CFG] | docs/configurations.md | https://github.com/google/mozc/blob/master/docs/configurations.md |
| [MODES] | 状態の遷移図 input_modes.svg | https://github.com/google/mozc/blob/master/docs/input_modes.svg |
| [GUI-DIR] | GUI のソースのディレクトリ | https://github.com/google/mozc/tree/master/src/gui |
| [OVL-COMMIT] | overlay keymap を入れたコミット「Support overlay SessionKeymap」（2023-02-10） | https://github.com/google/mozc/commit/93ba2474dedad201e3805037ed22a90653c6b455 |
| [H-BASIC] | ヘルプ: 基本的な使い方 | https://support.google.com/ime/japanese/answer/166759?hl=ja |
| [H-GEN] | ヘルプ: プロパティ › 一般 | https://support.google.com/ime/japanese/answer/166764?hl=ja |
| [H-DIC] | ヘルプ: 辞書 | https://support.google.com/ime/japanese/answer/166765?hl=ja |
| [H-ASSIST] | ヘルプ: 入力補助 | https://support.google.com/ime/japanese/answer/166767?hl=ja |
| [H-SUG] | ヘルプ: サジェスト | https://support.google.com/ime/japanese/answer/166768?hl=ja |
| [H-MISC] | ヘルプ: その他 | https://support.google.com/ime/japanese/answer/166769?hl=ja |
| [H-PRIV] | ヘルプ: プライバシー | https://support.google.com/ime/japanese/answer/173713?hl=ja |
| [H-ABOUT] | ヘルプ: Google 日本語入力とは | https://support.google.com/ime/japanese/answer/166748?hl=ja |
| [H-FAQ] | ヘルプ: よくある質問 | https://support.google.com/ime/japanese/answer/166771?hl=ja |
| [FEAT] | 製品ページの機能一覧 | https://www.google.co.jp/ime/feature.html |
| [ITM] | @IT「Google日本語入力でキー設定を変更する」 | https://atmarkit.itmedia.co.jp/ait/articles/1805/28/news022.html |
| [MADO] | 窓の杜（手書き入力・文字パレットの追加） | https://forest.watch.impress.co.jp/docs/news/440686.html |
