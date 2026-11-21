# その他の日本語入力と親指シフト関連ソフトのキー操作

MS-IME・ATOK・macOS の日本語入力・Google 日本語入力 / Mozc 以外の日本語入力（Japanist、SKK 系、Linux 系、azooKey ほか）と、親指シフトのエミュレータのキー操作・カスタマイズの仕組み・親指キーの扱い。
出典に無いものは「資料に無い」と書く。ソースコードの値にはファイルパスを添える。出典は §6 の略号で示す。

## 1. Japanist 2003 / Japanist 10（富士通）

### 1.1 製品の状況

| 項目 | 内容 | 出典 |
|---|---|---|
| 位置づけ | 富士通の日本語入力システム。OAK の後継で、親指シフト（OASYS 系）の本家 | [JP-FAQ] |
| 販売・サポートの終了 | 2020-05-19 に親指シフトキーボード、OASYS V10.0、Japanist 10 の販売終了とサポート終了を発表。販売終了は 2021 年 5 月、サポートは 2024 年 5 月以降に順次終了 | [PCW][GDM] |
| 製品サイト | 2026-03-20 に公開を終了し、アーカイブ PDF だけが残る | [JP-FAQ] の冒頭 |
| Japanist 2003 の制約 | ストアアプリ（UWP）の入力欄に対応しない（Windows 10 20H2 以降のエクスプローラーの検索ボックスなど）。USB の親指シフトキーボード FMV-KB232 には Rel.11 以降が必要。Windows 10 では Japanist 10 を推奨 | [JP-FAQ][KB232] |

### 1.2 親指キーと変換・無変換・空白の関係（快速親指シフト）

「快速親指シフト」は、JIS キーボードで親指シフトを再現するエミュレーション機能。動作環境 → キーボード → 快速親指シフト で有効にし、かな入力に切り替えて使う。

**FMV-KB232 を接続した場合の「快速親指シフトの設定」の既定値**:

| キー \ モード | かなモード | 英字モード | IME オフ |
|---|---|---|---|
| 親指左シフト | 親指左 / 無変換 | 無変換 | 無変換 |
| 親指右シフト | 親指右 / 変換 | 空白入力 | 空白入力 |

- かなモードでは、親指キーは「同時に押せばシフト、単独なら無変換 / 変換」という兼用になる。
- 「キー動作拡張」タブで、モードごとの動作を変えられる。例: 親指左シフトの「IME Off」を「無変換」から「かなモードへ」に変えると、IME オフのときに左親指でかな入力を始められる。
- 変換 / 無変換キーの最終的な動作は、この表に加えて次の設定にも左右される: 「英数/カナモード時の変換/無変換キーによる動作」（例: 「かなモードへ移行する」で OAK と同じ動作になる）、「無変換キーによるモード変更」。
- 英字モードと IME オフでは、変換キーの既定動作は「空白入力」。

出典: [JP-FAQ] の「FMV-KB232 を使うと…」と「OAK のように英字モードの時の変換キーでかなモードにしたい」の項。補足: [DOHEN]。

**JIS キーボードでの割り当て例**（個人サイトの紹介。Japanist の既定値かどうかは資料に無い）: 「無変換」キー = 空白、「空白」キー = 無変換 兼 左親指、「変換」キー = 変換 兼 右親指。物理的なスペースバーを左親指キーにする構成。出典: [EEE]。

**ベースとなるキー配列**（Japanist 2003）: 「標準 [モード1: かなを親指配列]」「KB211風 [モード1]」「KB611風 [モード2: かなと記号を親指配列]」。KB211風 / KB611風 では【：】【］】を【後退】【取消】に割り当てられる。USB キーボードには「BackSpace キーの入れ換え: `:` キーと入れ換える」「Esc キーの追加: `]` キーを ESC キーとして追加する」がある。出典: [JP-FAQ]。

**同時打鍵の判定時間の設定**: 資料に無い。

### 1.3 キーカスタマイズの仕組み

| 項目 | 内容 | 出典 |
|---|---|---|
| キー設定画面 | 動作環境（2003 では「動作環境（詳細表示）」）→ キーボード → キー設定。「追加」→「機能キーの追加」ダイアログを開き、右の「割り当てる動作」にチェックを入れ、左の「定義するキー」からキーを選ぶ | [JP-FAQ] |
| 1 キーに複数の機能 | 割り当てられる。ただし重なったときは優先順位で 1 つだけ動く（例: 「かな漢字 ON/OFF」が「半角/全角」より優先）。富士通は 1 キーに 1 機能を推奨 | [JP-FAQ] |
| 変換 / 無変換の動作 | キー設定とは別に、動作環境の「変換」「動作」ページにも設定がある | [JP-FAQ] |
| 他社 IME 風のスタイル | 「MS-IME や ATOK などと同じように操作できる」。動作環境の変更や、「動作環境/辞書の初期設定」での環境移行で似た操作感にできる。Japanist 2003 は MS-IME 2002/2000/98 と ATOK 15/14/13 の詳細設定を自動で引き継げる（「言語スタイル」を選ぶ）。起動は「便利な玉手箱」→「移行ウィザードを起動」 | [JP-FAQ] |
| OAK / 旧 Japanist からの移行 | 同じウィザードで引き継げる | [JP-FAQ] |
| OASYS 風の確定動作（個人サイトの推奨） | 「よみを確定キーで確定する」「確定時の機能キーを有効とする」「かな/英数切替えで変換結果を確定する」を ON、Japanist 2002/2003 では「変換中の文節移動はループする」を OFF | [OYAKEY] |
| スタイル一覧（「Japanist」「MS-IME」「ATOK」などのプリセット名） | 正式な名称と一覧は資料に無い。[OYAKEY] に「FMV DC」というスタイル名がある（ページは文字化けしている） | [OYAKEY] |

### 1.4 既定キー（FAQ に出てくるもの）

| キー | 状態 | 動作 | 出典 |
|---|---|---|---|
| 変換（右親指単独） | 確定済みの文字列の前にカーソル | 再変換（記号の選び直し、丸数字などの表現の変更も） | [JP-FAQ] |
| Ctrl+変換 | 読みの入力中 | 入力予測の候補リストを選ぶ | [JP-FAQ] |
| Ctrl+Shift+M | 読みの入力中 / 変換後 | 郵便番号 ⇔ 住所の一発変換 | [JP-FAQ] |
| Ctrl+→ | 確定前 | メニュー（例: 「クイック和英」で和英の候補） | [JP-FAQ] |
| 変換 / 無変換 | 英字モード / IME オフ | 既定は空白入力 / 無変換（§1.2 の表） | [JP-FAQ] |

状態 × キーの全体表（文節の伸縮、確定、取消、カタカナ変換など）は資料に無い。

### 1.5 特徴的な機能（[JP-FAQ]）

- 入力予測（「おてがる入力」）。記録は暗号化され、移行できない。
- 推敲辞書、俊敏辞典（国語・和英を引ける）、クイック和英。
- オプション辞書（旧字・異体字、顔文字）。
- 「変換方式」は「自動変換」「複文節変換」「文節変換」から選ぶ。
- 「出力コード」→「変換コード系: インターネット用」で、半角カナと機種依存文字の入力を抑える。
- 手書き入力パネル（変換 / 無変換ボタン）。

## 2. SKK 系

### 2.1 思想: モーダル入力、送り仮名を明示する

| 観点 | SKK | 一般的な IME（MS-IME など） |
|---|---|---|
| 変換の範囲 | ユーザーが大文字で見出し語の開始を明示する（▽）。形態素解析はしない | IME が文節を区切って自動で変換する |
| 送り仮名 | 送り仮名の始まりを大文字で明示する（`KaKu` → 書く）。システムが分解しなくてよいので、速く当たりやすい | IME が推定する |
| 入力モード | 「入力モード」（文字種: かな/カナ/全英/アスキー）と「変換モード」（■ 直接、▽ 見出し語、▼ 変換中）が独立している | 入力モードと未確定状態 |
| 確定 | 印字できる文字を続けて打つと暗黙に確定する | Enter が中心 |

出典: [DDSKK]、AquaSKK の説明 "An input method without morphological analysis."（[AQUASKK]）

### 2.2 ddskk（Emacs）の基本キー

| キー | 状態 | 動作 |
|---|---|---|
| `C-x C-j` / `C-x j` | 任意 | SKK モードのオン/オフ |
| `q` | かな/カナ | かな ⇔ カナの切替（`skk-toggle-kana`） |
| `l` | かな/カナ | アスキーモードへ（`skk-latin-mode`） |
| `L` | かな/カナ | 全英モードへ（`skk-jisx0208-latin-mode`） |
| `C-j` | アスキー/全英 | かなモードへ（`skk-kakutei`） |
| 大文字（例 `K`） | ■ | ▽ モードに入る（見出し語の開始） |
| `Q` | ■ | 後から ▽ モードに入る |
| `SPC` | ▽ / ▼ | ▽→▼（辞書を引く）。▼ では次の候補 |
| `x`（`C-p`） | ▼ | 前の候補 |
| `C-j` | ▼ / ▽ | ▼ では確定。▽ では ■ に戻る |
| `C-g` | ▽ / ▼ | 見出し語を消して抜ける / 取消 |
| `RET`、印字できる文字 | ▼ | 暗黙の確定 |
| 送り仮名の大文字（`U g o K u`） | ▽ | 送り仮名の開始を示し、▼ で変換する |
| `A S D F J K L` | 候補一覧 | 候補を選ぶ |
| 辞書にない語 | ▼ | ミニバッファの辞書登録モードに入る。`RET` で登録、`C-g` で中止 |
| `/` | ■ | abbrev モード（英字の見出し語で変換）† |
| `X` | ▼ | 誤って登録した候補の削除 † |
| `>` | ▽ / ▼ | 接頭辞・接尾辞の変換 † |

出典: [DDSKK]。† の行は [DDSKK] に無く、CorvusSKK（§2.3、[CORVUS]）と macSKK（§2.4、[MACSKK-KB]）の既定値にある。

### 2.3 CorvusSKK（Windows TSF）

Windows の TSF で動く SKK。

**キーの指定方法（2 系統）**

| 種類 | 指定方法 | 備考 |
|---|---|---|
| キー設定（ON/OFF） | 仮想キーコード + Alt/Ctrl/Shift の組み合わせ。ON と OFF でそれぞれ最大 8 行 | 既定: ON = Alt+\`（0xC0）、漢字（0x19）、半角/全角（0xF3/0xF4）、IME On（0x16）。OFF = Alt+\`、漢字、半角/全角、IME Off（0x1A） |
| キー設定（文字） | ASCII の範囲の文字を **ECMAScript の正規表現**で指定する | 正規表現が不正なら、警告なしでその機能が無効になる |
| キー設定（仮想キー） | VK コードで指定する。Shift は `S`、Ctrl は `C` を前に付ける（例: Shift+Tab = `S\x09`） | 文字キーの設定と重なったら仮想キーを優先する |

**文字キーの既定値**

| 機能 | 既定 |
|---|---|
| かな/カナ | `q` |
| ｶﾅ全英変換 | `Ctrl+q` |
| 全英 | `L` |
| ASCII | `l` |
| abbrev | `/` |
| 接辞 | `<` `>` |
| 次候補 | Space, `Ctrl+n` |
| 前候補 | `x`, `Ctrl+p` |
| 辞書削除 | `X`, `Ctrl+x` |
| 次補完 / 前補完 | `Ctrl+i`（Tab） / `Ctrl+u` |
| 補完と変換 | `Ctrl+c` |
| 直接入力 | `0`〜`9` |
| 確定 | `Ctrl+m`（Return）, `Ctrl+j` |
| 取消 | `Ctrl+g`, `Ctrl+[`（Esc） |
| 後退 / 削除 | `Ctrl+h` / `Ctrl+d`, DEL |
| 左移動・先頭 / 右移動・末尾 | `Ctrl+b`・`Ctrl+a` / `Ctrl+f`・`Ctrl+e` |
| 貼付 | `Ctrl+y`, `Ctrl+v` |
| ひらがな、絞り込み、変換位置、*無効*、再変換 | 文字キーの既定なし |

**仮想キーの既定値**: ひらがな = Ctrl+J（0x4A）、次候補 = PgDn、前候補 = PgUp、前補完 = Shift+Tab、削除 = Delete、左/上 = 左移動/先頭移動、右/下 = 右移動/末尾移動、*無効* = Ctrl+J（「ひらがな」と同じキー。理由は資料に無い）。

**そのほか**

| 項目 | 内容 |
|---|---|
| 変換位置指定 | 「開始・代替・送り」の 3 列、最大 256 行。AZIK 風の例: `KaQ` →「▽か*ん」、辞書の検索キーは「かn」 |
| ローマ字・仮名変換表 | 最大 32768 行。列はローマ字・ひらがな・カタカナ・半角カタカナ・「促/ん」フラグ・「待機」フラグ。待機 = 次のキーまで仮名の確定を遅らせる。UTF-16LE (BOM) または UTF-8 の TSV でインポート/エクスポートできる |
| 候補一覧の選択キー | 数字（1〜9 で固定）、表示（必須）、予備 1・2 |
| 補完 | 通常補完、複数補完、動的補完、複数動的補完。後方一致にも対応 |
| プライベートモード | Ctrl+Shift+F10。InputScope が IS_PRIVATE の入力欄では自動で入る。辞書を更新しない |
| 動作設定 | 「送り仮名で変換開始」「後退時に確定」など（既定値は資料に無い） |
| 仮想キーのテスト | 設定画面の「仮想ｷｰﾃｽﾄ」欄にキーを押すと VK コードが表示される |
| 親指シフト / NICOLA | 対応しているかは資料に無い |

出典: [CORVUS]

### 2.4 macSKK（macOS）

**キーバインドセットの UI**:
- 設定 →「キーバインド」タブの Picker でセットを選ぶ。**既定セットは編集も削除もできない**。複製してから編集する。
- セット名の「…」メニューで、リネーム・複製・削除ができる。
- 既定から変えたアクションは**太字**で表示される。行をダブルクリックするか右クリック →「編集」で変える。右クリック →「リセット」でそのアクションだけ既定に戻す。
- 1 つのアクションに複数のキーを割り当てられる（Backspace = BS と ⌃H など）。

**既定のキーバインド**

| アクション | 既定 | 有効な状態 |
|---|---|---|
| ひらがなモード | ⌃J | — |
| かなカナモード切り替え | Q | 通常入力・候補選択中 |
| 入力中のかなカナ切り替え | Q | 読みの入力中 |
| 半角カナモード | ⌃Q | — |
| 直接入力 | L | — |
| 直接入力の切り替え | なし（自分で割り当てる） | ひらがな等 → 直接入力、直接入力 → ひらがな |
| 全角英数モード | ⇧L | — |
| Abbrev モード | / | — |
| 直接入力時 Abbrev モード | ⌃; | 直接入力中 |
| 未確定入力開始 | ⇧Q | — |
| Sticky Shift | ; | — |
| Enter / Space / Shift-Space | Return / Space / ⇧Space | Shift-Space は補完候補で変換を始める |
| 前の変換候補を選択 | X | — |
| Tab | Tab | — |
| Backspace / Delete | BS, ⌃H / Del, ⌃D | — |
| キャンセル | Esc, ⌃G | 未確定入力・単語登録 |
| 左/右/下/上 | ←,⌃B / →,⌃F / ↓,⌃N / ↑,⌃P | — |
| 行頭 / 行末 | ⌃A / ⌃E | — |
| 選択中の変換候補の削除 | ⇧X | — |
| 登録モードでペースト | ⌃Y | 単語登録中 |
| 選択テキストを再変換 | ⌃/ | — |
| 確定アンドゥ | ⌃⇧R | — |
| 接頭辞/接尾辞 | ⇧. (>) | — |
| 英数キー / かなキー | 英数 / かな | — |

- 2.23.0（2026-11）以降、変換候補の選択キーを任意の 9 文字にできる。
- ローマ字かな変換ルールは、カスタムのルールファイルを選んで使う。

出典: [MACSKK-KB][MACSKK-CFG][MACSKK-REL]

### 2.5 AquaSKK（macOS）

- キーバインドは `keymap.conf` で変える（例: 英数モードへの切替を x に、Shift の代わりに `;` で変換開始）。出典: [ZKPHI]
- `keymap.conf` の書式の詳細と `kana-rule.conf` は資料に無い（[AQUASKK] の README に無い）。

### 2.6 libskk / Linux の SKK

- libskk（ibus-skk、fcitx5-skk の基盤）のキー設定の仕組みは資料に無い。

## 3. 親指シフトエミュレータとキー配列ソフト

### 3.1 NICOLA 規格（基準）

| 項目 | 内容 | 出典 |
|---|---|---|
| 同時打鍵 | 押した順に関係なく、一定時間内に押されれば同時とみなしてシフト入力にする（普通のシフトキーとの違い） | [WP-OYA] |
| 単独打鍵（任意仕様） | 左親指の単独打鍵 = 無変換、右親指の単独打鍵 = 変換。英字モードでは両方とも空白 | [WP-OYA] |
| 判定時間の規定値 | [WP-OYA] に無い。[AWASE] は「NICOLA 標準 100ms」と書く（§3.5） | [WP-OYA][AWASE] |
| キーの位置 | 富士通製は親指キー 2 個が並び、その右にスペース。JIS X 4064 の附属書の図はスペースが中央 | [WP-OYA] |

### 3.2 やまぶき / やまぶきR（Windows）

| 設定項目（タブ） | 内容 | 出典 |
|---|---|---|
| 配列タブ | 配列定義ファイル（`.yab`、例: NICOLA.yab）。文字キーのキーリピート | [SOLANIWA][NSLABS] |
| 親指シフトタブ | 左右の親指シフトキーを選ぶ（**Space、変換、無変換など**）。キーごとに「連続シフト」「単独打鍵（有効/無効）」「キーリピート」 | [SOLANIWA] |
| 同時打鍵の時間範囲 | **単位は ms ではなく %**。文字キーを押した時点を 0、離したか次のキーを押した時点を 100 とし、その前半 N% 以内に親指キーが押されれば同時とみなす。**初期値 60**。利用者は 50〜100 で調整 | [KAMO][NSLABS][SOLANIWA] |
| 拡張親指シフトタブ | 拡張親指シフト 1/2（独自配列用） | [SOLANIWA] |
| 文字キー同時打鍵シフトタブ | 文字キー同士の同時打鍵（新下駄・蜂蜜小梅など）。時間範囲（%）は親指とは別に設定する | [KAMO][61C] |
| 動作モードタブ | 一時停止のショートカット（例 ScrollLock）、IME にアクセスする API（TSF / IMM）、入力言語が日本語以外のときの入れ替え、メニューが開いているときの入れ替え | [SOLANIWA][NSLABS] |
| 連続シフト | 親指キーを押したまま連続でシフト入力する。誤入力（「さーびず」など）が増えるので OFF を勧める記事がある | [NSLABS] |

**スペースを親指キーにした実例**: デスクトップ機で「右親指シフトキー = Space、単独打鍵 = 有効」にし、**右親指の単独打鍵で変換**している（ノート機は 変換 キー）。蜂蜜小梅配列の例では「Space = 左親指、変換 = 右親指」。出典: [SOLANIWA][61C]

### 3.3 紅皿（Windows）

- やまぶき系の配列ファイルを使うエミュレータ。配列ファイルでスペースキーを機能キーとして定義する改造例がある。出典: [BENI]
- 親指キーの割り当て・判定時間・単独打鍵の設定項目は資料に無い。

### 3.4 DvorakJ（Windows）

- QWERTY から NICOLA や Dvorak などへ変換する。派生配列も同梱している。**直接入力時と日本語入力時で別の配列**を使える。Ctrl を押している間だけ QWERTY に戻す（ショートカット用）。Esc、全角/半角、CapsLock などを入れ替えられる。配列は TXT の設定ファイルで書く。出典: [MADO-DVJ]
- 親指キーの割り当てと同時打鍵の判定時間の設定は資料に無い。

### 3.5 awase（Windows、Rust 製）

US 配列とスペース親指キーに明示的に対応しているエミュレータ。低レベルキーボードフックで同時打鍵を判定し、IME にはローマ字として送る。Google 日本語入力を推奨し、MS-IME にも対応する。

| 設定（config.toml） | 既定 | 内容 |
|---|---|---|
| `left_thumb_key` / `right_thumb_key` | `"無変換"` / `"変換"` | US 配列では設定画面から、左右 Alt に親指キーを載せるか、Space を親指キーにできる |
| `keyboard_model` | `"jis"` | `"us"` で US 配列 |
| `simultaneous_threshold_ms` | `100` | 「NICOLA 標準 100ms」と記載。誤判定するなら 80〜120 を試す |
| `confirm_mode` | `wait` | `wait`（もっとも正確、わずかに遅延する）/ `ngram_predictive`（n-gram 統計で閾値を調整する） |
| 単独打鍵 | 「無効」（IME オン中は単独打鍵を捨てる） | もう一つの選択肢「IME にまかせる（パススルー）」にすると、単独打鍵を IME に送り、IME 側の割り当て（例: 変換）が効く。`muhenkan_solo_tap_always_suppress` / `henkan_solo_tap_always_suppress` |
| IME 連動 | 親指シフトへ = Ctrl+Shift+変換、ローマ字へ = Ctrl+Shift+無変換、IME ON = Ctrl+変換、IME OFF = Ctrl+無変換 | `keys.ime_on` に単独キー（例 `["変換"]`）を書くと、単独打鍵で IME を開ける |
| 左 Shift の単独打鍵 | 既定で有効 | IME オンのまま半角英数入力を切り替える |
| 配列 | やまぶき互換の `.yab`（既定 `nicola_keytop.yab`） | — |

- Space を親指キーにしたときに、単独打鍵で変換をどう起こすかは資料に無い。
- v1 は v2.0.0（2026-10-04）で保守を終えた。

出典: [AWASE]

### 3.6 Lacaille（macOS）とスペース親指キーの暴発対策

- 左親指 = スペースにすると、同時押しのつもりがずれて「変換」が暴発する問題がある。
- **「初回無効」**: Lacaille の環境設定で「親指左」を「初回無効」にすると、スペースの単独打鍵 1 回目に反応せず、**2 回続けて押すと反応する**。ルーズな押し方による誤変換を防ぐ、Lacaille の「最大の目玉機能」とされる。
- 同時判定時間は 35〜45ms 程度を勧めている。
- 代わりの変換操作: 次の候補 = control+n、確定 = control+m、文節を伸ばす = control+o、縮める = control+i。かなモードのスペース入力は shift+space（半角）、option+space（全角）。
- macOS ではライブ変換を使うと変換キーをほとんど使わなくなる、という運用上の指摘もある。

出典: [SHIO-LAC]

### 3.7 その他（親指ひゅんQ、Karabiner、orz 配列など）

| 対象 | 内容 |
|---|---|
| 親指ひゅんQ（macOS） | 設定項目は資料に無い。Mac では左親指 = スペース、右親指 = かなキーで代用するのが一般的 [SHIO-SHIFT] |
| Karabiner-Elements | NICOLA の設定例はあるが、同時判定の許容時間の調整に悩む相談がある [APPLE-COMM]。詳細は資料に無い |
| orz 配列などの独自配列 | 資料に無い |

### 3.8 既存の IME で親指シフトを使う方法

| IME | 状況 | 出典 |
|---|---|---|
| MS-IME / ATOK | 富士通 FAQ は、富士通の親指シフトキーボードを使う場合の注意として「MS-IME や ATOK で親指シフト打鍵することはできません」と書く。エミュレータ（§3）と組み合わせて使う。awase は MS-IME に対応する（§3.5）。ATOK 自体に NICOLA モードがあるかは資料に無い | [JP-FAQ][AWASE] |
| Mozc / Google 日本語入力 | 公式の NICOLA 対応は資料に無い。Mozc のメンテナが 2023 年のハッカソンで NICOLA を試作した: ローマ字テーブルの「次の入力」機能、**タイムアウト特殊キー `{!}`**（一定時間入力がなければ挿入。`ab` = 同時、`a{!}b` = 逐次）、機能キーを `{henkan}` のような文字として入力。左右の親指は `{L}`=F18、`{R}`=F19。本家に取り込まれたかは資料に無い | [ZENN] |
| Japanist | 本家として対応（§1） | — |
| ibus-anthy / fcitx5-anthy / libkkc（Linux） | IME 自体が NICOLA に対応（§4） | — |

## 4. Linux 系

### 4.1 ibus-anthy

**キーバインドのプリセット**: `shortcut-type`（既定 `'default'`）で `default` / `atok` / `wnn` を選ぶ。各プリセットは「コマンド名 → キーのリスト」の辞書。

主なコマンドの既定キー（`data/org.freedesktop.ibus.engine.anthy.gschema.xml.in` から抜粋）:

| コマンド | default | atok | wnn |
|---|---|---|---|
| on_off | （ビルド時に決まる） | Henkan, Eisu_toggle, Zenkaku_Hankaku | Shift+space |
| convert | space, KP_Space, Henkan | space, Henkan, Shift+space, Shift+Henkan | space |
| commit | Return, KP_Enter, Ctrl+J, Ctrl+M | Return, Ctrl+M | Ctrl+L, Ctrl+M, Ctrl+J, Return |
| cancel | Escape, Ctrl+G | Escape, BackSpace, Ctrl+H, Ctrl+[ | Escape, Ctrl+G, Alt+Down, Muhenkan |
| predict | Tab | Tab | Ctrl+Q |
| reconvert | Shift+Henkan | Shift+Henkan | — |
| select_next_candidate | space, Tab, Henkan, Down, Ctrl+N ほか | space, Tab, Henkan, Shift+space, Shift+Henkan | space, Ctrl+Q, Ctrl+P, Down |
| select_prev_candidate | Shift+Tab, Up, Ctrl+P ほか | Up | Ctrl+N, Up |
| select_prev/next_segment | Left/Right, Ctrl+B/F | Shift+Left/Right | Ctrl+B/F, Left/Right |
| shrink / expand_segment | Shift+Left, Ctrl+I / Shift+Right, Ctrl+O | Left, Ctrl+K / Right, Ctrl+L | Ctrl+I, F13 / Ctrl+O, F14 |
| commit_selected_segment | Ctrl+Down | Down, Ctrl+N | — |
| convert_to_hiragana / katakana / half / wide_latin / latin | F6 / F7 / F8 / F9 / F10 | F6,Ctrl+U / F7,Ctrl+I / F8,Ctrl+O / F9,Ctrl+P / F10,Ctrl+@ | F6〜F10 |
| convert_to_char_type_forward | Muhenkan | — | — |
| insert_space / insert_alternate_space | space / Shift+space | 同左 | space / — |
| dict_admin / add_word | F11 / F12 | F11 / Ctrl+F7 | F11 / F12 |

**親指シフト（thumb）の設定**

| キー | 既定 | 意味（`engine/python3/engine.py` の `__process_key_event_thumb` による） |
|---|---|---|
| `rs` / `ls` | `'Henkan'` / `'Muhenkan'` | 右/左の親指キー。任意のキーにできる（Space を右親指にしている利用者の報告がある: [LP1320277]） |
| `t1` | 100 | 親指キーを先に押したとき、文字キーを待つ時間（ms、`GLib.timeout_add`） |
| `t2` | 75 | 文字キーを先に押したとき、親指キーを待つ時間（ms） |
| `keyboard-layout` / `fmv-extension` / `handakuten` | 0 / 2 / false | 配列（NICOLA-J/A/F など）と FMV 拡張 |

**親指キーの単独打鍵の扱い**: 親指キーを押して T1 以内に文字キーが来ない（タイムアウトする）か、文字キーなしで離すと、`cmd_exec(RS() or LS())` が**その親指キー（例 Henkan や space）に割り当てられたコマンドを通常のキーバインド表から引いて実行する**。つまり右親指を space にすれば、単独打鍵で `convert` / `select_next_candidate` が動く。英字モードと全角英字モードでは親指処理を通らない。

出典: [IBUS-ANTHY]（`data/org.freedesktop.ibus.engine.anthy.gschema.xml.in`, `engine/python3/engine.py`）、[FEDORA]

### 4.2 fcitx5-anthy

| 項目 | 内容 |
|---|---|
| キーバインドのプロファイル | `KeyBindingProfile`: **Default / ATOK / Canna / MS-IME / VJE-Delta / WNN / Custom**（`profile/*.sty`、scim-anthy 由来） |
| 入力方式 | ROMAJI / KANA / NICOLA |
| NICOLA の配列 | Default / Nicola-A / Nicola-F / Nicola-J / Oasys100J / Tron Dvorak / Tron Qwerty JP / Custom |
| 左親指キー | 既定 `Muhenkan` |
| 右親指キー | 既定 **`Henkan` と `space` の 2 つ** |
| 判定時間 `NicolaTime` | 既定 **200**（範囲 5〜1000） |
| 単独打鍵 | タイムアウトしたら、保留していた親指キーのイベントを `emitKeyEvent(prevThumbKey_)` で流し直し、通常のキーとして処理する（space → 変換） |

VJE-Delta プロファイル（VJE のキー操作の再現。Ctrl+S/D/E/X の WordStar 系ダイヤモンド）の抜粋: 変換 = space, Henkan。文節の移動 = Left/Ctrl+S、Right/Ctrl+D。伸ばす = Shift+Right/Ctrl+W、縮める = Shift+Left/Ctrl+Q。候補ページ = Shift+Up/Ctrl+E、Shift+Down/Ctrl+X。ひらがな = F6/Ctrl+J、カタカナ = F7/Ctrl+K、全角英 = F8/Ctrl+L、半角 = F9/Ctrl+O。全取消 = Shift+BackSpace/Ctrl+Y。

出典: [F5ANTHY]（`src/config.h`, `src/nicola.cpp`, `profile/vje-delta.sty`）

### 4.3 libkkc / ibus-kkc

- 「規則（rule）」= `metadata.json` + `keymap/*.json`（入力モードごと: default, hiragana, katakana, latin, wide-latin, hankaku-katakana, direct）+ `rom-kana/*.json`。`include` で親を継承する。ユーザーの規則は `~/.config/libkkc/rules` に置く。
- 同梱の規則: default, act, atok, azik, azik-jp106, kana, kzik, **nicola**, tcode, trycode, tutcode, tutcode-touch16x。
- default の keymap: C-g/C-c/Escape = abort、Return/C-m = commit、space/Henkan_Mode/Down = next-candidate、S-space/C-x/Up = previous-candidate、Muhenkan = original-candidate、Right/Left/C-f = 文節の移動、S-Right/C-Right/C-o = expand、S-Left/C-Left/C-i = shrink、C-BackSpace = purge-candidate、A-r = register、Tab = complete、Zenkaku_Hankaku/A-@/A-\` = 直接入力、F6〜F10 = 文字種の変換。
- NICOLA は「キーイベントフィルタ」（`metadata.json` の `"filter": "nicola"`）で実装されている。親指キーは `Muhenkan`（左）と `Henkan`（右）が**コードに直書き**。`timeout = 100000`（µs、100ms）、`overlap = 50000`（µs、50ms: 重なって押された 2 つのキーを同時とみなす時間）。

出典: [LIBKKC]（`data/rules/README.rules`, `data/rules/default/keymap/default.json`, `data/rules/nicola/metadata.json`, `libkkc/nicola.vala`）

### 4.4 fcitx5-mozc

- キーマップは Mozc と同じ（MS-IME / ATOK / ことえり などのプリセット。[mozc.md](mozc.md)）。fcitx5 固有の差は資料に無い。

## 5. その他の特徴的な IME

### 5.1 azooKey（macOS 版 azooKey-Desktop と、コミュニティによる Windows 版）

zenz 系の言語モデルを使う（Zenzai）。リポジトリには zenz v3.1 small（GGUF）と `base_n5_lm`（.marisa）が submodule として入っている [AZK-DESK]。

| 項目 | 内容 | 出典 |
|---|---|---|
| 状態 | アルファ版（「動作は一切保証できません」）。macOS 15 で検証。`brew install azooKey` か pkg でインストールする | [AZK-DESK] |
| 機能 | Zenzai（ニューラルかな漢字変換）、プロフィールプロンプト、履歴学習、ユーザー辞書、Tuner による個人最適化、ライブ変換、AZIK、カスタム入力テーブル、LLM による「いい感じ変換」 | [AZK-DESK] |
| AI 機能（OpenAI API） | 文の途中で Ctrl+S →「つづき」で続きの候補。選択範囲で Ctrl+S → 別ウィンドウで指示（丁寧に、英訳など） | [ITMEDIA] |
| キーのカスタマイズ | **できない**（キーの解釈が `Core/Sources/Core/InputUtils/Actions/UserAction.swift` に直書き）。設定できるのは「いい感じ変換」のショートカット（`TransformShortcut`、既定 ⌃S）だけ。ほかに設定できるのは句読点のスタイル、全角/半角スペース、¥ と \ | [AZK-DESK] のソース |
| Windows 版 | azooKey-Windows（fkunn1326、コミュニティのフォーク）。Rust + Swift for Windows、`regsvr32` で DLL を登録する方式（TSF かどうかは資料に無い）。Zenzai のバックエンドは CPU（非推奨）/ CUDA / Vulkan。ライブ変換、学習、辞書、いい感じ変換、予測変換。キー操作の記載はない。開発中 | [AZK-WIN] |
| Linux | fcitx5-hazkey（コミュニティ） | [AZK-DESK] |

**azooKey（macOS）のキー → アクション**（`UserAction.swift`）

| キー | アクション |
|---|---|
| Ctrl+H / Delete | backspace |
| Ctrl+M / Enter | enter |
| Ctrl+P / Ctrl+N / Ctrl+F | 上 / 下 / 右 |
| Ctrl+I / Ctrl+O | 文節を 1 つ縮める / 伸ばす（editSegment -1 / +1） |
| Ctrl+J / Ctrl+K / Ctrl+; / Ctrl+L / Ctrl+: | F6 / F7 / F8 / F9 / F10 と同じ |
| Ctrl+S | suggest（AI の続き / 置換） |
| Ctrl+Shift+U | Unicode のコードポイント入力 |
| Ctrl+Delete | forget（学習を忘れさせる） |
| Space / Shift+Space | 設定に応じて全角/半角スペース。変換 |
| 英数 / かな | 入力言語を英語 / 日本語に |
| F6〜F10 | ひらがな / カタカナ / 半角カナ / 全角英数 / 半角英数で確定 |
| 1〜9 | 候補の番号選択 |
| PageUp / PageDown | 候補のページ（selecting 中） |
| そのほかの Ctrl+キー | アプリに渡す |

**状態ごとの遷移**（`Core/Sources/Core/InputUtils/InputState.swift`）

| キー \ 状態 | composing（入力中） | previewing（第 1 候補を表示中） | selecting（候補選択中） |
|---|---|---|---|
| 文字 | 追加 | 確定してから新しい入力 | 確定してから新しい入力 |
| Enter | 確定 | 確定 | 選んだ候補を確定（残りがあれば previewing） |
| Space | ライブ変換 ON → selecting、OFF → previewing | selecting へ | 次の候補（Shift なら前の候補） |
| Esc | 入力を破棄 | 候補を隠して composing へ | ライブ変換 ON → composing、OFF → previewing |
| ↓ | selecting へ | selecting へ | 次の候補（↑ は前の候補） |
| Shift+← / → | 文節を伸縮して selecting へ | 同左 | 文節を伸縮 |
| → | 何もしない | 何もしない | 選んだ文節を確定して次の文節へ |
| Tab | 予測候補を受け入れる | 何もしない | 何もしない |
| BackSpace | 1 文字削除 | 削除して composing へ | 削除して composing へ |
| 英数 | 入力言語を英語に | 同左 | 確定してから英語に |

### 5.2 Baidu IME / Simeji（PC 版）

- キー操作とカスタマイズ（MS-IME と互換のプリセットがあるかなど）は資料に無い。

### 5.3 かわせみ（macOS、物書堂）

- 「基本的なキー操作についてもエミュレートする事が出来ます」（他の IME からの移行を説明したページ）。出典: [KAWASEMI]
- 「キー割り当て編集ツール」「ローマ字ルール編集ツール」がある（2026 年のアップデート情報。v4.0.4 は macOS 27 に対応）。出典: [MACOTAKARA]
- プリセット（ATOK 風・ことえり風など）の有無と既定キーの表は資料に無い。

### 5.4 VJE、Canna、Wnn、egbridge、WXG

| 対象 | 内容 |
|---|---|
| VJE（VACS） | VJE-Delta のキー操作は、fcitx5-anthy / scim-anthy の `vje-delta.sty` に再現されている（§4.2） |
| Canna | fcitx5-anthy に `canna.sty` のプロファイルがある（§4.2。内容は資料に無い） |
| Wnn | ibus-anthy の `wnn` プリセット（§4.1）。on_off = Shift+space、確定 = Ctrl+L ほか、取消に Muhenkan |
| egbridge（エルゴソフト、Mac） | 資料に無い |
| WXG（エー・アイ・ソフト） | 資料に無い |

## 6. 出典

| 略号 | 資料名 | URL |
|---|---|---|
| [JP-FAQ] | Japanist FAQ（富士通、アーカイブ PDF） | https://docs.fujitsu/documents/1-0019/japanist-contact.pdf |
| [PCW] | PC Watch（親指シフト製品の販売終了） | https://pc.watch.impress.co.jp/docs/news/1253289.html |
| [GDM] | エルミタージュ秋葉原（同） | https://www.gdm.or.jp/pressrelease/2020/0519/348790 |
| [KB232] | アクセス FMV-KB232 | https://access-fs.com/oasys/fmv-kb232.html |
| [DOHEN] | 東京の空の下より（親指シフト導入記 10） | http://dohenkutsu.cocolog-nifty.com/blog/2011/11/10-0e3b.html |
| [EEE] | Japanist 風に無変換キーと空白キーを入れ替える方法（eee-life、現在 404） | https://eee-life.com/kb/input/swap |
| [OYAKEY] | oyakey（tsmatsu）。ページは文字化けしている | http://www.ma.ccnw.ne.jp/tsmatsu/index.html |
| [DDSKK] | ddskk マニュアル 5. 基本的な使い方 | https://ddskk.readthedocs.io/ja/latest/05_basic.html |
| [AQUASKK] | codefirst/aquaskk | https://github.com/codefirst/aquaskk |
| [ZKPHI] | AquaSKK の設定と使い方（zkphi） | https://scrapbox.io/zkphi/AquaSKK_%E3%81%AE%E8%A8%AD%E5%AE%9A%E3%81%A8%E4%BD%BF%E3%81%84%E6%96%B9 |
| [CORVUS] | CorvusSKK README | https://github.com/nathancorvussolis/corvusskk/blob/master/README.md |
| [MACSKK-KB] | macSKK キーバインド設定 | https://mtgto.github.io/macSKK/config/keybinding.html |
| [MACSKK-CFG] | macSKK 設定一覧 | https://mtgto.github.io/macSKK/config/ |
| [MACSKK-REL] | macSKK Releases | https://github.com/mtgto/macSKK/releases |
| [WP-OYA] | Wikipedia: 親指シフト | https://ja.wikipedia.org/wiki/親指シフト |
| [SOLANIWA] | solaniwa（やまぶきR の設定） | https://solaniwa.net/my-yamabukir-settings/ |
| [NSLABS] | nslabs（やまぶきで NICOLA） | https://www.nslabs.jp/yamabuki-nicola.rhtml |
| [KAMO] | はてなの鴨澤 | https://kamosawa.hatenablog.com/entry/2019/12/21/232303 |
| [61C] | 61℃ | https://61degc.seesaa.net/article/313864400.html |
| [BENI] | 紅皿で薙刀式改造版（scrapbox） | https://scrapbox.io/chibi/%E7%B4%85%E7%9A%BF%E3%81%A7%E8%96%99%E5%88%80%E5%BC%8F%E6%94%B9%E9%80%A0%E7%89%88 |
| [MADO-DVJ] | 窓の杜レビュー（DvorakJ） | https://forest.watch.impress.co.jp/docs/review/361436.html |
| [AWASE] | awase README（英語） | https://raw.githubusercontent.com/cuzic/awase/main/README.en.md |
| [SHIO-LAC] | shiology: 左親指シフトのスペースキーを「初回無効」にすると… | https://scrapbox.io/shiology/05260-180917_%E5%B7%A6%E8%A6%AA%E6%8C%87%E3%82%B7%E3%83%95%E3%83%88%E3%81%AE%E3%82%B9%E3%83%9A%E3%83%BC%E3%82%AD%E3%83%BC%E3%82%92%E3%80%8C%E5%88%9D%E5%9B%9E%E7%84%A1%E5%8A%B9%E3%80%8D%E3%81%AB%E3%81%99%E3%82%8B%E3%81%A8%E6%84%8F%E5%9B%B3%E3%81%97%E3%81%AA%E3%81%84%E5%A4%89%E6%8F%9B%E3%81%8C%E3%81%AA%E3%81%8F%E3%81%AA%E3%82%8B |
| [SHIO-SHIFT] | shioシフト | https://scrapbox.io/shiology/shio%E3%82%B7%E3%83%95%E3%83%88 |
| [APPLE-COMM] | Apple コミュニティ（Karabiner で NICOLA） | https://discussionsjapan.apple.com/thread/10160444 |
| [ZENN] | Zenn: komatsuh（Mozc で NICOLA の試作） | https://zenn.dev/komatsuh/articles/f3be1b8890fce6 |
| [IBUS-ANTHY] | ibus/ibus-anthy | https://github.com/ibus/ibus-anthy |
| [LP1320277] | Launchpad #1320277 | https://bugs.launchpad.net/bugs/1320277 |
| [FEDORA] | Fedora の NICOLA-F/A 対応の変更履歴 | https://lists.fedoraproject.org/pipermail/scm-commits/2010-March/403811.html |
| [F5ANTHY] | fcitx/fcitx5-anthy | https://github.com/fcitx/fcitx5-anthy |
| [LIBKKC] | ueno/libkkc | https://github.com/ueno/libkkc |
| [AZK-DESK] | azooKey-Desktop | https://github.com/azooKey/azooKey-Desktop |
| [ITMEDIA] | ITmedia（azooKey の AI 機能） | https://www.itmedia.co.jp/news/article/2507/17/1250717051/2 |
| [AZK-WIN] | azooKey-Windows（fkunn1326） | https://github.com/fkunn1326/azooKey-Windows |
| [KAWASEMI] | 物書堂 かわせみ4 サポート | https://monokakido.jp/en/mac/kawasemi4/ks4/ks40015.html |
| [MACOTAKARA] | マックお宝鑑定団（かわせみのアップデート） | https://www.macotakara.jp/software/entry-52315.html |
