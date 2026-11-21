# macOS 日本語入力プログラム のキー操作とカスタマイズ

macOS 標準の「日本語入力プログラム」（旧ことえり）のキー操作と設定をまとめる。主な出典は Apple「日本語入力プログラムユーザガイド」ver 6.3（macOS 27 版）。出典は末尾の「出典」の略号で示す。

Apple のガイドは「入力中/変換中/候補表示中」といった状態ごとの表を持たず、操作ごとに書く。この文書の節の分け方は、ガイドの節に従う。

---

## 1. 文字種変換（入力中・変換中）

[SC] の「入力ソースを変更する」の表（キーは原文どおり）。同じ表に「ファンクションキーは設定によっては Fn も同時に押す」と注記がある。

| 操作 | キー | 備考 | 出典 |
|---|---|---|---|
| 文字をひらがなに変換 | Control＋J / F6 | | [SC] |
| 文字をカタカナに変換 | Control＋K / F7 | | [SC] |
| 文字を全角ローマ字（全角英字）に変換 | Control＋L / F9 | | [SC] |
| 文字をローマ字（半角英字）に変換（デフォルト） | Control＋; / F8 | | [SC] |
| 文字を半角カタカナに変換 | Control＋; / F8 | 入力ソース設定の入力モードで「半角カタカナ」を有効にしている場合だけ | [SC] |
| 文字をローマ字に変換 | Control＋: / F10 | | [SC] |
| 文字をローマ字に変換（ANSI キーボード選択時） | Control＋: | US 配列でもこの表記 | [SC] |
| F8 → 半角カタカナに変換 | F8 | 「Windows風のキー操作」がオンのとき | [PCW2] |
| ライブ変換中に、ひらがな/カタカナとして確定 | Control＋J / Control＋K | ライブ変換の文脈での説明 | [PCW1] |

- 入力メニューにも同じ操作がある: 「ひらがなに変換」「カタカナに変換」「全角英字に変換」「半角カタカナに変換」「英字に変換」 [CH]。
- [CH] には、変換中（文節に区切った状態）でも文節を選んでから入力メニューの変換コマンドを使う例がある。キー操作でも同じかどうかは資料に無い。
- 文字種変換のあと確定前の状態に留まるか、そのまま確定するかは Apple の資料に無い。[MOZC]（Apple 公式ではない）は Ctrl+J/K/L/;/: を `DisplayAs*`（表示を切り替えるだけで、入力中の状態に留まる）に割り当てる。

## 2. かな漢字変換中・候補表示中

[SC] の「かなを漢字に変換する」の表。「Macのキーボードショートカット」と「Windows風のキーボードショートカット」の 2 列がある。

| 操作 | Mac（既定） | Windows風のキー操作 | 出典 |
|---|---|---|---|
| 漢字に変換する | Space | Space | [SC] |
| 次の漢字候補を選択 | ↓ / Space / **Control＋N** | ↓ / Space | [SC] |
| 前の漢字候補を選択 | ↑ / Shift＋Space / **Control＋P** | ↑ / Shift＋Space | [SC] |
| 候補を 8 行ずつ表示（ページ送り） | Shift＋↑/↓ / Control＋V / Control＋R | Shift＋←/→ / Page Up / Page Down | [SC] |
| 漢字の選択中（変換前）に読みに戻す | Esc | Esc / Control＋Z | [SC] |
| 漢字変換を確定 | Return | Return | [SC] |
| 変換済みテキストの別候補を表示（再変換） | Control＋Shift＋R / Option＋Shift＋R / かなキー 2 回 | Control＋Shift＋R / Alt＋Shift＋R / かなキー 2 回 | [SC] |
| 変換中の「次の」文節を選択（選択文節は太い下線） | ↑ / Control＋B | ↑ | [SC]（原文どおり。下の「矢印キーの向き」） |
| 変換中の「前の」文節を選択 | ↓ / Control＋F | ↓ | [SC]（原文どおり） |
| 選択した文節を伸ばす | Shift＋→ / Control＋W / Control＋O | Shift＋→ / Control＋L | [SC] |
| 選択した文節を縮める | Shift＋← / Control＋I | Shift＋← / Control＋K | [SC] |
| カーソルを上に移動 | ↑ / Control＋E | ← / Control＋E | [SC] |
| カーソルを下に移動 | ↓ / Control＋X | → / Control＋X | [SC] |
| カーソルを左に移動 | ← / Control＋S | ← / Control＋S | [SC] |
| カーソルを右に移動 | → / Control＋D | → / Control＋D | [SC] |
| 文字の後方（カーソルの前の文字）を削除 | Delete / Control＋H | Delete / Control＋H | [SC] |
| 変換対象のテキストをすべて削除 | Esc / Clear | Esc | [SC] |
| 変換を取り消す | Control＋Delete / かなキー 2 回 | Control＋Delete / かなキー 2 回 | [SC] |
| 英字（半角英数字）をかなに変換 | かなキー 2 回 | かなキー 2 回 | [SC] |
| かなを英字（半角英数字）に変換 | 英数キー 2 回 | 英数キー 2 回 | [SC] |

**矢印キーの向き**

- [SC] の注記（要旨）: 「表の矢印キーは横書き用。縦書きでは、書かれていない側の矢印キーを使う（例: ↓ の代わりに ←）」。
- [SC] の表は、横書きでも文節の移動を ↑/↓、カーソルの上下を ↑/↓ と ←/→ で書く。理由は資料に無い。
- 文節の移動のキーは出典で食い違う: [SC] は ↑ が次の文節、↓ が前の文節。[CW] は「テキスト文字列の次の部分/前の部分を選ぶときは →/← を押す」と書く。
- [CW] は「Shift＋→/← で文節を伸ばす/縮める」と書く。
- Control＋B/F の向きは出典で食い違う: [SC] は Ctrl+B が「次の文節」、Ctrl+F が「前の文節」。[MOZC] は Ctrl+F を SegmentFocusRight、Ctrl+B を SegmentFocusLeft にする。

### 2.1 候補選択ウインドウ [CW]

| 操作 | キー | 出典 |
|---|---|---|
| 候補ウインドウを出す | Space を（ウインドウが出るまで）押し続ける／繰り返す | [CW][IN] |
| 番号で選ぶ | 候補に対応する数字キー → Return で確定 | [CW] |
| マウスで選ぶ | 候補をダブルクリック → Return | [CW] |
| 次/前の候補 | ↓/↑、または Space / Shift＋Space | [CW] |
| 次/前の文節 | →/← | [CW] |
| 文節の伸縮 | Shift＋→ / Shift＋← | [CW] |
| 候補の並べ方を切り替える（ウインドウ下部のタブ） | **Tab**、またはタブをクリック | [CW] |
| 1 ページ上へ | Shift＋↑ / Control＋R / Page Up | [CW] |
| 1 ページ下へ | Shift＋↓ / Control＋V / Page Down | [CW] |
| 候補の詳しい情報 | 情報マーク付きの候補を選ぶと横に表示 | [CW] |

- 資料にある Tab の役割は「候補ウインドウの並べ方（タブ）の切り替え」だけ。
- 推測候補（予測）は「推測候補表示」をオンにすると、入力中に候補ウインドウへ出る [SET][CW]。推測候補をキーで選ぶ方法（↓、Tab など）は資料に無い。

## 3. 入力モード・入力ソースの切り替え [SW]

| 操作 | キー | 条件 | 出典 |
|---|---|---|---|
| 次の入力ソースへ | Control＋Option＋Space | | [SW] |
| 前の入力ソースへ（押し続けると一覧） | Control＋Space | | [SW] |
| ラテン系 ↔ 非ラテン系の入力ソース切替 | Caps Lock | システム設定 › キーボード › テキスト入力 › 「Caps Lockキーで…と切り替える」をオン | [SW] |
| 入力ソースの変更 | Fn / 地球儀キー | システム設定 › キーボード の「fn キーを押して」で設定 | [SW] |
| ひらがなへ | Control＋Shift＋J / Option＋Shift＋Z / （JIS）かなキー | | [SW] |
| 英字へ | Control＋Shift＋'（アポストロフィ） | ローマ字入力の入力ソースが必要 | [SW] |
| 英字へ（JIS） | Control＋Shift＋; / 英数キー | | [SW] |
| 英字へ | Shift | 「Shiftキーの動作」が「英字モードに入る」のとき | [SW] |
| 全角英字へ | Control＋Shift＋L | 入力モードで全角英字を有効にしている場合 | [SW] |
| カタカナへ | Control＋Shift＋K / Option＋Shift＋X / （JIS）Shift＋かなキー | 入力モードでカタカナを有効にしている場合 | [SW] |
| カタカナへ | Shift | 「Shiftキーの動作」が「カタカナを入力」のとき | [SW] |
| 半角カタカナへ | Control＋Shift＋; | 入力モードで半角カタカナを有効にしている場合 | [SW] |

- 出典で食い違う: [CH] は「JIS キーボードがない場合、ひらがな入力モードは Control＋Shift＋J、ローマ字入力モードは Control＋Shift＋;」と書く。[SW] は英字を Ctrl+Shift+'、Ctrl+Shift+; を半角カタカナとする。
- 「英数」「かな」キーを 1 回押すと英字/ひらがなへ切り替わる [SW][PCW2]。2 回押すと、直前に入力した文字の変換になる（§2）。

## 4. その他の操作

| 操作 | キー / 方法 | 出典 |
|---|---|---|
| 再変換（確定済みの文字） | 対象を選ぶかカーソルを置き、Control＋Shift＋R、かなキー 2 回、または入力メニュー「再変換」。アプリが対応している必要がある | [UN][CH] |
| 確定済みの文字を変更する | 選択して Delete → 入力し直す（再変換に頼らない方法） | [CH] |
| 【 】〔 〕 を入力（ひらがなモード） | Option＋8 / Option＋9 / Option＋Shift＋8 / Option＋Shift＋9 | [SYM] |
| … を入力 | Option＋; | [SYM] |
| 全角数字（かな入力ソースで「数字を全角入力」がオン） | Option を押しながら数字キー | [NUM] |
| 部首などで漢字を検索 | 範囲を選び Control＋2 | [PCW1] |
| 関連文字を出す | 確定直後の漢字を選び Control＋1 | [PCW1] |
| 矢印記号 | Z に続けて H/J/K/L（例: Z L → →） | [PCW1] |
| 小書き文字 | L または X に続けてかな（例: L A → ぁ） | [PCW1] |
| 文字ビューア | Command＋Control＋Space | [PCW1] |
| 仮名表を使って入力 | 入力メニュー（キーは無し） | [KANA] |
| プライベートモード | 入力メニュー「プライベートモード」（キーは無し） | [PRIV] |
| ライブ変換のオン/オフ | 入力メニュー「ライブ変換」または設定。ショートカットは無い | [IN][PCW1] |

**Option 系のキー**

- Apple の資料にある Option 系は、上の表のものと Option＋Shift＋Z/X（モード切替、§3）、Option＋Shift＋R（再変換、§2）だけ。
- [MOZC] には Option＋A/C/S/X/Z、Option＋F1〜F5（文字種変換）、Option＋J/L（カーソル移動）、Option＋I/K（前/次候補）、Option＋Space（全角スペース）がある。Apple の資料には無い。

## 5. ライブ変換 [IN][SET]

| 項目 | 内容 | 出典 |
|---|---|---|
| 動作 | 入力に合わせてひらがなを自動で漢字かな混じりに変換する。Space を押さなくてよい | [IN] |
| 追加の候補 | Space を 1 回以上押す | [IN] |
| 確定 | Return | [IN] |
| 元に戻す | Esc で、入力したひらがなと変換の下線に戻る | [IN] |
| ひらがな/カタカナで確定 | Control＋J / Control＋K | [PCW1] |
| 「句読点で変換」との関係 | ライブ変換をオンにすると「句読点で変換」は自動でオフになり、選べなくなる | [SET][PU] |
| オン/オフ | 入力メニュー「ライブ変換」または入力ソース設定 | [IN] |

ライブ変換中の文節の操作（←/→、Shift＋←/→）が通常の変換中と同じかどうかは資料に無い。

---

## 6. カスタマイズできる範囲

| 項目 | 状況 | 出典 |
|---|---|---|
| キー 1 つずつの割り当て変更 | **できない**。設定画面にキー割り当ての項目は無い。Apple のコミュニティでも「システム設定で変えられる修飾キーは限られ、複雑な割り当てにはサードパーティ製アプリが要る」と回答されている | [SET]、[APC] |
| 割り当ての切り替え | 「Windows風のキー操作」のオン/オフだけ（2 通り） | [SET][SC] |
| モード系のキー | Caps Lock の動作、Shift キーの動作、入力モードの有効/無効 | [SET] |
| システム全体 | 修飾キーの入れ替え（システム設定 › キーボード › 修飾キー）、Caps Lock/Fn/地球儀キーでの入力ソース切替 | [SW] |

## 7. 「Windows風のキー操作」

| 項目 | 内容 | 出典 |
|---|---|---|
| 場所 | 入力ソース設定（日本語 - ローマ字入力 / かな入力）のチェックボックス | [SET][EN] |
| 説明（原文要旨） | 「キーボードをWindowsキーボードのように操作し、Windowsと同様のショートカットを使用できるようにする」 | [SET] |
| 連動 | オンにすると「Shiftキーの動作」が自動で「英字モードで入力」になる | [SET] |
| Shift で英字 | 入力中に Shift を押すと英字モードになり、Return で確定すると元のモードに戻る | [EN] |
| キーの違い | §2 の表の「Windows風」列（Ctrl+N/P/B/F/W/O/I/V/R が外れ、Ctrl+Z/L/K、Shift+←→、PageUp/Down、Alt+Shift+R が入る） | [SC] |
| F8 | 半角カタカナに変換 | [PCW2] |
| 確定 | 「Return 1 回で候補が確定する」 | [PCW1] |

- Windows風のときに Ctrl+J/K/L/;/: の文字種変換がどうなるか（Ctrl+K/L が文節伸縮と重なる）は資料に無い。
- 変換/無変換キー（JIS の Mac キーボードには無い）の扱いは資料に無い。

## 8. 設定項目 [SET]

開き方: 入力メニュー → 「"日本語 - ローマ字入力"設定を開く」（または かな入力）→ サイドバーで入力ソース名を選ぶ [SET]。

| 設定 | 内容 | 出典 |
|---|---|---|
| 入力モード | 使う入力モード（ひらがな / カタカナ / 全角英字 / 半角カタカナ / 英字 など）のチェックボックス | [SET][SW] |
| Caps Lockの動作 | Caps Lock でひらがなからカタカナまたは英字へすばやく切り替える（例: 「オンの時『カタカナ』を入力」）。システム側の「Caps Lockで入力ソースを切替」がオンだと使えない | [SET] |
| Shiftキーの動作 | Shift でカタカナ入力 / 英字モードに切り替える（「英字モードに入る」「カタカナを入力」） | [SET][SW] |
| ライブ変換 | オン/オフ。オンにすると「句読点で変換」はオフになる | [SET] |
| タイプミスを修正 | タイプミスを自動で直し、入力中に候補を出す | [SET][IN] |
| Windows風のキー操作 | §7 | [SET] |
| 候補表示 | 候補ウインドウのフォントとサイズ | [SET][CW] |
| 推測候補表示 | 入力中に予測候補を出す | [SET] |
| 句読点で変換 | 句読点の入力で変換する（ライブ変換オン時は使えない） | [SET][PU] |
| 英字のレイアウト | ローマ字入力で使うキーボードレイアウト（既定は最後に使ったもの） | [SET] |
| 句読点の種類 | 使う句読点。選択肢の中身は資料に無い | [SET][PU] |
| "/"キーで入力する文字 | JIS で「/」か「・」か | [SET] |
| "¥"キーで入力する文字 | JIS で「＼」か「¥」か | [SET] |
| 数字を全角入力 | 数字を全角で入力する | [SET][NUM] |
| 追加辞書 | 追加辞書の一覧、書き出し、テキストファイルの読み込み | [SET] |
| 変換学習 | 学習のオン/オフと「リセット」 | [SET] |

---

## 9. 機能一覧

- 入力メニューから使う機能: ライブ変換、プライベートモード（学習しない・連絡先などを使わない）[PRIV]、再変換 [UN]、文字種変換 [CH]、仮名表 [KANA]、ユーザ辞書を編集（読み 32 文字・語句 64 文字まで、plist で書き出し・読み込み、Apple Account で同期）[DIC]、絵文字と記号 [DIC]。
- 自動の機能: 「http:」「www.」「file:」のような英字列は自動で英字モードになる [EN]。数字の変換候補として全角・半角・漢数字（位取りあり/なし）・大字が出る [NC]。

---

## 出典

| 略号 | 資料名 | URL |
|---|---|---|
| SC | Apple「Macの日本語変換用のキーボードショートカット」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10263/6.3/mac/27 |
| SET | Apple「Macの日本語入力ソース設定を変更する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim662a12b9/6.3/mac/27 |
| SW | Apple「Macで日本語入力ソースに切り替える」（入力モード切替） | https://support.apple.com/ja-jp/guide/japanese-input-method/jpimf6ffb247/6.3/mac/27 |
| IN | Apple「日本語入力ソースを使用して日本語を入力する」（ライブ変換） | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10265/6.3/mac/27 |
| CW | Apple「候補選択ウインドウを使用する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10262/6.3/mac/27 |
| CH | Apple「入力した日本語の文字を変更する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10231/6.3/mac/27 |
| EN | Apple「ひらがな/カタカナを使用して半角英字文字列を入力する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10232/6.3/mac/27 |
| UN | Apple「変換を元に戻す」（再変換） | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10309/6.3/mac/27 |
| PU | Apple「句読点を使用してテキストを変換する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10215/6.3/mac/27 |
| NUM | Apple「全角または半角の数字を入力する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10268/6.3/mac/27 |
| SYM | Apple「記号を入力する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10286/6.3/mac/27 |
| PRIV | Apple「プライベートモードを使用する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpime16330d9/6.3/mac/27 |
| DIC | Apple「ユーザ辞書を編集する/使用する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10228/6.3/mac/27 |
| KANA | Apple「仮名表を使用して文字を入力する」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10233/6.3/mac/27 |
| NC | Apple「ひらがな入力での数字を他の表記に変換」 | https://support.apple.com/ja-jp/guide/japanese-input-method/jpim10245/6.3/mac/27 |
| PCW1 | PC Watch「Macの日本語入力を快適にする12のワザ」（2022-05-27） | https://pc.watch.impress.co.jp/docs/column/macinfo/1412151.html |
| PCW2 | PC Watch「WindowsとMacのキー操作は何が違う？」（2024-09-18） | https://pc.watch.impress.co.jp/docs/column/macinfo/1624398.html |
| MOZC | Mozc の Kotoeri 風キーマップ（Google による模倣。Apple 公式ではない） | https://github.com/google/mozc/blob/master/src/data/keymap/kotoeri.tsv |
| APC | Apple サポートコミュニティ（キー割り当ての変更） | https://discussionsjapan.apple.com/thread/254979405 |
