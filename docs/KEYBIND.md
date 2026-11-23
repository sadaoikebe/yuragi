# キーバインドを変えられるようにする詳細設計

どんなキーの割り当てを設定されても、その割り当てで操作できるようにするための、ゆらぎ側の仕組みの設計。
各プリセットの中身（どのキーに何を割り当てるか）は扱わない。

| 資料 | 中身 |
|---|---|
| [keybind/windows.md](keybind/windows.md) | この設計が前提にする Windows・TSF のキー入力の動き（キーの届き方、Alt、PreservedKey、`kbd101` の読み替え、繰り返し） |
| [keybind/ime-impl.md](keybind/ime-impl.md) | 既存の IME（Mozc、CorvusSKK、SampleIME など）が、キーをどう受け取り、繰り返しと up をどう扱っているか |
| [keybind/ime-survey.md](keybind/ime-survey.md) | 主要な日本語 IME のキー操作とカスタマイズの比較。IME ごとの全表は `keybind/` の各ファイル |
| [keybind/reconversion.md](keybind/reconversion.md) | 再変換の仕組み（`ITfFnReconversion`、IMM32 の `IMR_RECONVERTSTRING`）と、Mozc・MS-IME の動き、アプリごとの違い |
| [DESIGN.md](DESIGN.md) | 全体の構成・通信・TIP の規則 |

---

## 1. 要約

| # | 決めること | 結論 |
|---|---|---|
| 1 | データモデル | **（局面, キー）→ コマンド** の表。局面は MS-IME の状態に合わせ、親の局面から引き継ぐ（§2、§3.1、§5） |
| 2 | キーの意味を決める所 | **エンジンだけ**。エンジンの 1 つの表引きで決める（§6） |
| 3 | TIP の役目 | エンジンが作った**「食べるか」の表**を引くだけ。表はブローカー経由でパイプから受け取る。食べるかは表で決め、返事が `eat:false` ならキーを送り直す（§7、§8） |
| 4 | 既定のキー割り当て | **MS-IME のプリセット**。新 MS-IME を実機で見た動きのとおりにし、見ていないキーは旧 MS-IME の表で補う。オン/オフと入力モードは新 MS-IME の US 配列と同じ Alt+`` ` ``、Ctrl/Alt/Shift+CapsLock。ImeOn・ImeOff・変換・無変換は、その仮想キーコードが届いたときに効く（§5.1） |
| 5 | 設定ファイル | `~/.yuragi-ime/keymap.json`。旧 MS-IME と同じく、プリセットか「ユーザー定義」を選ぶ。ユーザー定義は**プリセット＋差分**で持つ（§5） |
| 6 | Space（親指キー） | 表の `Space` は「Space の単独打鍵」。修飾付きの Space は親指キーにしない（§4） |
| 7 | 文字キー | 入力なし・入力中では常に文字。変換中より先の局面でだけ割り当てられる（§4） |
| 8 | 割り当てのないキー | 入力がある間、「MS-IME」では確定してアプリに通し、「macOS」では入力を残す。Alt の押下では確定する（§4.3） |
| 9 | オン/オフ・モードのキー | TIP が自分で実行する「常時」の割り当て。Alt 付きのものは TSF の PreservedKey に登録する（§7.5） |
| 10 | キーの出来事の扱い | `OnTestKeyDown` と `OnKeyDown` は同じ答えを返す。up は食べない（§7.3、§7.4） |
| 11 | 反映 | 設定ウィンドウで保存 → エンジンが読み直す（再起動しない）→ 全アプリの TIP に配る（§8.3） |
| 12 | 食べて手元に溜めたキー | 黙って消さず、あとのキーに追い越させない。送り直したキーでフォーカスが移ったら、移動先へ持ち越す（§7.6、§7.7） |

---

## 2. 用語とモデル

```
打鍵 ──→ 和音（キー＋修飾） ──→ [ 局面 ] で表を引く ──→ コマンド ──→ 実行
                                    │                      │
                                    │                      └ キーの行き先（食べる／通す／確定して通す）
                                    └ 無ければ親の局面 → 「常時」 → 割り当てなしの規則
```

| 用語 | 中身 |
|---|---|
| 和音（chord） | キー 1 つと修飾（Shift・Ctrl・Alt）の組。`Ctrl+U`、`Shift+Left`、`Space` |
| 局面（phase） | 入力の進み具合。直接入力／入力なし／入力中／変換中／候補選択中／文節長変更中／予測の候補／文節内入力 |
| コマンド | 名前の付いた操作 1 つ。`convert`、`commit`、`segment_shrink` など（§3.2） |
| キー表（keymap） | （局面, 和音）→ コマンド の全体。プリセットに利用者の差分を重ねたもの |
| 食べる表（eat table） | キー表から作る、TIP 用の（局面, 和音）→ 食べる／通す。コマンドの中身は持たない |
| 打鍵層 | 文字キーと Space のうち、Ctrl も Alt も付かないもの。同時打鍵の判定に入る（§4） |

「状態」という語は、通信の `state`（`ready`・`starting`・`down`）と利用者に見える状態（通常・準備中・停止・対象外）で使っているので、
キー表の区分は**局面**と呼び、通信の項目名は `phase` にする。

---

## 3. 局面とコマンド

### 3.1 局面

局面は MS-IME の状態（[ms-ime.md](keybind/ms-ime.md) §2 の ①〜⑥、§1.5 の予測）に合わせる。

| 局面 | ID | 条件 | 親 | MS-IME の状態 |
|---|---|---|---|---|
| 常時 | `global` | どの局面でも（直接入力、準備中も） | — | — |
| 直接入力 | `direct` | 直接入力 | `global` | オフ |
| 入力なし | `empty` | かな入力で、入力中の文字が無い | `global` | ① |
| 入力中 | `composing` | 入力があり、まだ変換していない。自動で出る予測候補（フォーカスなし）もここ | `global` | ② |
| 変換中 | `converting` | 変換済みで、候補窓は閉じている | `global` | ③ |
| 候補選択中 | `selecting` | 変換済みで、候補窓が開いている | `converting` | ④ |
| 文節長変更中 | `resizing` | 文節を伸ばすか縮めた直後。変換し直すか、ほかの操作をすると `converting` に戻る | `converting` | ⑤ |
| 文節内入力 | `editing` | 複数文節の変換の一部を文節戻しや前字削除で入力し直している。候補窓は閉じている | `converting` | ⑥ |
| 予測の候補 | `predicting` | 予測候補にフォーカスがある | `composing` | 予測 |

- 表を引くときは、今の局面に無ければ親をたどり、最後に `global` を見る。子の局面には、親と違う行だけを書けばよい。
  親の行のうち、コマンドがその子の局面で使えない（`phases` の外の）行は引き継がない。子の局面でそのキーを食べたいときは `noop` の行を書く。
- `converting` と `selecting` の違いは、候補窓が開いているかだけ。1 回目の変換では候補窓を出さず（`converting`）、2 回目の Space（`next_candidate`）で開く（MS-IME と同じ）。
- **変換候補の窓を開くのは、候補を選ぶ操作だけ**（`next_candidate`・`prev_candidate`・`open_candidates`）。注目文節や文節の境界を変える操作
  （文節の移動、伸縮、先頭の文節の確定、字種の変換）は、候補窓を閉じる。
- 自動表示の予測候補は、入力中のキー操作と未確定文字を変えない。Tab・↓ などの `predict` で表示済みの候補に
  フォーカスを入れると `predicting` に移り、候補番号で選べる。自動表示が間に合わなかったときも `predict` は使える。
- `resizing` には、文節の境界が実際に動いたときに入る。端で動かなければ、文節は変えずに候補窓だけを閉じる（`selecting` は `converting` になり、ほかの局面はそのまま）。リテラルの文節（数字や記号の並び）では、伸縮は何もしない。
- 伸縮した文節は、変換せずに読みで見せる。縮めて切り離した字は、新しい文節にして読みで見せる。伸ばして隣の文節から字を取ったときは、隣の文節の残りを読みにする。
  `resizing` の間は、伸縮のコマンド、`alnum_mode`、何も起こさないコマンド（`noop`・`pass_through`）では局面が変わらない。ほかのコマンドを実行すると `resizing` を終える。
  Space（`convert_segment`）は、読みにした文節を変換して `converting` に戻る。ほかのコマンドで終えたときは、読みの文節は読みのまま残る（確定すると読みのまま確定する。
  その文節で `next_candidate` を使うと、候補窓を開いて次の候補へ進む）。
- 文節長変更中の Esc・Ctrl+Z は、一連の伸縮を取り消し、伸縮前の文節の境界と選んでいた候補を戻す。候補窓は閉じたまま。
- 文節戻しでは、注目文節を選んでいた候補の読みに戻す。複数文節なら、その文節に注目したまま `editing` に入り、
  ほかの文節の変換を保つ。候補窓が開いているときの Esc・Backspace は、候補窓を閉じる。
- 候補窓を閉じた変換中の Backspace・Ctrl+H は、表示全体の末尾を 1 字削る。複数文節なら末尾を注目文節として `editing` に入る。
  末尾の文節が消えたときは、その前の文節の表記を編集できる形にする。編集する文節だけが残ったときは `composing` になる。
- `composing` では、カーソルを途中へ動かすと入力を読みで表示する。←・→ で 1 打ずつ、Home・End で入力の先頭・末尾へ移る。
  途中にも入力でき、Backspace・Delete は前後の 1 打を削る。両端では止まる。Space はカーソルの位置にかかわらず入力全体を変換する。
  Ctrl+Backspace・Ctrl+Delete は、カーソルの位置を保ってアプリに通す。確定してから通すが、Ctrl+Delete は末尾ならそのまま通す。
- `editing` では、注目文節の中で移動、挿入、削除ができる。Space はその文節を変換する。Esc・Shift+Esc は全戻し。
  Ctrl+←・Ctrl+→・Ctrl+A・Ctrl+F は文節の先頭・末尾へ移動し、Home・End は何もしない。
  ←・→ で文節の端を越えると、隣の文節へ移って `converting` に戻る。入力全体の端を越えると確定してキーを通す。
  Shift+←・Shift+→ と Ctrl+S/D/K/L は入力全体の端で止まる。
  Backspace・Ctrl+H は入力全体の先頭で、Delete・Ctrl+G は末尾で、確定してキーを通す。
- 「英数の続き」は局面にしない。文字キーの打たれ方が変わるだけで、使えるコマンドは `composing` と同じ。
  Shift+CapsLock（`alnum_mode`）で入ったときは、変換中でも局面を変えない（CONVERSION「英数の続き」）。
- 準備中・停止・対象外では、`global` の中の TIP が実行するコマンドだけが効く（§7.5）。

### 3.2 コマンド

コマンドは引数を持たない名前にする（`select_candidate_3` のように 1 つずつ別の名前）。編集画面で 1 つの一覧から選べるため。

各コマンドは次の属性を持つ。属性はエンジンの中のコマンド表（§6.2）に 1 か所だけ書く。

| 属性 | 中身 |
|---|---|
| `id` | 名前。設定ファイルと通信で使う。一度公開したら変えない |
| `phases` | 割り当てられる局面。それ以外の局面の行は、読み込みで落とす |
| `key` | キーの行き先。`eat`（食べる）／`pass`（アプリに通す）／`commit_pass`（確定してから通す） |
| `where` | `engine`（エンジンが実行）／`tip`（TIP が自分で実行。オン/オフなど） |
| `label` | 編集画面に出す日本語の名前 |
| `passes_at_edge` | 入力全体の端で確定して通すことがある（`*_or_pass`・`delete_after`）。`editing` の `Space` には割り当てられない（§4.2） |
| `starts_input` | 入力が無いときに文書へ文字を入れる（空白の 4 つ）。打鍵と同じく入力開始の down として、載せた `left_context`・`after_commit_seq` で左文脈を決め直す |

コマンドの一覧。「作った」が × のものは、プリセットの行に書いてもキー表を作るときに無視する（§5.4）。
局面の列の「composing 以降」は入力がある局面の全部、「converting 以降」は `converting`・`selecting`・`resizing`・`editing`、「selecting 以降」は `selecting`・`predicting`。

| コマンド | 局面 | 作った | 中身 |
|---|---|---|---|
| `ime_toggle` / `ime_on` / `ime_off` | global（`ime_toggle` は predicting にも割り当て可） | ○ / ○ / ○ | 直接入力とかな入力の切り替え。入力があれば確定してから切り替える。TIP が実行 |
| `mode_hiragana` / `mode_katakana` / `mode_full_alnum` | global | ○ | ひらがな／全角カタカナ／全角英数の入力モードにする。直接入力ならオンにする。TIP が実行 |
| `open_settings` / `open_word_register` | global（`open_word_register` は empty にも割り当て可） | ○ / ○ | 設定ウィンドウを開く（後者は単語登録のタブ）。TIP が実行 |
| `open_menu` | empty | ○ | タスクバーの右クリックと同じ IME メニューを開く。TIP が実行 |
| `insert_space` | empty, composing | ○ | 全角の空白を入れる |
| `insert_alt_space` | empty | ○ | 半角の空白を入れる |
| `insert_full_space` / `insert_half_space` | empty 以降 | ○ | 幅を決めた空白。入力なしでは文書に入れ、入力中では入力中の文字に足す。変換中より先では、確定してから空白で次の入力を始める |
| `undo_commit` | empty | × | 直前の確定を取り消す |
| `reconvert` | empty, direct | × | 確定済みの文字を変換し直す。[再変換の実装案](#33-再変換の実装案)を参照 |
| `convert` | composing、predicting | ○ | 読みを変換する。予測選択中は予測候補を閉じてから変換する |
| `predict` | composing | ○ | 予測候補に入る |
| `commit` | composing 以降 | ○ | 全部確定する |
| `commit_with_half_space` | predicting | ○ | 選んだ予測候補を確定し、半角空白を入れる |
| `commit_at_cursor_and_pass` / `commit_inside_and_pass` | composing | ○ | カーソルを保ったまま確定してキーを通す。後者は末尾なら確定せず通す |
| `commit_first_segment` | composing 以降 | ○ | 先頭の文節だけ確定する |
| `commit_one_char` | composing | ○ | 先頭の 1 打を、かなのまま確定する（CONVERSION「部分確定」） |
| `delete_before` | composing、converting 以降 | ○ | 入力中と文節内入力はカーソルの前の 1 打、変換済みは表示の末尾の 1 字を消す |
| `delete_last_and_commit` | converting 以降、predicting | ○ | 表示の末尾の 1 字を消して残りを確定する。末尾の文節より前の文節は、ふつうの確定と同じく学習に書く |
| `alnum_mode` | composing 以降 | ○ | 入力と変換を残したまま、入力が終わるまで英数の続きにする（CONVERSION「英数の続き」）。`resizing` は終えない |
| `cycle_kana_mode` / `toggle_alnum_width` | empty | ○ | 未確定文字が無いときに、かなの字種または英数の幅の入力モードを変える |
| `cycle_kana_script` / `cycle_alnum_width` | composing 以降 | ○ | 無変換・Shift+無変換。未変換の入力の字種、または変換中の注目文節の字種を変える |
| `delete_after` | composing、editing | ○ | カーソルの後の 1 打を消す。文節内入力で入力全体の末尾なら確定して通す |
| `cursor_left` / `cursor_right` / `cursor_home` / `cursor_end` | composing、editing | ○ | 左右へ 1 打、または入力・注目文節の先頭・末尾に移動する |
| `cursor_left_or_pass` / `cursor_right_or_pass` / `delete_before_or_pass` | editing | ○ | 左右へ移動、または前字を削除する。入力全体の端でこれ以上動けなければ確定して通す |
| `cancel` | composing | ○ | 入力を全部消す |
| `cancel_conversion` | converting 以降、predicting | ○ | 変換をやめて、入力中に戻る |
| `restore_reading` | converting 以降、predicting | ○ | 変換をやめて、入力全体を読みで表示する |
| `segment_revert` | converting、selecting | ○ | 注目文節を読みに戻す |
| `cancel_resize` | resizing | ○ | 文節長変更前の境界と表記を戻す |
| `to_hiragana` / `to_katakana` / `to_half_katakana` / `to_full_alnum` / `to_half_alnum` | composing 以降 | ○ | 字種を変える（MS-IME の F6–F10） |
| `input_to_hiragana` / `input_to_katakana` / `input_to_full_alnum` / `input_to_half_alnum` | composing | ○ | 入力全体の字種を変え、入力中のままカーソルを末尾へ移す |
| `close_candidates` | selecting | ○ | 候補窓を閉じて `converting` に戻る。変換はそのまま |
| `accept_candidate` | selecting | ○ | 現在の候補を選んで窓を閉じ、次の文節があればそこへ移る |
| `open_candidates` | converting | ○ | 選んでいた候補で候補窓を開く |
| `next_candidate` / `prev_candidate` | converting 以降、predicting | ○ | 次／前の候補。`converting` では候補窓を開く |
| `prev_prediction` | predicting | ○ | 予測候補を一つ戻る。先頭に達したら止まる |
| `next_page` / `prev_page` | selecting 以降 | ○ | 次／前の 9 件 |
| `prev_page_wrap` | selecting | ○ | 前の 9 件へ。先頭ページからは最後のページへ |
| `select_candidate_1` … `select_candidate_9` | selecting 以降 | ○ | 番号の候補を選ぶ |
| `pick_candidate_1` … `pick_candidate_9` | selecting | ○ | 番号の候補を選んで窓を閉じる |
| `candidate_first` / `candidate_last` | selecting 以降 | ○ | 先頭／最後の候補を選ぶ |
| `segment_left` / `segment_right` | converting 以降 | ○ | 前／次の文節へ |
| `segment_first` / `segment_last` | converting 以降 | ○ | 先頭／末尾の文節へ |
| `segment_shrink` / `segment_expand` | converting 以降 | ○ | 文節を 1 打縮める／伸ばす。境界が動くと `resizing` になる（§3.1） |
| `segment_shrink_and_convert` / `segment_expand_and_convert` | converting 以降 | ○ | 文節を 1 打縮める／伸ばす。境界が動いた文節をその場で変換する |
| `convert_segment` | resizing | ○ | 伸縮で読みにした文節を変換し、`converting` に戻る（MS-IME の「文節変換」。候補窓は開かない） |
| `convert_edited_segment` | editing | ○ | 注目文節の入力を変換し、候補窓を閉じた変換中に戻る |
| `forget_candidate` | selecting 以降 | ○ | 今の候補の学習を忘れる |
| `noop` | global 以外の全部 | — | 食べて何もしない。MS-IME が食べて何もしないキー、ゆらぎに作らない機能のキー、親の局面の割り当てを止める行に書く |
| `pass_through` | global 以外の全部 | — | 何もせずアプリに通す |
| `commit_and_pass` | composing 以降 | ○ | 確定してから、そのキーをアプリに通す。割り当ての無いキーの既定（§4.3）。キーは TIP が食べて、確定のあとに送り直す（§7.6） |

Mozc のコマンド名との対応は、プリセットを作るときに `tools/` の変換スクリプトの中に持つ（この設計の外）。

### 3.3 再変換の実装案

#### 入口と対象範囲

- アプリや Windows からは TIP の `ITfFunctionProvider` が返す `ITfFnReconversion` を入口にする。キー設定の `reconvert` からも、TIP が選択範囲を取得して同じ処理へ進む。アプリから範囲を渡された場合はその範囲を使う（[再変換の調査](keybind/reconversion.md) §4 の Excel）。
- MS-IME プリセットの候補は JIS の変換キーと Ctrl+ImeOn（同 §3）。US 配列専用の既定キーは設けない案とする。直前の確定を元に戻す `undo_commit` は別機能として扱う。
- 選択がある場合はその範囲を対象にする。選択が空の場合は、現行 MS-IME でカーソルが文節内と末尾にあるときの対象範囲を、選択ありの場合と見比べる。その結果を基に、カーソルの前後をどこまで読み、どの単位で切るかを決める。

#### 読みと候補

- 貼り付けた文字も扱えるよう、表記から辞書を逆引きして読みを得る案。表記上で Viterbi 探索を行う方法、辞書にない記号・英数字・かなの扱い、処理長の上限を検討する。索引を足す場合は辞書キャッシュの形式、起動時の読み込み時間、メモリ使用量を確認する。直前の確定履歴を補助に使うかも検討する。
- エンジンの入力は打鍵の列（`tokens`）で始まる。読みで始める入力をどう表現するかを決める。選択範囲の直前を `left_context` として使い、対象の元の表記を保持する。候補窓を開いた `selecting` で始める案とし、候補を変えずに確定した場合は元の表記を返す。Esc を押したときの動きは現行 MS-IME で確かめる。

#### 元の文字の置き換え

- TIP の `ReadSession::Document` はカーソルの左を読む処理。再変換では、書き換える範囲で `StartComposition` する処理が要る。同期の読み書きセッションを断られた場合、読み取り専用、埋め込み物を含む範囲、逆引き失敗の場合は原文を保つ。
- 最初に対応するアプリの範囲は同 §4 を基に決める。Word の編集ロック、Excel が渡す範囲、Chrome・Edge の一時的な文書、VS Code での二重挿入、コンソールや IMM32・CUAS の文字取得を確認する。TSF で文字を取得できないアプリでは `IMR_RECONVERTSTRING` が必要になることがある。
- エンジン側では逆引き、読みからの入力、元の表記を返す経路を試験する。TIP 側ではアプリで実際に対象の範囲だけが置き換わることと、取り消しや失敗で原文が保たれることを確かめる。

---

## 4. キー

### 4.1 和音の書き方

設定ファイルと編集画面での書き方。

```
[Ctrl+][Alt+][Shift+]<キー名>          例: Ctrl+U   Shift+Left   Ctrl+Shift+Space   F7   1
```

- 修飾の順は Ctrl、Alt、Shift に決める。読み込みでは順不同・大文字小文字の違いを受け付け、書き出しではこの順にそろえる。
- キー名: `A`–`Z`、`0`–`9`、記号は US 配列の刻印（`` ` `` `-` `=` `[` `]` `\` `;` `'` `,` `.` `/`）、
  `Space` `Enter` `Backspace` `Tab` `ImeOn` `ImeOff` `Convert` `NonConvert` `Esc` `Delete` `Insert` `Home` `End` `PageUp` `PageDown` `Left` `Right` `Up` `Down`
  `F1`–`F24` `CapsLock` `Numpad0`–`Numpad9` `NumpadAdd` `NumpadSubtract` `NumpadMultiply` `NumpadDivide` `NumpadDecimal`。
- キー名は US 配列の刻印で、**利用者が押した形**を表す。内部では和音を整数 1 つで持つ:
  `code = US 配列の仮想キーコード | 修飾 << 8`（修飾は Shift=1、Ctrl=2、Alt=4。TIP が `tip.json` の `toggle_mods`（`["alt"]` などの名前の並び）から作る値と同じ）。
  Alt+`` ` `` は `VK_OEM_3 | 4 << 8` で、TSF に届く `VK_KANJI` ではない。届いた形から和音への戻し方は §7.4。
- Win キー付きの和音は割り当てられない（Windows のもの）。
- 左右の修飾キーの区別（`LCtrl+` など）、修飾キーだけの単独打鍵、2 打の連続（Ctrl+X のあと Ctrl+S、など）は、MS-IME に無いので入れない。
  読み込みで知らない書き方に出会ったら、その行だけを無視する（§5.4）。
- Ctrl+`` ` ``（半角／全角）と、修飾付きの CapsLock（英数・ひらがな・カタカナ）は、配列ドライバが IME 用のキーに変えて渡し、
  押したときに up と down を対で出す（[windows.md](keybind/windows.md) §3.5）。これらは「押したら 1 打」として和音に戻す（§7.4）。
  MS-IME は Ctrl+`` ` `` を使わず、アプリに通す（[ms-ime.md](keybind/ms-ime.md) §1.5）。
  Ctrl+Shift+CapsLock はカナのロックを切り替える（直接入力の文字が半角カナになる）ので、プリセットには使わない。

### 4.2 割り当てられる範囲

文字キーと Space は入力そのものに使うので、割り当てられる局面を限る。**この規則は固定**で、設定では変えられない。

| 和音の種類 | direct | empty | composing | converting 以降、predicting |
|---|---|---|---|---|
| 文字キー（修飾なし、Shift 付き） | × | × 文字を打つ | × 文字を打つ | ○ 無ければ「確定して次の入力」 |
| `Space`（修飾なし） | × | ○ 単独打鍵 | ○ 単独打鍵 | ○ 単独打鍵 |
| 修飾付きの Space | global だけ | ○ | ○ | ○ |
| Ctrl 付きの文字キー（Ctrl+Alt も） | global だけ | ○ | ○ | ○ |
| Alt 付き（Ctrl なし）の和音 | global だけ | global だけ | global だけ | global だけ |
| それ以外のキー（Enter、矢印、F1 など。修飾は自由） | global だけ | ○ | ○ | ○ |

- **文字キー**（修飾なし、Shift 付き）は、`empty` と `composing` では必ず文字になる。Shift は小指のシフト面（英字、上段の記号）。
  `converting` 以降と `predicting` では割り当てを先に見る（候補窓の 1–9 は候補の番号、など）。
  割り当てが無ければ、確定して次の入力を始める。
- **`Space`** は親指キーで、同時打鍵の判定を通る。キー表の `Space` は、判定の結果が**単独打鍵**（`ThumbTap`）になったときに引く。
  文字キーと同時に押した Space は親指シフトで、キー表を見ない。単独と判定した時点では元の打鍵をアプリに返せないため、
  `Space` にはアプリに通すコマンドと TIP が実行するコマンドを割り当てられない。`editing` では、端で確定して通すことがあるコマンド（`passes_at_edge`）も割り当てられない。「何もしない」は割り当てられる。
  先行の親指シフト実装（ibus-anthy、fcitx5-anthy、やまぶきR）と同じ扱いなので、他の IME のプリセットの `Space` の行はそのまま使える。
- **修飾付きの Space**（Shift+Space、Ctrl+Space など）は親指キーにしない。押した時点で、ふつうの機能キーとして表を引く。
- **`global` の行は、局面の行が無いときに効く**（親をたどった最後）。Shift+CapsLock のように、`global` で切り替え、`composing` では英数の続き、と局面で意味を変えられる。
  利用者が `global` に足した和音だけは別で、土台のプリセットの局面の行より先になる（§5.4）。
  ただし Alt 付き（Ctrl なし）の和音は、次のとおり `global` にしか書けない。
- **Alt 付き（Ctrl なし）の和音は `global` だけ。** TSF は Alt+文字 などを `OnTestKeyDown`／`OnKeyDown` に渡さず、
  PreservedKey に登録したものだけが届く（[windows.md](keybind/windows.md) §1.3）。PreservedKey は局面に関係なく先に食べるので、局面ごとに意味を変えられない
  （`OnPreservedKey` で FALSE を返したときにキーがアプリに通るかは定まっていない。[windows.md](keybind/windows.md) §9）。
  Ctrl+Alt の和音はふつうのキーと同じく届くので、局面ごとに割り当てられる。
- **テンキー**の数字と記号は、MS-IME と同じく、Shift 面と同じリテラル（半角の数字・記号を 1 字入れる）として
  打鍵層に入れる。`converting` 以降と `predicting` では、数字の段と同じく割り当てを先に見る。
- **`direct` の行**は読み込めるが、今は効かない（直接入力では、エンジンは表を引かない）。

### 4.3 割り当てのないキー

表を親までたどっても行が無い機能キーへの応答は、入力があればプリセットの `unbound_input` で決まる。

| 局面 | 修飾なし・Shift・Ctrl 付き | Alt 付き（Ctrl なし）・Win 付き |
|---|---|---|
| direct、empty | アプリに通す | アプリに通す |
| composing 以降 | 「MS-IME」は **確定してアプリに通す**（`commit_and_pass`）。「macOS」は **食べて入力を残す**（`noop`） | アプリに通す（Alt を押したときに確定している） |

- MS-IME は、入力がある間、働きの無いキーの多くを確定してからアプリに通す（Insert、PageUp、Ctrl+C、Ctrl+V、Ctrl+Shift+矢印など）。
  食べて何もしないキー（Shift+Enter など）と、確定せずに通すキー（F1、Ctrl+Tab、Ctrl+Home など）もある。これらは MS-IME のプリセットに `noop`・`pass_through` の行として書く。
- **入力がある間に Alt を押すと、全部確定する。** MS-IME は Alt だけを押して離しても、割り当ての無い Alt+Z でも確定する。
  Alt キーそのものはキーの呼び出しに届く（[windows.md](keybind/windows.md) §1.3）ので、TIP がそれを見て確定を頼み、Alt は通す（§7.2）。
- Alt 付き（Ctrl なし）の和音は TIP に届かず、アプリのメニューなどに行く。`global` に割り当てたものだけを PreservedKey で受け取る（§4.2）。

---

## 5. 設定ファイル

### 5.1 置き場所

| ファイル | 中身 | 書く人 |
|---|---|---|
| `<インストール先>/yuragi/data/keymaps/<名前>.json` | プリセット。読むだけ | 配布物 |
| `~/.yuragi-ime/keymap.json` | 利用者の設定（どのプリセットを使うか、そこからの差分） | 設定ウィンドウ。手で書いてもよい |

`keymap.json` が無ければ、MS-IME のプリセット（`ms-ime.json`）をそのまま使う。
`ms-ime.json` はインストール時に配布物として置き、ゆらぎは読み取り専用として扱う。

MS-IME のプリセットは、新 MS-IME を実機で見た動き（[keybind/ms-ime.md](keybind/ms-ime.md) §1.5。食べるか、確定して通すか、そのまま通すか）のとおりにする。
働きの名前と、実機で見ていないキーは、旧 MS-IME のテンプレート「Microsoft IME」のキー設定の表（ms-ime.md §2）による。
オン/オフの Alt+`` ` `` と、入力モードの Ctrl/Shift/Alt+CapsLock は新 MS-IME の US 配列と同じ。
`VK_IME_ON` が届いたらひらがなに、`VK_IME_OFF` が届いたら半角英数に切り替える。
変換・無変換は `Convert`／`NonConvert` の仮想キーコードが届いたときに使える。
`kbd101` が INT4 を 0xFF、INT5 を `VK_OEM_PA1` として届けたときは、未確定文字を保ってそのままアプリに通す。
JIS 専用キーの実機での動きは [keybind/ms-ime.md](keybind/ms-ime.md) を参照。
TIP はどちらのファイルも読まない（§8）。

### 5.2 プリセットの形式

```json
{
  "version": 1,
  "name": "ms-ime",
  "label": "MS-IME",
  "bindings": [
    ["global",     "Alt+`",      "ime_toggle"],
    ["empty",      "Space",      "insert_space"],
    ["composing",  "Space",      "convert"],
    ["composing",  "Enter",      "commit"],
    ["selecting",  "Space",      "next_candidate"],
    ["selecting",  "Shift+Left", "segment_shrink"]
  ]
}
```

- 1 行が `[局面, 和音, コマンド]`。1 行に 1 つなので、差分が読みやすい。
- 同じコマンドに複数のキーを割り当てるときは、行を複数書く。
- 同じ（局面, 和音）の有効な行が 2 つあったら、後の行を使う。`keymap.json` の読み込みでは記録に残す。編集画面では 1 つの欄にまとめる。
- `unbound_input` は `commit_and_pass`（省略時）か `noop`。ユーザー定義にも土台のプリセットから引き継ぐ。
- プリセットは全部の行を書く（他のプリセットを土台にしない）。プリセット同士が独立なので、1 つを直しても他に響かない。

#### macOS プリセット

設定ウィンドウの「キー」タブから「macOS」を選んで保存する。割り当ては [macos.json](../yuragi/data/keymaps/macos.json)。ライブ変換と「Windows風のキー操作」をオフにした Mac の実機を基準にした。

- 変換の候補窓では Enter で候補を選んで次の文節へ移る。数字の 1〜9 は候補を選んで窓を閉じる。確定は窓を閉じた状態の Enter。Esc は入力全体を読みに戻す。
- 文節の伸縮は、その場で境界が変わった文節を変換し直す。ほかの文節の区切り、候補の並び、未変換時の表示、親指シフトの文字配列と数字の幅はゆらぎの規則に従う。
- Ctrl+Space でゆらぎのかな入力と直接入力を切り替える。Windows 用の Alt+`` ` `` と、JIS のかな・英数キー（`ImeOn` / `ImeOff`）でも切り替えられる。入力ソース自体の切り替えは Windows の Win+Space で行う。
- IME に届く Ctrl 付きのキーは Mac の Control の割り当てに合わせた。たとえば入力中の Ctrl+A は半角英数への変換、Ctrl+S はカーソルを左へ動かす。Windows アプリの Ctrl ショートカットは入力を終えてから使う。
- Option 単独の組み合わせは TSF で局面別に割り当てられない（§4.2）。Alt を押すとゆらぎの Windows 側の規則で確定する。
- 確定取り消し、再変換、候補の辞書情報やタブ、macOS のライブ変換は未対応。入力中の Ctrl+Q と、予測候補や変換候補の窓での Home / End は何もしない。

### 5.3 利用者の設定の形式（ユーザー定義）

旧 MS-IME のキー設定と同じく、選べるのは「プリセットのどれか」か「ユーザー定義」（[ms-ime.md](keybind/ms-ime.md) §3.2）。
ユーザー定義は、土台のプリセットと、それに重ねる差分で持つ。

```json
{
  "version": 1,
  "use": "custom",
  "custom": {
    "base": "ms-ime",
    "overrides": [
      ["composing", "Ctrl+U",  "to_hiragana"],
      ["selecting", "Down",    "commit_first_segment"],
      ["selecting", "PageUp",  null]
    ]
  }
}
```

- `use` は、使うプリセットの名前か `custom`（ユーザー定義）。`custom` は、ユーザー定義が無ければ項目ごと無い。
- `overrides` は、`base` のプリセットに重ねる行。コマンドが `null` の行は、「プリセットのその行を消す」。消したあとは、親の局面の行があればそれが効く。
  親の行も止めたいときは `noop`（食べる）か `pass_through`（通す）を書く。
- プリセットを使っているときに表を変えると、そのプリセットを土台にした新しいユーザー定義になり、前のユーザー定義と置き換わる（旧 MS-IME と同じ）。
  プリセットを選び直しても、ユーザー定義は消えず、「ユーザー定義」を選べば戻る。
- 差分で持つ理由:
  - プリセットを後から直したとき（誤りの訂正、新しいコマンドの行の追加）、変えていない行は利用者にも届く。
  - 利用者が何を変えたかがファイルを見て分かる。
- `tip.json` の `toggle_vk`・`toggle_mods` も読む。`keymap.json` が無いときに限り、その和音で、MS-IME のプリセットの `global` の
  `` Alt+` `` → `ime_toggle` の行を置き換える（`` Alt+` `` は切り替えに使わなくなる）。TIP も、表が届くまでは埋め込みの表の `global` に同じ置き換えをするので、
  表を知らない DLL が残っているアプリとも食い違わない。エンジンは、その和音がプリセットの局面の行にもあれば、局面の行を落とす（§5.4）。
  この状態で「キー」タブの割り当てを初めて変えるときは、従来の切り替えキーもユーザー定義の差分に取り込む。

### 5.4 読み込みの規則

エンジンと設定ウィンドウは同じ規則（`yuragi/ime/keymap.py`）で読む。打鍵に使う表を作るのはエンジン。
利用者の `keymap.json` では、DESIGN「互換の規則」と同じ考え方で、**悪い行だけを落とし、残りは使う**。

| 起きたこと | 扱い |
|---|---|
| `keymap.json` が無い | MS-IME のプリセット |
| `keymap.json` 全体を読み込めない、または `use`・`base` で選んだ別のプリセットが欠落・不正で使えない | `ms-ime.json` のプリセット。注意 `keymap` を出す |
| 知らないコマンド、知らない局面、読めない和音 | その行を無視。記録に残す（新しい版で作った設定を古い版が読んでも壊れない） |
| その局面で使えないコマンド（`phases` の外） | その行を無視。記録に残す |
| §4.2 で割り当てられない和音（`composing` の `A` など） | その行を無視。記録に残す |
| 利用者が `global` に足した和音（`overrides` の `global` の機能の割り当て、`tip.json` の切り替えキー）が、土台のプリセットの局面の行にもある | 土台の局面の行を落とす（常時のキーにしたものは、どの局面でも効く。新 MS-IME の「キーの割り当て」と同じ）。同じ `overrides` の中に局面の行もあれば、それは残す |
| まだ実装していないコマンド | 行を無視する（記録には残さない。プリセットに先に書いておける） |
| `version` が知らない値 | 読める行だけ読む |

- 無視した行の一覧は、エンジンのログと、設定ウィンドウの「キー」タブに出す。
- 注意 `keymap` は、注意 `lm` と同じ道（エンジン → ブローカー → 設定ウィンドウの「状態」タブ）で出す。通知は出さない。
- **同梱の `ms-ime.json` はエンジンの起動に必要な配布物。** 起動時にファイルの形式と全行を検査する。ファイルが無い、読めない、JSON や行の形式が不正、または知らないコマンド、読めない和音、§4.2 に反する割り当てがある場合は、`program-files-unreadable` で停止する。配布物は再インストールで復旧する。
- DLL に埋め込む食べる表も、ビルド時に同じ規則で `ms-ime.json` を読んで作る（§7.2）。

---

## 6. エンジン

### 6.1 モジュール

| ファイル | 中身 |
|---|---|
| `yuragi/chord/keys.py` | キーの分類（`classify()`）、和音の型 `Chord(vk, mods)`、和音の書き方の読み書き、打鍵層の判定 |
| `yuragi/ime/keymap.py` | プリセットと `keymap.json` を読み、検査し、**引くだけの表**に直す。食べる表を作る |
| `yuragi/ime/commands.py` | コマンド表。コマンドの属性と、`ImeSession` のどのメソッドを呼ぶか |
| `yuragi/ime/session.py` | `on_key()`（表を引いてコマンドを実行する）と、操作の中身（`_commit`、`_cycle`、`_resize` など） |
| `yuragi/data/keymaps/*.json` | プリセット |

現在のキー表（`Engine.keymap`）は全部のセッションで共有する。読み直すと新しい表を作って参照を入れ替える。
LM 待ちの要求は受付時の表を保持する（§8.3）。

### 6.2 コマンド表

```python
@dataclass(frozen=True)
class Command:
    id: str
    label: str
    phases: frozenset[str]
    key: str = "eat"            # eat / pass / commit_pass
    where: str = "engine"       # engine / tip
    run: Callable[[ImeSession], str | None] | None = None   # 確定した文字を返す。tip のコマンドは None
    keeps_resizing: bool = False  # 実行しても文節長変更を終えない（§6.3）
    passes_at_edge: bool = False  # 入力全体の端で確定して通すことがある。editing の Space には割り当てられない
    starts_input: bool = False    # 入力なしで文書に文字を入れる。打鍵と同じく左文脈を読み直す

COMMANDS = {c.id: c for c in (
    Command("convert", "変換", COMPOSING | PREDICTING, run=lambda s: s._convert()),
    Command("commit", "全確定", INPUT, run=lambda s: s._commit()),
    Command("segment_shrink", "文節を縮める", CONVERTED, run=lambda s: s._resize(-1), keeps_resizing=True),
    Command("select_candidate_3", "候補 3 を選ぶ", SELECTING, run=lambda s: s._select_row(2)),
    ...
)}
```

- コマンドの追加は、この表に 1 行足すことで終わる。TIP・ブローカー・通信は変えない（食べる表が自動で変わる）。
- `run` を持たないエンジンのコマンドは未実装なので、キー表を作るときに行を落とす。
- 操作は、操作ごとのメソッド（`_to_script("hiragana")` など）で、仮想キーコードでは分岐しない。キーの意味を決めるのは `keys.py` と `keymap.py` だけ。
  例外は、入力なしで通したキーが左文脈を消すかどうかで、`_pass_empty_key` が Enter・Backspace で分ける（CONVERSION §9）。

### 6.3 局面

局面は `ImeSession` のフィールドから求めるプロパティ。`resizing` は文節を伸縮したときに立ち、
`editing` は複数文節の変換の一部を入力し直すときに立つ。文節ごとの `raw` は、変換前の読みや編集中の文字を表示している間に立つ（§3.1）。

```python
@property
def phase(self) -> str:
    if self.direct:      return "direct"
    if not self.tokens:  return "empty"
    if self.predicting:  return "predicting"
    if not self.converted: return "composing"
    if self.resizing:    return "resizing"
    if self.editing:     return "editing"
    return "selecting" if self.candidates else "converting"
```

`resizing` を倒す所は、コマンドを実行する所の 1 か所にする。`keeps_resizing` のコマンド（`segment_shrink`・`segment_expand`・`alnum_mode`・`noop`・`pass_through`）以外は、実行の前に倒す。
伸縮のコマンドは、境界が動けば立て直す。入力が消える所（確定、取消、`reset`）でも倒す。

### 6.4 打鍵の処理

`on_key()` の流れ。**表を引くのは、コマンドを実行する時点**（下の 2 と 3）。
同時打鍵の判定待ちや LM 待ちが残っている間に次のキーが来ても、待ちが片づいたあとの局面で意味が決まる。

```
on_key(down, vk, t, mods):
  0. 直接入力なら何もしない。修飾キー自体は、押されているかの記録だけ。
     ただし Alt キーの down は、入力があれば判定待ちを締めて全確定する（§4.3。eat は false）。
     up は、同時打鍵の判定に入った down の分だけ判定に渡す。コマンドとして使った down の up は捨てる。
  1. 和音を作る。chord = Chord(vk, mods)
  2. 打鍵層でない和音（機能キー、Ctrl/Alt 付き、修飾付きの Space）:
       a. 判定待ちの打鍵を締める（_finish_pending）
       b. LM 待ちがあれば、残りを待ちのあとに回す（_then）
       c. その時点の局面で表を引く → コマンドを実行。行が無ければ §4.3
  3. 打鍵層の和音（文字キー、修飾なしの Space）:
       a. 文字キーで、局面が converting 以降か predicting（LM 待ちがあれば、2b と同じく待ちのあとの局面で見る）で、
          表に行があれば → 判定待ちを締めて、コマンドを実行（同時打鍵の判定には入れない）
       b. それ以外 → Shift 面・英数の続き・同時打鍵の判定へ
  4. 同時打鍵の判定が「Space の単独打鍵」（ThumbTap）を出したとき:
       その時点の局面で、和音 `Space` として表を引く → コマンドを実行。行が無ければ何もしない
```

- 4 の Space の行は、MS-IME のプリセットでは `empty`→`insert_space`、`composing`→`convert`、`converting`→`next_candidate`（候補窓を開く）などの行になる（Space の割り当ては ms-ime.md §1.4、§2.1）。
- 2c で LM 待ちがあるときは、`ConversionRequest` と `_continuation` で「表を引いて実行する」を待ちのあとに回す。
- コマンドが例外を出したときは、DESIGN「要求 1 件ごとの防壁」で受ける。

### 6.5 返事の項目

| 項目 | 中身 |
|---|---|
| `phase` | 返事の時点の局面（§6.3）。同時打鍵の判定待ち・LM 待ちがあっても、求め方は同じ |
| `eat` | この要求のキーを食べたか。`true`／`false`。down の要求の返事にだけ付く（TIP は up を食べない。§7.4） |
| `global` | この要求のキーが TIP の担当するコマンドに当たったときの、コマンドの名前。TIP が返事の確定を書いたあとで実行する（§7.5）。もう 1 つ、`alnum_mode` で入った英数の続きが、食べたキー（Enter、Esc など）で入力ごと終わったときの `ime_off`（このときの `eat` は `true`。MS-IME は英数モードのまま、つまりオフで終わる） |

`eat` の決め方:

| 起きたこと | `eat` |
|---|---|
| コマンドを実行した | コマンドの `key` が `eat` なら `true`、`commit_pass` なら `false`（TIP はこれを見て、確定のあとにキーを送り直す。§7.6）。`pass` のコマンドは食べる表の `pass` に入り、TIP が送らないので返事は無い |
| 同時打鍵の判定に入った（文字キー、Space） | `true` |
| 割り当てなし | §4.3 のとおり（「通す」なら `false`） |
| 直接入力 | `false` |
| TIP が実行するコマンドに当たった（§7.5） | `false`。返事に `global` を付ける |

TIP は `OnKeyDown` の答えをこの `eat` では変えない（§7.3）。

---

## 7. TIP

### 7.1 食べる表

TIP が持つのは、エンジンが作った次の形の表だけ。親の局面の引き継ぎも検査も済んでいて、TIP は探すだけ。

```json
{"rev": "3f9a1c",
 "phases": {
   "empty":      {"eat": [520, 544], "pass": []},
   "composing":  {"eat": [13, 8, 27, 9, 117, 597, 552], "pass": [], "rest": "eat"},
   "converting": {"eat": [...], "pass": [...], "rest": "eat"},
   "selecting":  {"eat": [...], "pass": [...], "rest": "eat"},
   "resizing":   {"eat": [...], "pass": [...], "rest": "eat"},
   "predicting": {"eat": [...], "pass": [...], "rest": "eat"},
   "editing":    {"eat": [...], "pass": [...], "rest": "eat"}},
 "global": [{"code": 1216, "command": "ime_toggle"}]}
```

- 数字は和音の整数（§4.1）。`eat` は「受け取って、エンジンに送る」、`pass` は「送らずに通す」（`pass_through` の行）。
  `commit_pass` のコマンドは `eat` に入る（エンジンに送って食べ、確定のあとに送り直す。§7.6）。
  局面に割り当てた TIP のコマンドも `eat` に入る。エンジンが表を引き、返事の `global` で実行を指示する（§7.5）。
- `rest` は、どちらにも無い和音の扱い（§4.3）。`"eat"` は「受け取ってエンジンに送る」（エンジンが確定して `eat:false` を返し、TIP が送り直す）。Alt 付き・Win 付きは通す。
- `global` は `direct` と準備中にも効く行で、TIP が自分で実行する（§7.5）。局面の表に同じ和音があれば、局面の表が先。
- 打鍵層の和音（文字キー、修飾なしの Space）は表に入れない。かな入力の間は常に受け取る。
  `converting` 以降で文字キーに割り当てがあっても、TIP から見れば「受け取る」で同じ。
- `rev` は表の中身から作った短い識別子。同じ表を配り直したとき、TIP が何もしないで済む。
- 大きさは数 KB。接続のときと、変わったときにだけ届く。

### 7.2 受け取るかの規則

```cpp
enum class Phase { Empty, Composing, Converting, Selecting, Resizing, Predicting, Editing, Direct };
enum class Take { Pass, Send };              // アプリに通す／エンジンに送る

struct KeyTable { ... };                     // ParseKeyTable(json) で作る。Sends(phase, code)・Overrides(phase, code)・GlobalAt(phase, code)
struct Local {
    Phase phase = Phase::Empty;              // 最後に反映した返事の phase
    bool unsettled = false;                  // 返事を待つ要求がある、または判定のタイマーが掛かっている
};

Take WantKey(Chord chord, const Local& local, const KeyTable& table);
```

TIP の規則（`yuragi_tip.cpp` の `Decide()` と `tip_logic.h` の `WantKey()`。`OnTestKeyDown` でも使うので、通信しない）:

1. 直接入力、Win 付き、修飾キーそのもの、Alt 付き（Ctrl なし）の和音 → 通す。
2. ただし Alt キーそのものは、局面が `composing` 以降（または `unsettled`）なら、同じ down をエンジンにも送る。
   エンジンは確定し（§6.4 の 0）、TIP は確定を書くが、Alt は送り直さない（もうアプリに渡っている）。
3. 常時の和音（`global` に行がある）→ §7.5 の規則。TIP が実行するなら通さずに実行し、エンジンに聞くなら送る。
4. 打鍵層の和音 → 送る。
5. 今の局面の表で受け取る和音（`eat`、または `rest` が `eat` で `pass` に無い）→ 送る。
6. `unsettled` → **`composing` 以降のどれかの局面で受け取る和音なら、送る。** 局面がまだ決まっていないので、広く受け取る。
7. それ以外 → 通す。

返事が来たあと:

- 返事に `global` があれば、そのキーは送り直さない。返事の確定を文書に書き終えたあとで、TIP がそのコマンドを実行する（§7.5）。実行できないときは送り直す。
- `WantKey()` が送ると決めたキーは、`OnKeyDown` でも食べる（§7.3）。返事が `eat:false` なら、そのキーはアプリに渡すべきだったので、
  確定などを文書に書き終えたあとで送り直す（§7.6）。`commit_pass` のコマンド、割り当ての無いキー（§4.3）、規則 6 で広く受け取ったキーがこれに当たる。
- 返事が `KEY_BUDGET_MS` に間に合わなかったら、`WantKey()` の判定どおりに食べる。
  `commit_pass` のコマンドは、確定が後から届き、書き終えたところで送り直す（§7.6）。
- TIP の手元のフラグ `composing_`（表示の制御に使う）は、`phase` から求める。

表がまだ届いていないとき（ブローカーにつながる前、表を配らないブローカー）は、DLL に埋め込んだ MS-IME のプリセットの食べる表を使う。
埋め込む表はビルドのときにプリセットから作り、食い違いは試験で見つける（§9）。

### 7.3 キーの処理の流れ

流れは DESIGN「打鍵の処理」の 1–4 のとおりで、「食べるか」は食べる表で決める。

```
OnTestKeyDown:  和音に戻す（§7.4）→ 常時のキーか（§7.5）→ WantKey(…, table)
OnKeyDown:      同上（同じ答え）
OnKeyUp:        食べない。エンジンに送った down の up は、エンジンにも送る（§7.4）
返事:           phase を覚える。eat:false なら送り直す（§7.6）
```

**`OnTestKeyDown` と `OnKeyDown` は、同じキーに必ず同じ答えを返す。** アプリには `OnKeyDown` だけを呼ぶものと、先に `OnTestKeyDown` を呼んで
TRUE のときだけ `OnKeyDown` を呼ぶものがあり、後者では `OnTestKeyDown` に TRUE と答えたキーは、`OnKeyDown` で FALSE を返してもアプリに届かない
（[windows.md](keybind/windows.md) §1.1）。答えは食べる表と手元の局面だけで決め、エンジンの返事では変えない。食べる表とエンジンが食い違わないことは試験で保つ（§9.2）。

### 7.4 キーの出来事の扱い

MS-IME と同じく、届いた出来事を 1 つずつ、届いた時点の形で扱う（[ms-ime.md](keybind/ms-ime.md) §1.5）。前提の事実は [windows.md](keybind/windows.md)。

| 出来事 | 扱い | 前提の事実 |
|---|---|---|
| down | 仮想キーコードと、その出来事の時点の修飾から和音に戻す。`VK_KANJI` は Alt+`` ` ``、`VK_DBE_*` は修飾付きの CapsLock・Ctrl+`` ` ``（表で戻す） | `kbd101` の読み替えは出来事ごとの修飾で決まる（windows.md §3.1、§3.2、§3.5） |
| up | 食べない。エンジンに送った down の up は、エンジンにも送る（同時打鍵の判定に要る）。返事は待たない | MS-IME も、食べた down の up をアプリに渡す（ms-ime.md §1.5） |
| up が来ない | 次の down を、ふつうの down として扱う（up が来なかったキーを、押されたままとして扱い続けない） | `` ` `` → Ctrl・CapsLock → Shift・CapsLock → Ctrl の順 C と、Alt でメニューに入ったあと（`` ` `` → Alt の順 D、CapsLock → Alt の順 C・D など）の up は来ない（windows.md §3.2） |

- 押されているかを、`VK_KANJI`・`VK_OEM_3` の `GetKeyState` で判定しない。順 B・順 C で押されたままに見える（windows.md §3.3）。
- キーの up を作って送らない。`VK_KANJI`（順 B）や `VK_OEM_3`・`VK_CAPITAL`（順 C）が押されたままに見えるのは配列ドライバの動きで、どの IME でも起きる（windows.md §3.3）。

### 7.5 常時のキー（オン/オフ・モードなど）

`global` の行は、TIP が自分で実行する。直接入力の間も、準備中も効く必要があるため。

- 実行できるコマンドは `where: tip` のものだけ: `ime_toggle`・`ime_on`・`ime_off`・`mode_hiragana`・`mode_katakana`・`mode_full_alnum`（手元の入力モードを変え、`set_direct`・`set_mode` を送る。
  オフにするときと、ひらがな以外の入力モードにするときは、入力があればエンジンが先に確定する。ひらがなにするときは入力を残す）、`open_settings`・`open_word_register`（ブローカーに `open_admin` を送る）。
- `open_menu` は `empty` の行からエンジンが返す。MS-IME プリセットでは Ctrl+F10 と Ctrl+変換。TIP は入力欄のスレッドで、キーのコールバックを抜けてからメニューを開く。
- **Alt 付き（Ctrl なし）の行だけを TSF の PreservedKey に登録する。** Alt 付きの和音は PreservedKey にしか届かない（[windows.md](keybind/windows.md) §1.3）。
  ほかの行は `OnKeyDown` で照合する（局面の表に同じ和音があれば、そちらが先。§7.1）。
- **局面が決まっていない間は、局面で意味が変わる和音を TIP が自分で決めない。** 返事を待つ要求があるか、判定のタイマーが掛かっている間（§7.2 の `unsettled`）、
  `global` の和音がどれかの局面の表にもあれば、そのキーを食べてエンジンに送る。エンジンは判定待ちを締め、その時点の局面で表を引く（§6.4）。
  引いたコマンドが TIP の担当なら、返事に `global` を付ける（§6.5）。TIP は、返事の確定を文書に書いたあとでそのコマンドを実行する。
  文字キーの直後の Shift+CapsLock は、返事の局面がまだ「入力なし」でも、打った文字を確定してオフにしない。
  MS-IME プリセットの予測候補では、判定待ちの有無にかかわらず Shift+CapsLock をエンジンに送り、予測候補の局面に割り当てた `ime_toggle` で確定してオフにする。
  どの局面の表にも無い和音（Alt+`` ` `` など）、局面が決まっているとき、直接入力、エンジンに送れないとき（準備中）は、TIP が手元の局面で決める。
- 登録の形は、TSF に届く形に合わせる。**Alt+`` ` `` は `{VK_KANJI, TF_MOD_IGNORE_ALL_MODIFIER}` で登録する**
  （`{VK_OEM_3, TF_MOD_ALT}` や `{VK_KANJI, TF_MOD_ALT}` には届かない。[windows.md](keybind/windows.md) §3.6）。同じ理由で、§4.1 の IME 用のキーに変わる和音（Alt+CapsLock など）は、変わったあとの仮想キーコードで登録する。
- PreservedKey には 1 つずつ GUID が要る。決まった GUID の列から、Alt 付きの行に順に当てる。40 個まで登録する（1 スレッドで 40 個を登録できることは確かめた。[windows.md](keybind/windows.md) §1.4）。
  それより多い行は登録しない（記録には出さない）。
- 表が変わったら、登録を全部外して登録し直す。アクティブなまま登録し直せて、すぐ効く。
  登録は TIP のスレッドで行う（読み取りスレッドから届いた表は、非同期の返事と同じ道で UI スレッドに渡す）。
- 準備中に効くのは、オン/オフとモードの切り替え（`tip_logic::Toggles`）と `open_settings`。`open_word_register` はエンジンが使えるときだけ効く。停止・対象外では、`open_settings` だけを受け取る。
- Windows 側で IME が閉じているときは、直接入力の局面として `global` を引く。`ime_toggle` と `ime_on` は
  IME を開いてひらがな入力にする。入力モードを指定するコマンドは、IME を開いて指定のモードにする。
  対象は有効な入力欄で、エンジンが通常または準備中のとき。
- パスワード欄では、どれも食べない。

### 7.6 食べたキーをアプリに渡す（送り直し）

`OnTestKeyDown` で食べると答えたキーを、あとから通すことはできない（§7.3）。返事が `eat:false` のキー（`commit_and_pass`、割り当ての無いキー、§7.2 の規則 6 で受け取ったキー）は、

1. キーは食べる。
2. エンジンの返事の確定を、いつもどおり文書に書く。
3. 書き終えたあと、同じキーを `SendInput` で送り直す。送り直すキーには `dwExtraInfo` に印を付け、TIP はその印のあるキーを見ずに通す。

送り直すまでのあいだに利用者が次のキーを押すと、順序が入れ替わるので、そのあいだのキーは送り直しが済むまで手元に溜める。`dwExtraInfo` が TIP のキーの呼び出しの中で読めない場合（[windows.md](keybind/windows.md) §9）は、
送り直すキーを手元で覚えておき、次に来た同じキーを 1 回だけ通す。

溜めたキーは食べてあるので、アプリには元のキーが届いていない。そこで、溜めたキー（以下「手元の列」）について次を守る。

- **食べたキーは、エンジンに送るか、印を付けて Windows に返すか、理由を記録して捨てるかの、どれかに必ず行き着く。** 黙って消える道を作らない。
- **手元の列が空でない間は、新しいキーを先に通さない。** 列の末尾に溜める。
- 手元の列を捨ててよいのは、§7.7 の持ち越しに当たらないフォーカスの移動、TIP が外されるとき、送り直す時点で前面が別のプロセスのとき、だけ。捨てた件数と理由を記録に出す（キーの中身は出さない）。
- 切断、エンジンの終了（`reset`・`down`・エラー）、アプリによる変換の打ち切りでは、手元の列を捨てずに処理を続ける。
  エンジンが使えない間のキーは食べる表の引き直しで「通す」になり、Windows に返る（DESIGN「打鍵の処理」4 と同じ扱い）。

### 7.7 送り直したキーでフォーカスが移るとき（持ち越し）

`Enter → Tab → A` を LM 待ちの間に続けて押すと、Tab と A は手元の列に入る。Enter の確定を書いたあと Tab を送り直すと、アプリは次の欄に移る。
MS-IME では A は次の欄に入る（キーを 1 打ずつその場で処理し終えるので、押した順に、処理の時点でフォーカスのある欄に届く）。同じ結果にするために、手元の列を移動先へ**持ち越す**。

**持ち越す移動。** 送り直したキーが TIP を通ってから、TIP が次に手元の列を処理するまでの間に来たフォーカスの移動を、そのキーが起こした移動とみなす。

- TIP は、送り直したキーを通すときに、列の処理を自分のウィンドウに投函する。投函したメッセージは、あとから来るキーやマウスの入力より先に取り出されるので
  （[windows.md](keybind/windows.md) §1.7）、この間に利用者のほかの操作は挟まらない。時間では判定しない。
- 加えて、移動の前後で前面のウィンドウの根の所有者（`GA_ROOTOWNER`）が同じこと。Enter が開いたダイアログには持ち越し、別のアプリや無関係のウィンドウには持ち越さない。
- 持ち越しを始めたあとは、手元の列が空になるまで、根の所有者が同じ移動のたびに持ち越しを続ける（1 回の移動でフォーカスの通知は複数届く）。
- これに当たらない移動（マウスで別の欄を押した、Alt+Tab した）では、手元の列を捨てる（§7.6）。
- `OnTestKeyDown` で食べると答えたあと、`OnKeyDown` の中で初めて移動に気づいたキーは、Windows が移動先に配ったキーなので、上の条件を見ずに持ち越しの列に入れる。

**持ち越しの間に押されたキー。** 移動先の入力欄の種類が分かる前でも、食べて手元の列の末尾に溜める（§7.6 の 2 つ目の規則。通すと、溜めてあるキーを追い越す）。
通すのは、Win 付きのキー、修飾キーそのもの、キーの呼び出しに届かない Alt 付きの和音だけ。up は食べない。
これは DESIGN「パスワード欄」の「答えが出るまでは素通し」の例外で、条件は DESIGN に書いた。

**届け方。** 列の先頭から 1 打ずつ、その時点の移動先の状態で決める。

| 移動先 | 届け方 |
|---|---|
| 通常欄 | 新しい欄の局面（入力なし）で食べる表を引き直し、エンジンに送る／常時のキーを実行する／Windows に返す |
| パスワード欄、キーボードが無効、文書が無い | エンジンに送らず、印を付けて Windows に返す |
| Windows 側で IME が閉じている | §7.5 のオン操作は順番に実行する。通常の打鍵は印を付けて Windows に返す |
| 種類がまだ分からない | 最初の移動から `KEY_BUDGET_MS` まで待つ。分からないままなら、エンジンに送らず Windows に返す |

- Windows に返すのは 1 打ずつ。返したキーが TIP を通るまで次を出さず、その間に押されたキーは列の末尾に溜める。
- 持ち越したキーは、エンジンには `reset` のあとの新しい入力として届く。移動の前の返事は反映しない（DESIGN「見えている文字の確定」）。
- エンジンに送って返事を待っているキーは持ち越さない。エンジンの側の入力は `reset` で捨てられ、画面の文字は表示のまま残る。

**直らない場合。** フォーカスを、送り直したキーの処理が終わったあとで移すアプリでは、TIP は移動の前に A を古い欄のキーとして処理してしまう。
こういうアプリがあるか、そのとき MS-IME がどう見えるかは確かめていない（[windows.md](keybind/windows.md) §9）。

---

## 8. 通信

プロトコル 1 の、キー表にかかわる項目（DESIGN「互換の規則」）。

### 8.1 項目

| 向き | 項目 | 中身 |
|---|---|---|
| TIP → ブローカー | `{"op":"set_mode","mode":"katakana"}` | 入力モード（`hiragana`・`katakana`・`full_alnum`）。`mode_hiragana`・`mode_katakana`・`mode_full_alnum`（§7.5） |
| TIP → ブローカー | `{"op":"open_admin"}` | 設定ウィンドウを開く。`open_settings`・`open_word_register` のどちらも、最初のタブ（単語登録）で開く |
| エンジン → ブローカー | `ready` に `"keymap":{…}` | 食べる表（§7.1） |
| エンジン → ブローカー | `{"event":"keymap","keymap":{…}}` | 読み直したあとの表 |
| ブローカー → エンジン | `{"op":"reload_keymap","sid":3,"seq":1}` | 設定ファイルを読み直す |
| ブローカー → TIP | hello の返事に `"keymap":{…}` | ブローカーが持っている最新の表。無ければ項目ごと無い |
| ブローカー → TIP | `{"event":"keymap","keymap":{…}}` | 表が変わった |
| エンジン → TIP（返事） | `"phase"`、`"eat"` | §6.5 |
| エンジン → TIP（返事） | `"global":"ime_toggle"` | このキーは TIP の担当するコマンドだった（または、英数の続きが終わってオフにする `ime_off`）。TIP が実行する（§6.5、§7.5）。`resolved_keys` の項目にも付く |
| エンジン → TIP（返事） | `"eat_pending":true`、`"resolved_keys":[{"seq":12,"eat":false}]` | LM 待ちで打鍵が保留されたとき、最初の返事に `eat_pending` を付ける。処理後、確定文字列を届ける返事に元の `seq` と最終結果を付ける |
| 設定ウィンドウ → ブローカー | `{"op":"reload_keymap","seq":1}` | 保存したあとに送る |
| ブローカー → 設定ウィンドウ | `{"seq":1,"keymap_reload":"applied"}` | 読み直しの結果（§8.3） |

ブローカーは表の中身を解釈しない。エンジンから受け取った JSON の値を覚えておき、そのまま配る。
エンジンが落ちても、ブローカーは最後の表を持ち続ける（新しいエンジンが `ready` で言い直すまで）。

### 8.2 表をパイプで配る理由

TIP に `keymap.json` を読ませない。理由は 3 つ。

1. **読み方が 1 つで済む。** 引き継ぎ・差分・検査を C++ にも書くと、エンジンと食い違う。
2. **サンドボックス内のアプリにも届く。** パイプは「すべてのアプリパッケージ」に開いているが、利用者のフォルダは読めない。
3. **全部のアプリに同時に届く。** ファイルだと、アプリごとに読む時機がずれる。

### 8.3 設定を変えたときの流れ

```
設定ウィンドウ: keymap.json を書く（一時ファイルに書いて置き換える。config.json と同じ）
      │ {"op":"reload_keymap"}
      ▼
ブローカー ──→ エンジン: 読み直して、新しいキー表に入れ替える（要求と要求の間で。再起動しない）
      ▲            │ {"event":"keymap","keymap":{…}}
      └────────────┘
ブローカー: 表を覚え、つながっている全部の TIP に {"event":"keymap",…} を送る
TIP: rev が違えば表を入れ替え、常時のキーを登録し直す
```

- 入力中だったセッションは、未確定文字と局面を保ったまま新しい表で続ける。エンジンがすでに受け付けて LM 待ちの列に置いた要求と、
  LM 完了後に再開する処理は受付時の表を使う。`Space` の単独打鍵は `ThumbTap` を処理する要求の表を引く。
- 新しい表は読み終えてから入れ替える。不正な行だけを飛ばして読み込めた場合は、使える行を反映する（§5.4）。
  ファイル全体または使うプリセットが読めなければ、前の表を使い続ける。
- 設定ウィンドウが付けた `seq` で応答を返す。`keymap_reload` は反映済みが `applied`、読み直しに失敗したら `failed`（`reason` 付き）、
  エンジンの準備ができていなければ `deferred`。その場合は次の起動で設定を読む。

### 8.4 版が混ざるとき

更新のあと、開いたままのアプリには古い DLL が残る。

| 組み合わせ | 動き |
|---|---|
| 表を知らない DLL（v0.2.7 まで。開いたままのアプリに残る）＋ 表を送るエンジン | DLL は `keymap`・`phase`・`eat` を無視し、自分の決まった規則と、返事を見て食べたかを決める規則で動く。その DLL が通すキー（Ctrl 付きなど）の割り当ては、そのアプリを開き直すまで届かない。切り替えキーは `tip.json` の値（§5.3） |
| 表を使う DLL ＋ 表を送らないエンジン | 更新の途中の短い間だけ。表が届かないので DLL に埋め込んだ食べる表を使い、`eat` が無いので `WantKey` の判定どおり。`global` も来ないので、判定待ちの間に送った常時のキーは送り直しになり、アプリに通る |

設定ウィンドウの「キー」タブに、「旧版の DLL が残っているアプリは、開き直すと変更が反映されます。」と 1 行書く
（更新の直後だけ起きる。ふだんは全部のアプリにすぐ届く）。

---

## 9. 設定ウィンドウと試験

### 9.1 「キー」タブ

設定ウィンドウに「キー」タブを置く。表は旧 MS-IME のキー設定と同じく、キーを行、局面を列にする（[ms-ime.md](keybind/ms-ime.md) §3.2）。

| 部品 | 中身 |
|---|---|
| キー設定 | プリセットの一覧と「ユーザー定義」から選ぶ。表を変えると「ユーザー定義」になる（§5.3） |
| 表 | 行がキー、列が局面（常時・入力なし・入力中・変換中・候補選択中・文節長変更中・予測の候補・文節内入力）。欄に機能の名前を出し、割り当てなしは「–」 |
| 変更 | 欄をダブルクリックするか［変更］を押すと、その局面で使える機能の一覧が開き、そこから選ぶ |
| キー追加 | 表に無いキーを、キーと修飾の一覧から選んで足す。§4.2 で割り当てられない和音は一覧に出さない。Alt 付き（Ctrl なし）の和音は、常時の列だけを変えられる |
| 読み込みの記録 | `keymap.json` に無視した行があれば、理由と一緒に出す（§5.4） |

- 選べるのは用意したキーと機能だけなので、§4.2 に反する行や、同じ（局面, キー）の重なりは作れない。
- プリセットから受け継いだ割り当てに戻す操作と、その局面の割り当てを外す操作を選べる。外したあとは親の局面をたどる。
- 表に残る未実装のコマンドには、欄に本来の機能の名前と「未実装」を出す。新規に割り当てられるのは実装済みの機能。
- 保存は「保存」を押したとき。押すと §8.3 の流れで、すぐ全部のアプリに効く。

### 9.2 試験

黙って壊れる所だけを試験する。

| 試験 | 見つけるもの |
|---|---|
| 入力全体の試験（`tests/transcripts/`、`test_partial_commit` など）は、MS-IME のプリセットで動かす。期待値は MS-IME の動き | プリセットの行の誤りによる、意図しない挙動の変化 |
| **TIP とエンジンの突き合わせ**: 局面 × 和音の全部の組について、エンジンに実際にキーを送ったときの `eat` と、C++ の `WantKey()` が食べる表から出す答えが同じ。`tests/keymap_cases.py` が組の全部をエンジンに送って期待値を作り、`tip_logic_test --key-cases` の標準入力に渡す。C++ は DLL に埋め込む表で `WantKey()` を引いて比べる（CTest の `tip_keymap_roundtrip`） | TIP とエンジンの食い違い（キーがアプリに抜ける、食べたまま何も起きない） |
| DLL に埋め込む表は、ビルドのたびにプリセットから作る（CMake）。上の突き合わせがその表で比べる | 埋め込みの作り忘れ |
| 悪い行の混ざった `keymap.json` で、良い行は効き、悪い行だけが落ちる | 1 行の誤りで設定の全部が消えること |
| 自作の `keymap.json` や選んだ別のプリセットが読めないとき（§5.4）、同梱の `ms-ime.json` で動き、注意 `keymap` が出る | 設定の破損でエンジンが起動しなくなること |
| 同梱の `ms-ime.json` が無い、読めない、形式が不正、または悪い行があるとき、`ready` を返す前に `fatal program-files-unreadable` を出して終了する | 配布物の破損が診断されずにエンジンが終了すること、壊れた割り当てで起動すること |
| `tip.json` の切り替えキーがプリセットの局面の行と重なる（Ctrl+Space）とき、入力のある局面でも切り替えのコマンドが引ける | 切り替えキーが入力中に食べられて効かないこと |
| 文節長変更（§3.1）: 多文節を変換して、縮める → 伸ばす → Space → Space。返事の `phase`、候補、文節の境界、見せる文字（読みか変換か）を追う。`resizing` からの文節の移動、先頭の文節の確定、字種の変換、取消、確定、文字キーのあとの局面と文字。端で動かない伸縮。`selecting` での文節の移動 | 候補窓が開いたままになること、`resizing` が残ること、読みにした文節が黙って変換されること、候補窓を閉じた変換中で操作が黙って効かないこと |
| 判定待ちの間の常時のキー（§7.5）: 文字キーの down の直後（返事は「入力なし」とタイマー）の Shift+CapsLock で文字が残る。入力なしで同じキーをエンジンに送ると返事に `global`。`tip_logic_test.cpp` で、判定待ちの間はそのキーを送ると決まる | 打った文字が確定されてオフになること、常時のキーが実行されずアプリに抜けること |
| 判定待ち・LM 待ちの間に機能キーを押す（Space の直後の Enter、変換待ちの間の ←） | 表を引く時機の誤り（待ちが片づく前の局面で引いてしまう） |
| コマンドとして使った文字キーの up が、同時打鍵の判定に入らない | 候補を番号で選んだ直後の誤入力 |
| TIP のキーの出来事の扱い（§7.4）: `tip_logic_test.cpp` で、届いた仮想キーコードから和音への戻し（`VK_KANJI`、対で届く `VK_DBE_*`）と食べるかを確かめる。TSF の呼び出しの列（[windows.md](keybind/windows.md) §3.2 の順 A〜D、up が来ない列）は、自動の試験に無い（実機で確かめる） | 和音への戻し誤り、up を食べること |
| 手元の列と持ち越し（§7.6、§7.7）: 出来事の列（キー、送り直したキーの通過、フォーカスの移動と根の所有者、入力欄の種類の判明、時刻）を `tip_logic_test.cpp` で与え、キーの届く順と行き先（エンジン／Windows に返す／捨てる）を比べる。LM 待ちの `Enter → Tab → A`、種類が分かる前の `B`、移動先がパスワード欄、種類が分からないまま期限、別のウィンドウへの移動、送り直しと関係のない移動 | 食べたキーが消えること、あとのキーが追い越すこと、パスワード欄や未判定の欄のキーがエンジンに行くこと、無関係の欄に届くこと |
| 実機: 2 欄以上のフォームで、エンジンの返事を遅らせて上と同じ列を打つ（Win32 のダイアログ、Word、Chromium、WPF か WinUI）。フォーカスの通知・種類の照会・キーの到着の順序を記録する | TSF の呼び出しの順序についての前提の崩れ（§7.7 の「持ち越す移動」の見分け方は、アプリの作りに依る） |
| 実機: `tools/keyprobe/msime_tsf_table.py` と同じ表を、ゆらぎで採り、MS-IME の表と比べる（食べるか、確定して通すか、そのまま通すか） | プリセットと MS-IME の食い違い |
| 実機: [keybind/windows.md](keybind/windows.md) §1・§3 の表の項目を、確認用の TIP と `checks.py`（`tools/keyprobe/README.md`）で、TIP のキーの扱いを変えるときと Windows の大きな更新のあとに確かめる | TSF・配列ドライバの前提の崩れ（自動の試験では見つからない） |
