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

- 出典で食い違う: [CH] は「JIS キーボードがない場合、ひらがな入力モードは Control＋Shift＋J、ローマ字入力モードは Control＋Shift＋;」と書く。[SW] は英字を Ctrl+Shift+'（JIS キーボードでは Ctrl+Shift+; か英数キー）とし、半角カタカナにも Ctrl+Shift+; を挙げる。
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

## 10. 実機で確かめたこと

§1〜§8 の「資料に無い」「出典で食い違う」を、Mac の実機で確かめた。全部の状態 × キーの表は [macos-table.md](macos-table.md)。
Windows（MS-IME・ゆらぎ）との違いの整理は [macos-vs-windows.md](macos-vs-windows.md)。

- **環境:** MacBook Air (M1)、macOS 27.2.1、内蔵キーボードは US 配列、入力ソース「日本語 - ローマ字入力」。2026-11-22。
- **見方:** `tools/keyprobe/mac/`。試験アプリの窓（`NSTextInputClient`）にキーを合成して入れ、日本語入力プログラムの呼び出しを記録する（方法は [macos-probe.md](macos-probe.md)）。
  11 の状態 × 147 キーを既定の設定で採り、「ライブ変換」「Windows風のキー操作」をオンにして採り直した。
- **本物のキー:** システムが先に取るキーと押し続けは、人が押して確かめた（§10.8）。それ以外は合成したキー。
- **設定:** ライブ変換オフ、推測候補表示オン、タイプミス修正オン（この Mac の設定）。試験中は学習を止めた（プライベートモード）。

### 10.1 資料の「資料に無い」「食い違い」への答え

| 問い | 実機 | 節 |
|---|---|---|
| 文節の移動は ←/→ か ↑/↓ か | **←/→**。↑/↓ は候補ウインドウを開く（[SC] の表の ↑/↓ は誤り、または縦書きの表） | §2 |
| Control＋B / F の向き | **B が前、F が次**の文節（[SC] と逆。[MOZC] と同じ）。Control＋S / D も前 / 次 | §2 |
| 文字種変換のあと、入力中に留まるか | **留まる**（確定しない）。変換中は注目文節の字種だけを変え、変換中に留まる | §1 |
| 変換中の Control＋J / K / L / ; | 注目文節の字種を変える（ひらがな / カタカナ / 全角英字 / 半角英字） | §1 |
| 推測候補をキーで選ぶ方法 | Tab・↓・Control＋N で入って次へ、Shift＋Tab・↑・Control＋P で前へ。Return で確定。数字では選べない | §2.1 |
| 候補ウインドウの数字のあと、確定に Return が要るか | 要る。数字はその候補を選んで窓を閉じ、変換中に留まる | §2.1 |
| 候補ウインドウの Tab | 下のタブ（標準 → 読み → 部首 → 名前 → 記号 → 標準）を順に替える。Shift＋Tab は逆順 | §2.1 |
| ライブ変換中の ←/→、Esc、Control＋J / K | §10.7 | §5 |
| 「Windows風」の Control＋K / L | 文節の伸縮（字種の変換ではない） | §7 |
| 「Windows風」で Return 1 回で確定するか | する（候補ウインドウが開いていても 1 回） | §7 |
| 英数 2 回、かな 2 回 | §10.6 | §2 |
| Mozc にある Option＋A / C / S / X / Z | **ある**（既定）。A・S は半角英字、C は全角英字、X はカタカナ、Z はひらがな。Option＋J / L はカーソル左 / 予測候補に入る | §4 |
| Control＋1、Control＋2 | 試験アプリでは何も起きなかった（確定直後・選択なし） | §4 |
| 候補ウインドウの 1 ページの件数 | **9 件**（[SC] の「8 行ずつ」とは違う） | §2 |
| カーソルを上 / 下（↑・Control＋E / ↓・Control＋X） | 入力中の ↑ は何もせず、Control＋E は食べて何もしない。↓・Control＋X は予測候補に入る。変換中はどれも候補ウインドウを開く | §2 |
| Control＋:（ローマ字に変換） | 合成した Control＋Shift＋;（US 配列の Control＋:）は、入力中も変換中も何も変えなかった | §1 |

### 10.2 入力中（未変換）

| キー | 動き |
|---|---|
| Space、Shift＋Space、PageUp/Down、Shift＋↑/↓、Control＋↑/↓、Control＋R / V | 変換する（候補ウインドウは出さない。予測候補の窓は閉じる） |
| Return、Shift＋Return、Control＋M、**Control＋I** | 確定する |
| Esc、Shift＋Esc、Control＋[ | 入力を全部消す |
| Delete、Shift＋Delete、Control＋H | カーソルの前の 1 字を消す |
| ForwardDelete（fn＋Delete）、Control＋D・Control＋G | **カーソルの後ろの字は消さない**（ForwardDelete は何もしない。Control＋D はカーソルを右へ） |
| ←、Control＋B、Control＋S、Shift＋←、Option＋J | カーソルを左へ |
| →、Control＋F、Control＋D、Shift＋→ | カーソルを右へ |
| Home / End | 入力の先頭 / 末尾へ |
| Tab、↓、Control＋N、Control＋X、Option＋L | 予測候補に入る（§10.3） |
| ↑、Shift＋Tab | 何もしない |
| F6 / F7 / F8 / F9 / F10 | ひらがな / カタカナ / 半角英字 / 全角英字 / 半角英字（F8 は資料の「半角英字」のとおり） |
| Control＋J / K / L / ; / '、Control＋A | ひらがな / カタカナ / 全角英字 / 半角英字 / 半角英字 / 半角英字 |
| Option＋Z / X / C / A / S | ひらがな / カタカナ / 全角英字 / 半角英字 / 半角英字 |
| Option＋Space / Control＋Option＋Space | 入力中の文字に全角 / 半角の空白を足す |
| 英数キー | 確定して英字（ABC）にする |
| Shift＋英字 | 大文字を入れ、確定までその入力は英字の続き（Space は半角の空白を足し、変換しない）。「Shiftキーの動作」の既定 |
| Control＋Q | **入力を捨てて制御文字 `\x11` を確定する**（本物のキーでも同じ。§10.8） |
| Command＋矢印、Option＋矢印、Control＋C / E / O / P / T / U / W / Y / Z など | 食べて何もしない（入力は残る） |

- 割り当ての無いキーは**食べて何もしない**。MS-IME のように「確定してアプリに通す」ことはしない。
- ローマ字: `kya`→きゃ、`la`・`xa`→ぁ、`ltu`・`xtu`→っ、`nn`→ん、`n'`→ん（`kan'i`→かんい）。`zh`・`zj`・`zk`・`zl` は ← ↓ ↑ →。`z.`・`z,`・`z-`・`z/`・`z[` は記号にならない（z と記号のまま）。
- 数字は半角で入力中の文字に入る。`1234` を変換すると 1234 → 🔢 → １２３４ … の順に候補が出る。

### 10.3 予測候補（推測候補表示）

| キー | 動き |
|---|---|
| （入力しただけ） | 予測候補の窓が出る。フォーカスは無い |
| Tab、↓、Control＋N、Control＋X、Option＋L | 予測候補に入り、次の候補へ |
| Shift＋Tab、↑、Control＋P | 前の候補へ（先頭では止まる） |
| Return、Control＋M | 選んだ予測候補を確定する |
| Space | 予測をやめ、読みを変換する（予測候補は使わない） |
| Esc、Control＋[ | 予測候補から出て、入力中に戻る |
| 数字、文字キー | **選んだ予測候補を確定して**、その字で次の入力を始める（数字で選ぶことはできない） |
| Delete、Control＋H | **選んだ予測候補の末尾 1 字を消して確定する**（「感情」→「感」。本物のキーでも同じ） |
| → | 候補の詳しい情報（辞書）を横に出す |
| Home / End | **入力を捨てて制御文字 `\x01` / `\x04` を確定する**（Home は本物のキーでも同じ） |
| 英数キー | 選んだ予測候補を確定して英字にする |

### 10.4 変換中（文節）

| キー | 動き |
|---|---|
| Space | 次の候補。2 回目で候補ウインドウを開く（MS-IME と同じく、1 回目の変換では窓を出さない） |
| Shift＋Space、↑、↓、PageUp/Down、Shift＋↑/↓、Control＋↑/↓、Control＋E / N / P / R / V / X、Option＋L | 候補ウインドウを開く（候補は変えない） |
| Return、Shift＋Return、Control＋M、**Tab** | 全部確定する |
| Esc、Shift＋Esc、Control＋[ | **全部の文節を読みに戻す**（注目文節だけではない）。もう 1 回で全部消す |
| Delete、Shift＋Delete、Control＋H | **表示の末尾 1 字を消して、残りを確定する**（「今日は雨です」→「今日は雨で」を確定） |
| →、Control＋F、Control＋D | 次の文節（最後の文節では何もしない） |
| ←、Control＋B、Control＋S、Option＋J | 前の文節 |
| Home / End | 先頭 / 末尾の文節 |
| Shift＋←、Control＋I、Control＋Q | 注目文節を縮める。**縮めたらすぐ変換し直す**（読みにはしない）。「今日は」→「今日／は」 |
| Shift＋→、Control＋O、Control＋W | 注目文節を伸ばし、すぐ変換し直す。「今日は／雨です」→「今日はあ／目です」 |
| F6〜F10、Control＋J / K / L / ; / '、Control＋A、Option＋Z / X / C / A / S | 注目文節の字種を変える |
| 文字キー、数字、記号、Shift＋英字 | 確定して、その字で次の入力を始める |
| Option＋Space | 確定して全角の空白を入れる |
| 英数キー | 確定して英字にする |

- 伸縮のあとの Space は、注目文節の次の候補へ進んで候補ウインドウを開く。
- 縮めた文節の残りも、すぐ変換される（「今日」を「許」に縮めると、残りは「雨は」になった）。

### 10.5 候補ウインドウ

| キー | 動き |
|---|---|
| Space、↓、Control＋N、Control＋X、Option＋L | 次の候補 |
| Shift＋Space、↑、Control＋P、Control＋E | 前の候補 |
| PageDown、Shift＋↓、Control＋V、Control＋↓ / PageUp、Shift＋↑、Control＋R、Control＋↑ | 次 / 前のページ（9 件ずつ。先頭のページで前へ行くと最後のページへ） |
| 1〜9 | その番号の候補を選び、窓を閉じる（変換中に留まる。確定には Return がもう 1 回要る） |
| **Return** | **候補を選んで窓を閉じるだけ。確定しない。** 複数文節なら注目を次の文節へ移す。もう 1 回の Return で全部確定 |
| Tab / Shift＋Tab | 窓の下のタブ（標準・読み・部首・名前・記号）を順に替える |
| → / ← | 複数文節なら次 / 前の文節へ移り、窓を閉じる。1 文節では辞書の説明を横に出す |
| Esc | 全部の文節を読みに戻し、窓を閉じる |
| Delete | 末尾 1 字を消して確定する（§10.4 と同じ） |
| Shift＋← / → など伸縮のキー | 伸縮して窓を閉じる |
| 文字キー、0 | 確定して、その字で次の入力を始める |

- 窓の候補の並びは Space で進む順と違う。1 番目はひらがな（「かんじ」。注記 Hiragana）で、Space の 1 回目に出る候補は 2 番目。↑ でひらがなに戻れる。
- 辞書の印（📖）の付いた候補を選ぶと、→ で語の説明が出る。
- 番号は窓の中の位置。2 ページ目で 2 を押すと、2 ページ目の 2 番目を選ぶ。

### 10.6 確定のあと（取り消し・再変換・英数とかな）

| 操作 | 動き |
|---|---|
| Control＋Delete（確定の直後） | **確定を取り消す**。確定した「感じ」が変換中に戻り、候補ウインドウが開く。選択しなくてよい。アプリが置き換え範囲（`replacementRange`）に対応している必要がある |
| Control＋Shift＋R / Option＋Shift＋R | **選んだ文字**を再変換する。選択が無いと何もしない（試験アプリ。カーソルの前の語を自動で選ぶことはしなかった） |
| 再変換中の Esc | 1 回目で読みに戻り、2 回目で元の表記を確定し直す |
| かなキー 2 回（すばやく） | 選んだ文字を再変換する（間隔 0.15 秒では効き、0.45 秒では効かない）。選んだ英字「watashi」は英語の発音で読み、「ワット／アッシュ／愛」になった |
| 英数キー 2 回 | 何も起きなかった（選択があってもなくても）。[SC] の「かなを英字に変換」は再現しなかった |
| Control＋Z、Command＋Z | 日本語入力プログラムは使わない（アプリへ） |

### 10.7 ライブ変換

| キー | 動き |
|---|---|
| （入力しただけ） | 読みが変換されて出る（文節の区切りはあるが、注目文節の太い下線は無い）。予測候補の窓も出る |
| Space | 文節を選ぶ状態に入り、候補ウインドウを開く |
| ←、Control＋B / S | 文節を選ぶ状態に入り、**最後の文節**に注目して候補ウインドウを開く（カーソルは動かない） |
| →、↑、↓、Control＋N / P / E / F / D / X | 文節を選ぶ状態に入り、先頭の文節に注目して候補ウインドウを開く |
| Return | 確定する（候補ウインドウが開いていないとき。開いていれば窓を閉じる） |
| Esc | **1 回目は最後の文節を読みに戻す**（「今日は雨です」→「今日は／あめです」）。文節選択の状態からは全部を読みに戻す |
| Delete | 読みの末尾 1 字を消す（確定しない。ライブ変換でないときと違う） |
| F6〜F10、Control＋J / K / L / ; | 入力全体の字種を変える。文節選択中は注目文節だけ |
| Shift＋← / →、Control＋I / O / W | 文節を選ぶ状態で、注目文節を伸縮する |
| Option＋Space | 文節選択中は、確定して全角の空白を入れる |

### 10.8 人の手で確かめたこと・確かめていないこと

本物のキーボードで押したもの（手順は `tools/keyprobe/mac/guide.py` など）。

| キー | 結果 |
|---|---|
| Control＋Space | 入力ソースを直前に使ったものへ切り替える（日本語 → 韓国語、ABC → 日本語）。入力中なら確定してから切り替える |
| 地球儀キー（fn） | 何も起きない（この Mac は「fn キーを押して: 何もしない」。`AppleFnUsageType=0`） |
| Shift の単独打鍵 | 何も起きない（「Shiftキーの動作」が既定でもカタカナでも。合成でも同じ） |
| Space の押し続け | 繰り返しのたびに Space 1 回と同じ（変換 → 窓を開く → 次の候補 …）。押し続け特有の動きは無い |
| 予測候補を選んでいるときの Delete | 末尾 1 字を消して確定（合成と同じ） |
| 予測候補を選んでいるときの Home（fn＋←）、入力中の Control＋Q | 入力を捨てて制御文字を確定（合成と同じ） |

確かめていないもの: Caps Lock（この Mac は Caps Lock を無効にしてある）、Control＋Option＋Space（入力メニューの次の入力ソース）、
JIS キーボードの英数・かなキーを本物で押したとき、かな入力、ほかのアプリ（ブラウザなど）での違い。

### 10.9 設定のキー名

設定は `defaults` の `com.apple.inputmethod.Kotoeri` にある。`defaults write` で書き、日本語入力プログラムのプロセス（`JapaneseIM-RomajiTyping`）を強制終了すると、次に使うときに読み直す
（SIGTERM は効かない。SIGKILL で止めると自動で起動し直す）。ライブ変換だけは、プロセスを止めなくても効いた。
キー名は `CoreJapaneseEngine.framework` の `JIMPreferences` と、共有キャッシュの文字列から見つけた。

| キー | 設定画面の項目 | 値 |
|---|---|---|
| `JIMPrefLiveConversionKey` | ライブ変換 | 0 / 1 |
| `JIMPrefWindowsModeKey` | Windows風のキー操作 | 0 / 1 |
| `JIMPrefShiftKeyActionKey` | Shiftキーの動作 | 未設定・1・2・3: 英字モードに入る。**0: カタカナを入力**（Shift＋A で「ア」、その 1 字だけ） |
| `JIMPrefCapsLockActionKey` | Caps Lockの動作 | 確かめていない |
| `JIMPrefPrivNoLearningKey` | プライベートモード（学習しない） | 1 で学習しない（対照実験で確かめた） |
| `JIMPrefPredictiveCandidateKey` | 推測候補表示 | 0 / 1 |
| `JIMPrefAutocorrectionKey` | タイプミスを修正 | 0 / 1 |
| `JIMPrefConvertWithPunctuationKey`、`JIMPrefPunctuationTypeKey`、`JIMPrefFullWidthNumeralCharactersKey`、`JIMPrefCharacterForSlashKey`、`JIMPrefCharacterForYenKey`、`JIMPrefRomajiKeyboardLayoutKey`、`JIMPrefCandidateWindowFontKey`、`JIMPrefCandidateWindowFontSizeKey` | §8 の各項目 | 確かめていない |
| `JIMPrefConvertWithArrowKey` | **設定画面に無い** | 確かめていない |

### 10.10 「Windows風のキー操作」の実機

Apple が「Windows 風」として何を MS-IME 風にしたかの記録。全部は [macos-table.md](macos-table.md) の最後。

- F8 が半角カタカナ。Control＋U / I / O / P / T が F6〜F10（MS-IME と同じ）。Control＋J / K / L / ; の文字種変換は無くなる。
- Control＋K / L が文節の縮め / 伸ばし。Control＋Z と変換中の Delete・Control＋H が「読みに戻す」（確定しない）。
- 候補ウインドウの Return は 1 回で確定する。
- ↑ / ↓ は前 / 次の候補を選んで窓を開く（既定は窓を開くだけ）。PageUp/Down は変換中は何もしない。
- Option＋J / L と Option＋Shift＋Z / X / R は Option の文字（∆ ¬ など）になる。Option＋A / C / S / X / Z の字種変換は既定と同じに残る。
- Control＋C は確定する。Control＋N は変換中と予測候補の選択中に、入力を捨てて制御文字 `\x0e` を確定する（Control＋Q と同じ癖）。入力中は何もしない（カーソルが途中にあるときは末尾へ動かす）。

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
