# 日本語 IME のキー操作の比較

主要な日本語 IME の、キー操作の特徴・カスタマイズの仕組み・機能ごとの既定キー。IME ごとの全表と出典は次のファイルにある。

| ファイル | 中身 |
|---|---|
| [ms-ime.md](ms-ime.md) | 新 MS-IME と以前のバージョンの MS-IME。旧 IME「Microsoft IME」テンプレートの状態 × キーの全表 |
| [atok.md](atok.md) | ATOK（Windows・Mac）。8 状態 × キー、割り当てできる機能、Win/Mac の差 |
| [macos.md](macos.md) | macOS 標準の日本語入力（旧ことえり）。Mac と「Windows風」、設定項目 |
| [mozc.md](mozc.md) | Google 日本語入力 / Mozc。keymap の形式、状態とコマンドの全部、プリセットの比較 |
| [reconversion.md](reconversion.md) | 再変換の仕組み（TSF・IMM32）と、Mozc・MS-IME の動き、アプリごとの違い |
| [others.md](others.md) | Japanist、SKK 系、親指シフトのソフト、ibus-anthy・fcitx5-anthy・libkkc、azooKey |

「無し」は、出典が無いと書いているもの。「資料に無い」は、出典で確かめられないもの。旧 MS-IME の「キー設定の表に無い」は、既定のキー設定の画面の表（ms-ime.md §2。割り当てのあるキーと、Shift+Enter のように割り当ての無いキーの行が載っている）のどの行にも、その機能が無いこと。

---

## 1. 各 IME の特徴（キー操作とカスタマイズの観点）

| IME | キー操作の特徴 | カスタマイズ |
|---|---|---|
| **新 MS-IME**（Win10 2004〜/Win11） | 公式の既定キーは IME オン/オフ・入力モード、F6〜F10、候補ウィンドウの操作など一部だけ。変換中の編集キーの全表は資料に無い。実機では、食べるキーの働きは旧 IME の表とほぼ同じで、割り当ての無いキーの多くを確定してアプリに通す（ms-ime.md §1.5） | テンプレート 2 つ（Microsoft IME / ATOK）＋ 4 キー（無変換・変換・Ctrl+Space・Shift+Space）を数個の機能から選ぶだけ。状態ごとの指定は無い |
| **旧 MS-IME** | Space 変換、Shift+←→ で文節伸縮、Ctrl+↓ で文節確定、Ctrl+U/I/O/P/T の字種変換、Ctrl+K/L 伸縮、Ctrl+Backspace 確定取消 | 6 状態 × キーの表の欄ごとに、用意された機能から選ぶ（キーの組み合わせも用意されたものだけ）。テンプレート 5 つ（Microsoft IME / IME Standard / ATOK / VJE / WX）。IME の画面にファイルの入出力は無く、レジストリを regedit で書き出して移す |
| **ATOK**（Win） | **←→ が文節伸縮、Shift+←→ が文節移動**（MS-IME と逆）。↓ が部分確定。Shift+Space が次候補、Ctrl+Space が全候補表示。変換キーに次の候補群・漢字／半角モード切替、Shift+変換に再変換、無変換に半角英数の固定入力。機能が多い（電子辞典、ATOK ダイレクト、校正支援、IVS など） | 8 状態 × キー。スタイル（ATOK / MS-IME）。プリセットを変えると必ず別名のスタイルとして保存。テキスト出力、旧版からのマージ移行、アプリ別の切り替え。修飾は Shift と Ctrl のみ（Alt 不可） |
| **ATOK**（Mac） | Win との違いは atok.md §1.4（Shift+Space が前候補、再変換が Ctrl+Shift+Y など） | プリセット 5 つ（ATOK / macOS 標準風 / egbridge 風 / MacVJE-Delta 風 / MS-IME 風）。複製・改名・他のスタイルから読み込み。キーは実際に押して指定する |
| **macOS 標準** | Ctrl+N/P で候補、Ctrl+H で削除、Ctrl+B/F で文節の移動、Ctrl+I・Ctrl+W/O で文節の伸縮、**Ctrl+J/K/L/;/: の字種変換**、英数/かなキー、ライブ変換 | キーは変えられない。「Windows風のキー操作」の on/off だけ |
| **Google 日本語入力 / Mozc** | 既定は Windows・Linux で MS-IME（ms-ime.tsv）、macOS でことえり（kotoeri.tsv）、ChromeOS で chromeos.tsv。Tab で予測 | **（状態, キー）→ コマンド の TSV**。プリセット（GUI では ATOK / MS-IME / ことえり。内部に mobile / chromeos / overlay）。GUI エディタ、TSV のインポート/エクスポート。引けなかったときの表（Suggestion→Composition、Prediction→Conversion、ZeroQuerySuggestion→Precomposition） |
| **Japanist**（富士通、親指シフトの本家、2021 年 5 月販売終了） | 快速親指シフトの既定（FMV-KB232 接続時）: かなモードでは親指キー単独で 左＝無変換・右＝変換。英字モードと IME オフでは 左＝無変換・右＝空白入力 | 「定義するキー × 割り当てる動作」のチェック表。1 キーに複数の機能を割り当てると優先順位で 1 つだけ動く。Japanist 2003 は MS-IME / ATOK の詳細設定を「言語スタイル」を選んで引き継ぐ。「キー動作拡張」でモードごとに親指キーの動作を変える |
| **SKK 系** | モーダル。大文字で変換開始・送り仮名を明示。▽▼、x で前候補、C-g、q でかな/カナ、l でアスキー | CorvusSKK は文字キーを正規表現、仮想キーを VK+S/C 接頭辞で指定。macSKK は既定を複製して編集、変えた行を太字、行ごとにリセット |
| **ibus-anthy / fcitx5-anthy / libkkc** | NICOLA に対応。親指キーは、ibus-anthy が `rs`/`ls`（既定 Henkan/Muhenkan、任意のキーにできる）、fcitx5-anthy が左 Muhenkan・右 Henkan と space、libkkc が Muhenkan（左）・Henkan（右）をコードに直書き | プリセット（ibus-anthy: default/atok/wnn、fcitx5-anthy: Default/ATOK/Canna/MS-IME/VJE-Delta/WNN/Custom）。ibus-anthy は「コマンド名 → キーのリスト」。libkkc は入力モードごとの keymap（JSON）を `include` で継承する |
| **azooKey**（macOS 版。zenz を使う） | キーの解釈はソースに直書き。Ctrl+I/O と Shift+←→ で伸縮、ライブ変換が on なら Space で候補選択へ | キーで変えられるのは「いい感じ変換」のショートカット（既定 Ctrl+S）だけ |

---

## 2. 機能ごとの既定キーの比較

主要 4 系統の既定キー。各列の出典は次のとおり。

- **MS-IME 列**: 旧 MS-IME の表（[ms-ime.md](ms-ime.md) §2、テンプレート「Microsoft IME」）。丸数字はその表の状態（② 入力のみ、③ 変換済み、④ 候補一覧、⑤ 文節長変更、⑥ 文節内入力）。
  Mozc の ms-ime.tsv（[mozc.md](mozc.md) §4.1）が違うときは「（Mozc: …）」で添える。新 MS-IME の資料（ms-ime.md §1）にあるものは「新 IME:」と書く。
- **ATOK 列**: ATOK Windows 版の ATOK スタイル（[atok.md](atok.md) §1.1・§1.3）。
- **macOS 列**: Apple の資料（[macos.md](macos.md)）の Mac 既定。Mozc の kotoeri.tsv（mozc.md §4.1）が違うときは「（Mozc: …）」で添える。

Google 日本語入力 / Mozc の既定は、Windows・Linux では ms-ime.tsv、macOS では kotoeri.tsv（mozc.md §1.1）。
日本語キー（変換・無変換・かな・英数・半角/全角・ひらがな・カタカナ）は US 配列のキーボードに無いので、括弧で示す。

### 2.1 IME のオン/オフ・入力モード

| 機能 | MS-IME | ATOK | macOS |
|---|---|---|---|
| オン/オフ切替 | (半角/全角)。新 IME: Alt+`（US 配列）、(変換)/(無変換) は設定で選べる | (半角/全角)（101/104 での代わりは資料に無い） | 切替のキーは資料に無い。入力ソースの切り替えは Ctrl+Space（前）/ Ctrl+Option+Space（次） |
| オンにする / オフにする（別々） | ImeOn（ひらがなキー）/ ImeOff（IME オフ）（ms-ime.md §2.2）。新 IME: ImeOn（ひらがな）/ ImeOff（半角英数）（Mozc: オン = (英数)・(ひらがな)・(カタカナ)・F13・ON、オフ = OFF） | (変換) でオンにできる。オフだけのキーは資料に無い（機能「日本語入力OFF」はある） | (かな)（ひらがなへ）/ (英数)（英字へ） |
| ひらがな・カタカナ・英数の入力モード | (ひらがな)、(カタカナ)、(英数)（かな英数）、(無変換)（かな切替）、Shift+(無変換)（英数切替）。新 IME の US 配列: Ctrl+CapsLock（ひらがな）、Shift+CapsLock（英数）、Alt+CapsLock（カタカナ。出典で食い違う、詳細は ms-ime.md §1.2） | (無変換)（半角英数の固定入力）、Shift+(無変換)（固定入力英字の順次切替）、Ctrl+(無変換)（固定入力カナの順次切替）、(変換)（漢字／半角モード切替） | Ctrl+Shift+J（ひらがな）/ K（カタカナ）/ L（全角英字）/ '（英字）、Option+Shift+Z/X、Ctrl+Shift+; は出典で食い違う（詳細は macos.md §3） |
| 一時的な英数入力 | 和英混在入力の設定「Shift キー単独で英数モードに切り替える」。一時的かどうかは資料に無い（Mozc: 設定「シフトキーでの入力切替」、既定は英数字） | Shift+文字キー（英語入力モード）。(Caps Lock英数) で英語入力モードのオン/オフ | Shift（「Shiftキーの動作」が英字モードのとき。Return で元に戻る） |

### 2.2 入力中（変換前）

| 機能 | MS-IME | ATOK | macOS |
|---|---|---|---|
| 変換 | Space、Shift+Space、(変換) | Space、Shift+Space、(変換) | Space |
| 全確定 | Enter、Ctrl+M、Ctrl+Enter | Enter、Ctrl+M（Shift+Enter は出典で食い違う、詳細は atok.md §1.3） | Return（Mozc: Ctrl+M も） |
| 部分確定（先頭の文節） | キー設定の表に無い（② の Ctrl+↓・Ctrl+N は文字末尾） | ↓、Ctrl+N（Mozc の atok.tsv では全確定） | 資料に無い |
| 1 字ずつ確定 | Shift+↓（1文字確定）（Mozc: 割り当て無し） | Shift+↓（1 音確定） | 資料に無い |
| 1 打 / 1 字消す（左） | BS、Ctrl+H、Shift+BS、Ctrl+BS | BS、Ctrl+H | Delete、Ctrl+H |
| カーソルの右を消す | Del、Ctrl+G | Del、Ctrl+G | 資料に無い（Mozc: Del、Ctrl+D） |
| 全部消す | Esc、Shift+Esc、Ctrl+Z。新 IME（実機）: ② の Ctrl+Z は何もしない | Esc、Ctrl+[ | Esc、Clear |
| カーソル移動 ←→ | ←→、Shift+←→、Ctrl+K/L、Ctrl+S/D | ←→、Ctrl+K/L | ←→、Ctrl+S/D（Mozc: Ctrl+B/F、Option+J/L。Ctrl+D は右を消す） |
| 先頭 / 末尾へ | Home/End、Ctrl+A/F、Ctrl+←/→、Ctrl+↑/↓、末尾は Ctrl+N も（Mozc: Ctrl+E で先頭、Ctrl+X で末尾も） | Ctrl+←/→ | 資料に無い（Mozc: Ctrl+A/E、Home/End、Ctrl+←/→） |
| ひらがな | F6、Ctrl+U | F6、Ctrl+U | F6、Ctrl+J |
| 全角カタカナ | F7、Ctrl+I | F7、Ctrl+I | F7、Ctrl+K |
| 半角カタカナ | F8、Ctrl+O（機能名は「半角」） | F8、Ctrl+O（機能名は「半角（後）変換」） | F8、Ctrl+;（入力モードで半角カタカナを有効にしたとき。既定は半角英字） |
| 全角英数 | F9、Ctrl+P | F9、Ctrl+P | F9、Ctrl+L |
| 半角英数 | F10、Ctrl+T | F10、Ctrl+@ | F10、Ctrl+:（ローマ字に変換）、F8、Ctrl+;（ローマ字（半角英字）に変換。既定）（Mozc: F10、Ctrl+:、Ctrl+'） |
| 予測を出す | Tab（Mozc: サジェスト表示中は ↓ も）。新 IME: Tab・Shift+Tab・↓・↑ で予測候補ウィンドウに入る | Tab（推測変換）。推測候補が出ているときは Tab・↓ でほかの推測候補 | 推測候補は自動表示。キーで選ぶ方法は資料に無い（Mozc: Tab、サジェスト表示中は ↓・Ctrl+N） |
| 予測を選んで確定 | キー設定の表に無い（Mozc: Shift+Enter で最初のサジェスト）。新 IME: 予測候補ウィンドウで Enter | Shift+Enter、Ctrl+Enter（自動表示候補確定。入力中の Shift+Enter は出典で食い違う、詳細は atok.md §1.3） | 資料に無い（Mozc: Shift+Enter で最初のサジェスト） |
| 学習を使わずに変換 | キー設定の表に無い（F2 は ③④⑤ の文字編集）（Mozc: F2） | 資料に無い（F2〜F5 は辞書セット変換。無学習全文確定は割付けなし） | 資料に無い（Mozc: F2） |
| 連想変換 | キー設定の表に無い | Ctrl+Tab | 資料に無い |
| 全角空白 / 半角空白 | Ctrl+Space（半角、②〜⑥）、Ctrl+Shift+Space（全角）、入力なしの Shift+Space（別幅） | 資料に無い（Shift+Space は次候補） | 資料に無い（Mozc: Option+Space で全角） |

### 2.3 変換中

| 機能 | MS-IME | ATOK | macOS |
|---|---|---|---|
| 次の候補 | Space、(変換)（③ では拡張候補、④ では次の候補）、↓・Ctrl+X（④）（Mozc: Space・↓・Ctrl+X・(変換) とも次の候補） | Space、Shift+Space、Ctrl+↓、(変換)（候補ウィンドウ表示中は次の候補群） | Space、↓、Ctrl+N |
| 前の候補 | Shift+Space、Ctrl+↑、Shift+(変換)（③④）、↑・Ctrl+E（④）（Mozc: Shift+Tab も） | ↑、Ctrl+↑ | ↑、Shift+Space、Ctrl+P（Mozc: Shift+Tab・Ctrl+E・Option+I も） |
| 次 / 前のページ | PgDn/PgUp、Shift+↓/↑（④） | (変換) / Shift+(変換)（候補群）。グループの移動は Tab・Ctrl+J / Shift+Tab | Shift+↓/↑、Ctrl+V/R、Page Down/Page Up |
| 番号で選ぶ | 数字キーはキー設定の表に無い。新 IME: 数字（Mozc: 設定「候補選択ショートカット」、既定 1〜9） | 1〜9 | 数字キー → Return で確定 |
| 全候補（一覧）表示 | Tab（④ で候補表示切替）。新 IME: Tab でテーブル表示に広げる | Ctrl+Space（全候補を表示） | 資料に無い（候補ウインドウは Space を繰り返すと出る。Tab は候補の並べ方の切り替え） |
| 前 / 次の文節へ | ← / →、Ctrl+S / Ctrl+D | **Shift+← / Shift+→** | 出典で食い違う（詳細は macos.md §2）。Apple の表は 前 = ↓・Ctrl+F、次 = ↑・Ctrl+B、候補選択ウインドウの説明は ← / →（Mozc: ← / →、Ctrl+B / Ctrl+F、Ctrl+S / Ctrl+D） |
| 先頭 / 最後の文節へ | Home/End、Ctrl+A/F、Ctrl+←/→（③） | Ctrl+← / Ctrl+→ | 資料に無い（Mozc: Home/End、Ctrl+A、Ctrl+←/→） |
| 文節を縮める / 伸ばす | Shift+←/→、Ctrl+K/L（⑤ では ↑/↓、Ctrl+E/X も） | **← / →**、Ctrl+K/L | Shift+←/→、Ctrl+I・Ctrl+W/O（Mozc: Ctrl+Q でも縮める） |
| 全確定 | Enter、Ctrl+M、Ctrl+Enter | Enter、Ctrl+M | Return（Mozc: Ctrl+M も） |
| 先頭の文節だけ確定 | Ctrl+↓、Ctrl+N | ↓、Ctrl+N | 資料に無い |
| 先頭 / 末尾の 1 字を確定 | Shift+↓（③⑤⑥ の「先頭確定」。1 字か文節かは資料に無い）（Mozc: Shift+↓ は次のページ） | PgDn / PgUp | 資料に無い |
| 変換をやめる（読みに戻す） | Esc・Ctrl+Z・Ctrl+BS・Shift+BS（文節戻し）、Shift+Esc（全戻し）（Mozc: BS・Ctrl+H・Del・Ctrl+G も） | BS、Ctrl+H（変換取消）、Insert（全変換取消。atok.md の [W36] の表には無い）。Esc・Ctrl+[ は全文字削除 | Esc（読みに戻す）、Ctrl+Delete・(かな) 2 回（変換を取り消す）。Windows風は Ctrl+Z も（Mozc: BS・Ctrl+H も） |
| 注目文節を消す | キー設定の表に無い | Shift+Del | 資料に無い |
| 字種（F6〜F10 / Ctrl 系） | F6〜F10、Ctrl+U/I/O/P/T | F6〜F10、Ctrl+U/I/O/P/@ | F6〜F10、Ctrl+J/K/L/;/: |
| 候補の学習を消す | Ctrl+Del（④ で単語削除）（Mozc: 予測候補の表示中に Ctrl+Del で履歴から削除） | Ctrl+Del（単語削除） | 資料に無い（Mozc: 予測候補の表示中に Ctrl+Del） |
| 次を打つと確定 | 資料に無い（Mozc: ○） | 資料に無い | 資料に無い（Mozc: ○） |

### 2.4 確定後・その他

| 機能 | MS-IME | ATOK | macOS |
|---|---|---|---|
| 確定取り消し | Ctrl+BS（① の確定取消）。新 IME（実機）: ① では通す（取り消さない） | Ctrl+BS（確定のアンドゥ） | 資料に無い（Mozc: Ctrl+BS） |
| 再変換 | (変換)、Ctrl+ImeOn（①）（[reconversion.md](reconversion.md)） | Shift+(変換)（Mac は Ctrl+Shift+Y） | Ctrl+Shift+R、Option+Shift+R、(かな) 2 回 |
| 単語登録を開く | Ctrl+F7（①）（Mozc: 割り当て無し） | Ctrl+F7 | キーは資料に無い（入力メニュー「ユーザ辞書を編集」） |
| 設定を開く | キー設定の表に無い（Ctrl+F10 は ① のメニュー） | Ctrl+F12 | キーは資料に無い（入力メニュー） |
| IME パッド・文字パレット・絵文字 | F5・Ctrl+Y（IME パッドの部首・コード変換）。新 IME: Win+.（絵文字。OS の機能） | Ctrl+F11（文字パレット） | Command+Control+Space（文字ビューア） |
| 辞書を引く | 資料に無い | End（情報ウィンドウ）、Shift+Ctrl+End（電子辞典の部分一致検索） | 資料に無い |

### 2.5 系統ごとの違いのまとめ

- **MS-IME 系**（旧 MS-IME、Google 日本語入力の既定）: ←→ が文節移動、Shift+←→ が伸縮。
  azooKey（macOS）は Shift+←→ が伸縮で、候補選択中の → は選んだ文節を確定して次の文節へ移る（← の動作は others.md §5.1 の表に無い）。
- **ATOK 系**: ←→ が伸縮、Shift+←→ が文節移動（逆）。↓ が部分確定（MS-IME 系では ↓ は候補一覧での次の候補）。Shift+Space が次候補、Ctrl+Space が全候補表示。
- **macOS 系**: Ctrl+J/K/L/;/: の字種、Ctrl+N/P（候補）、Ctrl+B/F（文節）、Ctrl+H（削除）。Mozc の kotoeri.tsv は Google による模倣で、Ctrl+B/F の向きなど Apple の資料と違う所がある（macos.md §2）。
- **Ctrl+英字** は 3 系統で意味が違う（例: Ctrl+K は MS-IME/ATOK で縮める・カーソル左、macOS でカタカナ）。
- **Space** はどの系統も変換と次の候補（旧 MS-IME の ③ では拡張候補）。**Shift+Space** は MS-IME 系で前候補、ATOK(Win) で次候補、ATOK(Mac)・macOS で前候補。入力なしでは旧 MS-IME で別幅の空白（Mozc は 3 プリセットとも InsertAlternateSpace）。

---

## 3. IME ごとの資料

| IME | 資料 | 出典の状況 |
|---|---|---|
| MS-IME | 新 MS-IME の実機の動き（[ms-ime.md](ms-ime.md) §1.5）、旧 MS-IME の表（ms-ime.md §2）、Mozc の `ms-ime.tsv`・`chromeos.tsv`（[mozc.md](mozc.md)） | 実機の動きは TSF のアプリで採った。旧 IME の表と Mozc は照合でき、違う所は §2 の「（Mozc: …）」。旧 IME の表はキー設定の画面と同じで、「–」は割り当てなし |
| ATOK | ATOK Windows の公式マニュアル（[atok.md](atok.md)）と Mozc の `atok.tsv` | 公式マニュアルの表は状態別ではない。状態別の表は利用者が改変したエクスポート [GIST34]。出典で食い違う所がある（Ctrl+F8、入力中の Shift+Enter など。atok.md §1.1・§1.3） |
| macOS（ことえり） | Apple の資料（[macos.md](macos.md)）と Mozc の `kotoeri.tsv` | Apple の資料は状態別の表を持たない。文節の移動のキーと Ctrl+B/F の向きは出典で食い違う（macos.md §2） |
| Japanist | 資料に無い | 状態 × キーの全体表は資料に無い（others.md §1.4） |
| SKK | ddskk・CorvusSKK・macSKK の既定（others.md §2） | モーダル入力で、入力モードと変換モード（▽▼）が独立している（others.md §2.1） |

- **US 配列で使えないキー**: 変換・無変換・かな・英数・半角/全角・ひらがな・カタカナの行は効かない。Mozc の `chromeos.tsv` は `ms-ime.tsv` から日本語キーの行を消したもので（mozc.md §4.3）、
  消える行には再変換（Henkan）、オン/オフ、入力モード（Hiragana・Katakana・Muhenkan・Eisu）の行がある。各 IME の US 配列での代わり:
  新 MS-IME は Alt+`` ` ``・Ctrl/Shift/Alt+CapsLock、ATOK は CapsLock（Caps Lock英数の代わり）・Shift+Ctrl+CapsLock（カタカナひらがなの代わり。半角/全角の代わりは資料に無い）、macOS は Ctrl+Shift+J/'。
  これらが US 配列でどの仮想キーコードとして届くかは [windows.md](windows.md) §3。
- **Space**: どの IME の既定でも Space は変換・次候補。ibus-anthy と fcitx5-anthy は、親指キーの単独打鍵（ibus-anthy はタイムアウトか文字キーなしで離したとき、fcitx5-anthy はタイムアウトしたとき）を
  通常のキー表で処理する（others.md §4.1・§4.2）。右親指を space にすれば、キー表の Space が Space の単独打鍵として働く。
  やまぶきR には、右親指を Space にして単独打鍵で変換する実例がある（others.md §3.2）。awase で Space を親指キーにしたときに単独打鍵で変換をどう起こすかは資料に無い（others.md §3.5）。
  NICOLA 規格の単独打鍵（任意仕様）「左親指＝無変換・右親指＝変換」は、左右の親指キーをスペースバー 1 つで兼ねると使えない。
- **Alt**: ATOK は Alt を修飾に使えない。Alt+`` ` `` は新 MS-IME（US 配列）と CorvusSKK でオン/オフ、libkkc で直接入力。Mozc の 3 プリセットの表には無い。
- **公式の一覧が無いもの**: 新 MS-IME の変換中の編集キー（文節伸縮・部分確定・Ctrl+英字）と Ctrl+Space / Ctrl+Shift+Space の空白。実機で見た動きは ms-ime.md §1.5。
- **資料に無いこと**: ATOK Windows の Insert・Ctrl+Insert の現行の割り当て。macOS の Tab で推測候補を選べるか、Windows風のときの Ctrl+J/K/L。
  Mozc で同じ（状態, キー）が重複したときの優先。Japanist の状態 × キーの全体表。
- **出典で食い違うこと**: ATOK Windows の Ctrl+F8・Shift+F8（変換辞書切替メニュー）と入力中の Shift+Enter（atok.md §1.1・§1.3）。macOS の文節の移動のキーと Ctrl+B/F の向き（macos.md §2）。

---

## 4. 編集画面の先行例

- **Mozc**: 状態・キー・コマンドの 3 列。キーは実際に押して入れる。プリセットからのインポート、TSV の読み書き。
- **macSKK**: 既定は編集できず、複製して編集する。変えた行を太字で示し、行ごとに既定へ戻せる。
- **ATOK**: プリセットを変えると必ず別名のスタイルとして保存する。旧版からのマージ、テキストでの書き出し。行を機能にするかキーにするかを切り替えられ、［キーを検索］で押したキーの割り当てを探せる。
- **新 MS-IME**: 4 つのキーの機能を選べるだけ。評価は分かれる（@IT は使いにくいとし、さくらのナレッジは分かりやすくなったとする。ms-ime.md §4.5）。
- 1 つの操作に複数のキー: ibus-anthy は「コマンド名 → キーのリスト」、Japanist は「定義するキー」×「割り当てる動作」のチェック表、macSKK は 1 つのアクションに複数のキー、Mozc は同じ操作を何行にも書く。
  重なったときは、Japanist は優先順位で 1 つだけ動き、CorvusSKK は文字キーと仮想キーの設定が重なると仮想キーを優先する。Mozc は資料に無い。
