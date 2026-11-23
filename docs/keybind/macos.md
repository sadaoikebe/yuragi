# macOS 日本語入力プログラム のキー操作とカスタマイズ

macOS 標準の「日本語入力プログラム」（旧ことえり）のキー操作と設定。
全部の状態 × キーの表は [macos-table.md](macos-table.md)、Windows（MS-IME・ゆらぎ）との違いは [macos-vs-windows.md](macos-vs-windows.md)、調べ方は [macos-probe.md](macos-probe.md)。

**出典の欄の読み方**

| 書き方 | 意味 |
|---|---|
| 実機 | Mac の実機で、試験アプリ（`tools/keyprobe/mac/`）の中で合成したキーを入れて見た動き。試験アプリの窓は 2 種類（最小限の `NSTextInputClient` と、AppKit の標準のテキスト欄 `NSTextView` とメインメニュー）。違いが出るのは §5 と Command 付きのキー（§1）だけ |
| 実機（本物のキー） | 同じ試験アプリで、人が本物のキーボードで押して見た動き |
| 利用者 | Mac の利用者が、ふつうのアプリで見た動き（試験アプリでは採れないもの） |
| [SC] など | 資料にある動き（末尾の「出典」）。実機では見ていない |

- 実機の環境: MacBook Air (M1)、macOS 27.2.1、内蔵キーボードは US 配列、入力ソース「日本語 - ローマ字入力」（入力モードはひらがなだけ）と ABC。
- 実機の設定: ライブ変換オフ（§8 は別）、Windows風のキー操作オフ（§9 は別）、推測候補表示オン、タイプミス修正オン、Shiftキーの動作は既定。
- 実機の動きは、AppKit の標準のテキスト入力を持つアプリでのもの。ブラウザなど独自のテキスト入力を持つアプリでは違うことがある。
- Command 付きのキーは、メインメニューを持つアプリでの動き（§1）。
- キーの名前は Mac の刻印（Delete は前の字を消すキー、fn＋Delete が後ろの字を消すキー、Return、Option）。

---

## 1. 入力中（未変換）

| キー | 動き | 出典 |
|---|---|---|
| Space、Shift＋Space、Page Up / Page Down、Shift＋↑ / ↓、Control＋↑ / ↓、Control＋R / V | 変換する。候補ウインドウは出さない（予測候補の窓は閉じる） | 実機 |
| Return、Shift＋Return、Control＋M、Control＋I | 確定する | 実機 |
| Esc、Shift＋Esc、Control＋[ | 入力を全部消す | 実機 |
| Delete、Shift＋Delete、Control＋H | カーソルの前の 1 字を消す | 実機 |
| fn＋Delete、Control＋G | 何もしない（カーソルの後ろの字を消す操作は無い） | 実機 |
| ←、Control＋B、Control＋S、Shift＋←、Option＋J | カーソルを左へ | 実機 |
| →、Control＋F、Control＋D、Shift＋→ | カーソルを右へ | 実機 |
| Home / End | 入力の先頭 / 末尾へ | 実機 |
| Tab、↓、Control＋N、Control＋X、Option＋L | 予測候補に入る（§2） | 実機 |
| ↑、Shift＋Tab、Control＋E | 何もしない | 実機 |
| F6、Control＋J、Option＋Z | ひらがなにする | 実機 |
| F7、Control＋K、Option＋X | カタカナにする | 実機 |
| F9、Control＋L、Option＋C | 全角英字にする | 実機 |
| F8、F10、Control＋;、Control＋'、Control＋A、Option＋A、Option＋S | 半角英字にする | 実機 |
| Control＋Shift＋;（US 配列の Control＋:） | 何もしない | 実機 |
| Option＋Space / Control＋Option＋Space | 入力中の文字に全角 / 半角の空白を足す | 実機 |
| Option＋8 / 9 / ; / Shift＋8 / Shift＋9 | 入力中の文字に • / 【 / … / ° / 〔 を足す | 実機 |
| 英数キー | 確定して英字（ABC）にする | 実機 |
| Shift＋英字 | 大文字を入れる。続く英字は、確定まで英字で入る（Space は変換せず半角の空白を足す） | 実機 |
| Control＋Q | 入力を捨てて、制御文字 `\x11` を確定する（`NSTextView` でも文書に `\x11` が入る） | 実機（本物のキー） |
| Control＋C / O / P / T / U / W / Y / Z、Option＋矢印 | 食べて何もしない（入力は残る） | 実機 |

- 字種を変えても確定しない。入力中のまま残る（カーソルは末尾）。
- 割り当ての無いキーは食べて何もしない。入力を確定してアプリに渡すことはしない。
- Control＋Option＋Space の行は、試験アプリの中で合成したキーで見た動き（入力中の文字に半角の空白を足す）。本物のキーでは、システムのショートカット「次の入力ソースへ」（§6）が有効なら、システムが先に取って入力ソースが切り替わり、日本語入力プログラムには届かない（[macos-probe.md](macos-probe.md) §5）。
- Apple の資料は F8 と Control＋; を「半角英字（入力モードで半角カタカナを有効にしていれば半角カタカナ）」、Control＋: と F10 を「ローマ字に変換」とする [SC]。
- ローマ字: `la`・`xa` は「ぁ」、`ltu`・`xtu` は「っ」、`nn` と `n'` は「ん」（`kan'i` は「かんい」）。`zh`・`zj`・`zk`・`zl` は ← ↓ ↑ →。`z.`・`z,`・`z-`・`z/`・`z[` は記号にならず、z と記号のまま残る（実機）。
- 数字は半角で入力中の文字に入る。`1234` を変換すると、候補は 1234、🔢、１２３４ … の順（実機）。数字の候補には漢数字（位取りあり / なし）・大字もある [NC]。
- 「http:」「www.」「file:」のような英字列は、自動で英字モードになる [EN]。

**Command 付きのキー（アプリのショートカット）**

日本語入力プログラムは Command 付きのキーを食べない。入力中・予測候補・変換中・候補ウインドウのどの状態でも、キーはアプリのメニューとキーの割り当てに届く。
入力中の文字がどうなるかは、アプリの操作しだい。カーソルを動かす操作・文字を入れる操作は入力中の文字を確定し、ほかの操作は確定しない。

| キー | 動き（`NSTextView`、入力中の文字がある状態） | 出典 |
|---|---|---|
| Command＋S | 保存（メニュー）が動く。入力中の文字は確定されずに残る | 実機 |
| Command＋A | すべてを選択する。入力中の文字は確定される | 実機 |
| Command＋V | 入力中の文字を確定してから、貼り付ける | 実機 |
| Command＋Z | 取り消す。入力中の文字も消える | 実機 |
| Command＋C / X | 何も起きない（選択が無いので、アプリがコピー・カットを無効にしている） | 実機 |
| Command＋← / ↑ | 行頭・文頭へ動く。入力中の文字は確定される | 実機 |
| Command＋→ / ↓ | 行末・文末へ動く（入力中の文字が末尾にあれば動かず、入力中の文字は残る） | 実機 |
| Command＋Delete | 行頭まで消す。入力中の文字（変換中は注目文節）も消える | 実機 |

## 2. 予測候補（推測候補表示）

| キー | 動き | 出典 |
|---|---|---|
| （入力しただけ） | 予測候補の窓が出る。フォーカスは無い | 実機 |
| Tab、↓、Control＋N、Control＋X、Option＋L | 予測候補に入り、次の候補へ | 実機 |
| Shift＋Tab、↑、Control＋P | 前の候補へ。先頭では動かない | 実機 |
| Return、Control＋M | 選んだ候補を確定する | 実機 |
| Space | 予測候補をやめ、読みを変換する | 実機 |
| Esc、Control＋[ | 予測候補から出て、入力中に戻る | 実機 |
| 文字キー、数字 | 選んだ候補を確定して、その字で次の入力を始める。数字で候補は選べない | 実機 |
| Delete、Control＋H | 選んだ候補の末尾 1 字を消して確定する（「感情」なら「感」を確定） | 実機（本物のキー） |
| → | 候補の詳しい情報（辞書）を横に出す | 実機 |
| Home / End | 入力を捨てて、制御文字 `\x01` / `\x04` を確定する（`NSTextView` でも文書に入る） | 実機（Home は本物のキー） |
| F6〜F10、Control＋J / K / L / ; | 予測候補の窓を閉じる | 実機 |
| 英数キー | 選んだ候補を確定して英字にする | 実機 |

## 3. 変換中（文節）

| キー | 動き | 出典 |
|---|---|---|
| Space | 次の候補。2 回目から候補ウインドウを開く（1 回目の変換では窓を出さない） | 実機 |
| Shift＋Space、↑、↓、Page Up / Down、Shift＋↑ / ↓、Control＋↑ / ↓、Control＋E / N / P / R / V / X、Option＋L | 候補ウインドウを開く。候補は変えない | 実機 |
| Return、Shift＋Return、Control＋M、Tab | 全部確定する | 実機 |
| Esc、Shift＋Esc、Control＋[ | 全部の文節を読みに戻す。もう 1 回で入力を全部消す | 実機 |
| Delete、Shift＋Delete、Control＋H | 表示の末尾 1 字を消して、残りを確定する（「今日は雨です」なら「今日は雨で」を確定） | 実機 |
| →、Control＋F、Control＋D | 次の文節へ（最後の文節では動かない） | 実機 |
| ←、Control＋B、Control＋S、Option＋J | 前の文節へ | 実機 |
| Home / End | 先頭 / 末尾の文節へ | 実機 |
| Shift＋←、Control＋I、Control＋Q | 注目文節を 1 字縮め、すぐ変換し直す（「今日は」が「今日／は」） | 実機 |
| Shift＋→、Control＋O、Control＋W | 注目文節を 1 字伸ばし、すぐ変換し直す（「今日は／雨です」が「今日はあ／目です」） | 実機 |
| F6〜F10、Control＋J / K / L / ; / '、Control＋A、Option＋Z / X / C / A / S | 注目文節の字種を変える（キーごとの字種は §1） | 実機 |
| 文字キー、数字、記号、Shift＋英字 | 確定して、その字で次の入力を始める | 実機 |
| Option＋Space | 確定して全角の空白を入れる | 実機 |
| 英数キー | 確定して英字にする | 実機 |

- 伸縮すると、残りの文節も変換し直す（「今日」を「許」に縮めると、残りは「雨は」になる）。伸縮のあとの Space は、注目文節の次の候補へ進んで候補ウインドウを開く。
- 注目文節は太い下線、ほかの文節は細い下線で出る。
- Apple の資料の表は、文節の移動を「↑ / Control＋B が次、↓ / Control＋F が前」、ページ送りを「8 行ずつ」と書く [SC]。実機は上の表のとおり（文節の移動は ← / →、Control＋B が前、ページは 9 件）。[MOZC] の Control＋B / F の向きは実機と同じ。

## 4. 候補ウインドウ

| キー | 動き | 出典 |
|---|---|---|
| Space、↓、Control＋N、Control＋X、Option＋L | 次の候補 | 実機 |
| Shift＋Space、↑、Control＋P、Control＋E | 前の候補 | 実機 |
| Page Down、Shift＋↓、Control＋V、Control＋↓ | 次のページ（9 件ずつ） | 実機 |
| Page Up、Shift＋↑、Control＋R、Control＋↑ | 前のページ。先頭のページでは最後のページへ | 実機 |
| 1〜9 | そのページのその番号の候補を選んで窓を閉じる。変換中に留まる | 実機 |
| Return | 候補を選んで窓を閉じる。確定はしない。文節が複数なら注目を次の文節へ移す。確定はもう 1 回の Return | 実機 |
| Tab / Shift＋Tab | 窓の下のタブ（標準・読み・部首・名前・記号）を順に / 逆順に替える | 実機 |
| → / ← | 文節が複数なら、次 / 前の文節へ移って窓を閉じる。文節が 1 つなら、→ で候補の辞書の説明を横に出す | 実機 |
| Esc | 全部の文節を読みに戻し、窓を閉じる | 実機 |
| Delete | 表示の末尾 1 字を消して、残りを確定する | 実機 |
| Shift＋← / →、Control＋I / O / W / Q | 伸縮して窓を閉じる | 実機 |
| 文字キー、0 | 確定して、その字で次の入力を始める | 実機 |
| ダブルクリック | その候補を選ぶ（確定は Return） | [CW] |

- 窓の候補の並びは、Space で進む順と違う。「かんじ」では 1 かんじ（注記 Hiragana）、2 感じ、3 漢字、4 幹事、5 かんじ、6 監事、7 カンジ、8 寛治、9 完二。Space の 1 回目に出る候補（感じ）は 2 番目で、↑ で 1 番目のひらがなに戻れる。
- 辞書の印（📖）の付いた候補は、→ で語の説明が出る。
- 「読み」のタブは、注目文節の先頭の字の読みで漢字 1 字の候補を並べる。「記号」のタブは、候補が無ければ「No Candidates」と出る。
- Space を押し続けると、繰り返しのたびに Space を 1 回押したのと同じに働く（変換 → 窓を開く → 次の候補 …）（実機（本物のキー））。

## 5. 確定したあと

| 操作 | 動き | 出典 |
|---|---|---|
| Control＋Delete（確定の直後） | 確定を取り消す。確定した文字が変換中に戻り、候補ウインドウが開く。文字を選ばなくてよい。そのあとの Esc は 1 回目で読みに戻し、2 回目で文字ごと消す | 実機 |
| Control＋Shift＋R / Option＋Shift＋R | 選んだ文字を再変換する。選んでいなければ、カーソルの前の 1 語（「感じ今日」の末尾なら「今日」）を再変換する | 実機 |
| かなキーをすばやく 2 回 | Control＋Shift＋R と同じく再変換する。間が 0.45 秒あると再変換にならない。英字を選んでいると英語の発音で読む（「watashi」は「ワット／アッシュ／愛」）。英字を打った直後に選ばずに押すと、末尾の 1 字を消すだけ | 実機 |
| 再変換中の Esc | 1 回目で読みに戻り、2 回目で元の表記を確定し直す | 実機 |
| 英数キー 2 回 | 何もしない（選んでいてもいなくても） | 実機 |
| 入力メニュー「再変換」 | 選んだ文字かカーソルの位置の語を再変換する | [UN][CH] |
| 選んで Control＋1 | 選んだ文字の先頭の 1 字の関連文字を、候補ウインドウに出す（「感じ」なら「感」） | 実機、[PCW1] |
| 選んで Control＋2 | 部首などで漢字を探す一覧を、候補ウインドウに出す（「感じ」なら 憾・撼・轗 …） | 実機、[PCW1] |

- この節の動きは、アプリが選択範囲・置き換え範囲（`replacementRange`）・確定済みの文字を日本語入力プログラムに返すことが前提。AppKit の標準のテキスト欄（`NSTextView`）では上の表のとおり動く。
  それらを返さないアプリでは、選んでいないときの再変換・かな 2 回や、Control＋1・Control＋2 が動かない。
- Apple の資料は、かなキー 2 回を「英字をかなに変換」、英数キー 2 回を「かなを英字に変換」、Control＋Delete を「変換を取り消す」とする [SC]。
- 確定したあと、入力が無いときの Control＋英字（A / E / F / B / N / P / K / D / H / T / Y / O / V）は、アプリの編集のコマンドになる（実機）。

## 6. 入力ソース・入力モードの切り替え

| 操作 | キー | 条件・動き | 出典 |
|---|---|---|---|
| 直前の入力ソースへ | Control＋Space | 入力中なら確定してから切り替える。押し続けると一覧 | 実機（本物のキー）、[SW] |
| 次の入力ソースへ | Control＋Option＋Space | このショートカットが有効なら、入力中でもキーは日本語入力プログラムに届かない（§1 の同じキーの行は、届いたときの動き） | [SW] |
| 英字（ABC）へ | 英数キー | 入力中・変換中なら確定してから切り替える | 実機 |
| ひらがなへ | かなキー | | 実機 |
| ひらがなへ | Control＋Shift＋J / Option＋Shift＋Z | | [SW] |
| 英字へ | Control＋Shift＋'（JIS は Control＋Shift＋;） | ローマ字入力の入力ソースが必要 | [SW] |
| 全角英字へ | Control＋Shift＋L | 入力モードで全角英字を有効にしている場合 | [SW] |
| カタカナへ | Control＋Shift＋K / Option＋Shift＋X / （JIS）Shift＋かなキー | 入力モードでカタカナを有効にしている場合 | [SW] |
| 半角カタカナへ | Control＋Shift＋; | 入力モードで半角カタカナを有効にしている場合 | [SW] |

**Caps Lock と fn / 地球儀キー**

| キー | 設定 | 動き | 出典 |
|---|---|---|---|
| Caps Lock | システム設定 › キーボード › テキスト入力 の「Caps Lockキーで…と切り替える」がオン | ラテン系 ↔ 非ラテン系の入力ソースを切り替える | [SW] |
| Caps Lock | 上の設定がオフ、「Caps Lockの動作」（§10）が既定 | ランプが点く / 消えるだけ。入力ソースは変わらず、ランプが点いていても英字はかなになり、入力中の文字もそのまま残る | 実機（本物のキー） |
| Caps Lock | 「Caps Lockの動作」でカタカナか英字を選んだとき | ランプが点いている間、カタカナか英字を入力する | [SET] |
| fn / 地球儀キー | システム設定 › キーボード の「fn キーを押して」が「入力ソースを変更」 | 最近使った順の入力ソースの一覧を、押すたびに 1 つ先へ進めて切り替える。1 回押すと直前に使った入力ソース、すばやく 2 回で 2 つ前、3 回で 3 つ前。押す間が 1 秒あくと、それぞれが 1 回押しになる（2 回押すと元に戻る）。押し続けてから離すと切り替わらない。入力中なら確定してから切り替える | 実機（本物のキー）、[SW] |
| fn / 地球儀キー | 同上 | 押すと画面の中央に入力ソースの一覧（ABC、日本語、中国語（簡体字）など）が出る。文字の入力中は、入力欄のすぐ下に A・あ・한・拼 のような入力ソースの表示が出る | 利用者 |
| fn / 地球儀キー | 「fn キーを押して」が「何もしない」 | 何も起きない | 実機（本物のキー） |

- 入力モードがひらがなだけのとき、Control＋Shift＋J / K / L / ; / ' は入力中も変換中も何もしない。英字（ABC）から Control＋Shift＋J でひらがなには切り替わらない（実機）。
- [CH] は「JIS キーボードがない場合、ひらがな入力モードは Control＋Shift＋J、ローマ字入力モードは Control＋Shift＋;」と書く。
- 「Shiftキーの動作」（§10）が「英字モードに入る」なら Shift＋英字で英字モード（§1）、「カタカナを入力」なら Shift＋英字でその 1 字をカタカナで入れる（Shift＋A で「ア」）（実機）。Shift を単独で押して離しても、どちらの設定でも何も起きない（実機（本物のキー））。

## 7. 記号・そのほかの入力

| 操作 | キー / 方法 | 出典 |
|---|---|---|
| 【 / 〔 | Option＋9 / Option＋Shift＋9（US 配列） | 実機 |
| 【 】〔 〕 | Option＋8 / 9 / Shift＋8 / Shift＋9（ひらがなモード）。US 配列の実機では Option＋8 は •、Option＋Shift＋8 は ° | [SYM] |
| … | Option＋; | 実機、[SYM] |
| 全角数字（かな入力ソースで「数字を全角入力」がオン） | Option を押しながら数字キー | [NUM] |
| 矢印記号 | z に続けて h / j / k / l | 実機、[PCW1] |
| 小書き文字 | l または x に続けてかな | 実機、[PCW1] |
| 文字ビューア | Command＋Control＋Space | [PCW1] |
| 仮名表 | 入力メニュー（キーは無し） | [KANA] |
| プライベートモード | 入力メニュー（キーは無し）。学習しない、連絡先などを使わない | [PRIV] |
| ユーザ辞書 | 入力メニュー「ユーザ辞書を編集」。読み 32 文字・語句 64 文字まで。plist で書き出し・読み込み。Apple Account で同期 | [DIC] |

## 8. ライブ変換

打つそばから読みを漢字かな混じりに変換して見せる。Space を押さなくてよい [IN]。オン / オフは入力メニュー「ライブ変換」か設定で、キーの割り当ては無い [IN][PCW1]。
オンにすると「句読点で変換」はオフになり、選べなくなる [SET][PU]。

| キー | 動き | 出典 |
|---|---|---|
| （入力しただけ） | 変換した文字が出る。文節の区切りはあるが、注目文節の太い下線は無い。予測候補の窓も出る | 実機 |
| Space | 文節を選ぶ状態に入り、候補ウインドウを開く | 実機 |
| ←、Control＋B / S | 文節を選ぶ状態に入り、最後の文節に注目して候補ウインドウを開く（カーソルは動かない） | 実機 |
| →、↑、↓、Control＋N / P / E / F / D / X | 文節を選ぶ状態に入り、先頭の文節に注目して候補ウインドウを開く | 実機 |
| Return | 確定する。候補ウインドウが開いていれば、窓を閉じるだけ | 実機 |
| Esc | 最後の文節を読みに戻す（「今日は雨です」が「今日は／あめです」）。文節を選ぶ状態からは全部を読みに戻す | 実機 |
| Delete | 読みの末尾 1 字を消す。確定しない | 実機 |
| F6〜F10、Control＋J / K / L / ; | 入力全体の字種を変える。文節を選ぶ状態では注目文節だけ | 実機 |
| Shift＋← / → | 入力しただけの状態では ← / → と同じ。文節を選ぶ状態では注目文節を縮める / 伸ばす | 実機 |
| Control＋I / O | 先頭の文節（文節を選ぶ状態では注目文節）を縮める / 伸ばす | 実機 |
| Control＋W | 文節を選ぶ状態では注目文節を伸ばす。入力しただけの状態では何もしない | 実機 |
| Option＋Space | 文節を選ぶ状態では、確定して全角の空白を入れる | 実機 |

## 9. 「Windows風のキー操作」

入力ソース設定（日本語 - ローマ字入力 / かな入力）のチェックボックス [SET][EN]。説明は「キーボードをWindowsキーボードのように操作し、Windowsと同様のショートカットを使用できるようにする」[SET]。
オンにすると「Shiftキーの動作」が自動で「英字モードで入力」になる [SET]。既定と違うキーは次のとおり（全部は [macos-table.md](macos-table.md) の最後）。

| キー | 動き | 出典 |
|---|---|---|
| F8 | 半角カタカナにする | 実機、[PCW2] |
| Control＋U / I / O / P / T | F6〜F10 と同じ（ひらがな / カタカナ / 半角英字 / 全角英字 / 半角英字） | 実機 |
| Control＋J / K / L / ; | 字種の変換に使わない。変換中の Control＋K / L は注目文節を縮める / 伸ばす | 実機、[SC] |
| Control＋Z、変換中の Delete・Control＋H | 読みに戻す（確定しない） | 実機 |
| 候補ウインドウの Return | 1 回で確定する | 実機、[PCW1] |
| 変換中の ↑ / ↓ | 前 / 次の候補を選んで候補ウインドウを開く | 実機 |
| 変換中の Page Up / Page Down | 何もしない | 実機 |
| Option＋J / L、Option＋Shift＋Z / X / R | Option の文字（∆ ¬ など）を入れる。Option＋A / C / S / X / Z の字種の変換は残る | 実機 |
| Control＋C | 確定する | 実機 |
| Control＋N | 変換中と予測候補を選んでいるときは、入力を捨てて制御文字 `\x0e` を確定する。入力中はカーソルを末尾へ動かす | 実機 |

## 10. 設定

**カスタマイズできる範囲**

| 項目 | 内容 | 出典 |
|---|---|---|
| キー 1 つずつの割り当て | 変えられない。設定画面にキー割り当ての項目は無い。複雑な割り当てにはサードパーティ製アプリが要る | [SET][APC] |
| 割り当ての切り替え | 「Windows風のキー操作」のオン / オフだけ（§9） | [SET][SC] |
| モード系のキー | Caps Lock の動作、Shift キーの動作、入力モードの有効 / 無効 | [SET] |
| システム全体 | 修飾キーの入れ替え（システム設定 › キーボード › 修飾キー）、Caps Lock・fn・地球儀キーでの入力ソースの切り替え | [SW] |

**設定項目**

開き方: 入力メニュー →「"日本語 - ローマ字入力"設定を開く」（またはかな入力）→ サイドバーで入力ソース名を選ぶ [SET]。
設定は `defaults` の `com.apple.inputmethod.Kotoeri` にある。`defaults write` で書き、日本語入力プログラムのプロセス（`JapaneseIM-RomajiTyping`）を SIGKILL で止めると、次に使うときに起動し直して読む（SIGTERM では止まらない。ライブ変換は止めなくても効く）（実機）。

| 設定 | 内容 | `defaults` のキー | 出典 |
|---|---|---|---|
| 入力モード | 使う入力モード（ひらがな / カタカナ / 全角英字 / 半角カタカナ / 英字 など） | （入力ソースの有効 / 無効。`com.apple.HIToolbox`） | [SET][SW] |
| Caps Lockの動作 | Caps Lock でひらがなからカタカナまたは英字へ切り替える。システム側の「Caps Lockで入力ソースを切替」がオンだと使えない。既定（`defaults` に値が無い）では、Caps Lock は入力に影響しない（§6） | `JIMPrefCapsLockActionKey` | [SET]、実機（本物のキー） |
| Shiftキーの動作 | 「英字モードに入る」「カタカナを入力」（§6） | `JIMPrefShiftKeyActionKey`: 未設定・1・2・3 で英字モード、0 でカタカナ | [SET][SW]、実機 |
| ライブ変換 | オン / オフ（§8）。macOS の初期値はオン | `JIMPrefLiveConversionKey`（0 / 1） | [SET]、実機 |
| タイプミスを修正 | タイプミスを自動で直し、入力中に候補を出す | `JIMPrefAutocorrectionKey` | [SET][IN] |
| Windows風のキー操作 | §9 | `JIMPrefWindowsModeKey`（0 / 1） | [SET]、実機 |
| 候補表示 | 候補ウインドウのフォントとサイズ | `JIMPrefCandidateWindowFontKey`、`JIMPrefCandidateWindowFontSizeKey` | [SET][CW] |
| 推測候補表示 | 入力中に予測候補を出す（§2） | `JIMPrefPredictiveCandidateKey` | [SET] |
| 句読点で変換 | 句読点の入力で変換する（ライブ変換オンでは使えない） | `JIMPrefConvertWithPunctuationKey` | [SET][PU] |
| 英字のレイアウト | ローマ字入力で使うキーボードレイアウト（既定は最後に使ったもの） | `JIMPrefRomajiKeyboardLayoutKey` | [SET] |
| 句読点の種類 | 使う句読点 | `JIMPrefPunctuationTypeKey` | [SET][PU] |
| "/"キーで入力する文字 | JIS で「/」か「・」か | `JIMPrefCharacterForSlashKey` | [SET] |
| "¥"キーで入力する文字 | JIS で「＼」か「¥」か | `JIMPrefCharacterForYenKey` | [SET] |
| 数字を全角入力 | 数字を全角で入力する | `JIMPrefFullWidthNumeralCharactersKey` | [SET][NUM] |
| 追加辞書 | 一覧、書き出し、テキストファイルの読み込み | `JIMPrefSpecialtyDictionariesKey` | [SET] |
| 変換学習 | 学習のオン / オフと「リセット」 | — | [SET] |
| プライベートモード | 学習しない（§7） | `JIMPrefPrivNoLearningKey`（1 で学習しない） | [PRIV]、実機 |
| （設定画面に無い） | — | `JIMPrefConvertWithArrowKey` | 実機 |

- `defaults` のキー名は `CoreJapaneseEngine.framework` の `JIMPreferences` と共有キャッシュの文字列にある。値まで書いたキー（ライブ変換、Windows風、Shiftキーの動作、プライベートモード）は実機で効くのを見たもの。ほかは、名前から設定項目との対応を推したもの。
- 変換を確定すると学習し、次から第 1 候補が変わる。試験で確定するときは、先にプライベートモードにする（学習を戻す手段は「変換学習: リセット」だけで、ふだんの学習も消える）。

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
