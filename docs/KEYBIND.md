# キーバインドを変えられるようにする詳細設計

どんなキーの割り当てを設定されても、その割り当てで操作できるようにするための、ゆらぎ側の仕組みの設計。
各プリセットの中身（どのキーに何を割り当てるか）は扱わない。まだ実装していない。

| 資料 | 中身 |
|---|---|
| [keybind/windows.md](keybind/windows.md) | この設計が前提にする Windows・TSF のキー入力の動き（キーの届き方、Alt、PreservedKey、`kbd101` の読み替え、繰り返し） |
| [keybind/ime-impl.md](keybind/ime-impl.md) | 既存の IME（Mozc、CorvusSKK、SampleIME など）が、キーをどう受け取り、繰り返しと up をどう扱っているか |
| [keybind/ime-survey.md](keybind/ime-survey.md) | 主要な日本語 IME のキー操作とカスタマイズの比較。IME ごとの全表は `keybind/` の各ファイル |
| [DESIGN.md](DESIGN.md) | 全体の構成・通信・TIP の規則 |

---

## 1. 要約

| # | 決めること | 結論 |
|---|---|---|
| 1 | データモデル | **（局面, キー）→ コマンド** の表。局面は MS-IME の状態に合わせ、親の局面から引き継ぐ（§3、§4.1、§6） |
| 2 | キーの意味を決める所 | **エンジンだけ**。今 3 か所（`WantKey`、`EatAfterReply`、`on_key`）にある判定を、エンジンの 1 つの表引きにまとめる（§7） |
| 3 | TIP の役目 | エンジンが作った**「食べるか」の表**を引くだけ。表はブローカー経由でパイプから受け取る。食べるかは表で決め、返事が `eat:false` ならキーを送り直す（§8、§9） |
| 4 | 既定のキー割り当て | **MS-IME のプリセット**。新 MS-IME を実機で見た動きのとおりにし、見ていないキーは旧 MS-IME の表で補う。US 配列に無いキーの行は持たず、新 MS-IME の US 配列での代わり（Alt+`` ` ``、Ctrl/Alt/Shift+CapsLock）を使う（§6.1） |
| 5 | 設定ファイル | `~/.yuragi-ime/keymap.json`。旧 MS-IME と同じく、プリセットか「ユーザー定義」を選ぶ。ユーザー定義は**プリセット＋差分**で持つ（§6） |
| 6 | Space（親指キー） | 表の `Space` は「Space の単独打鍵」。修飾付きの Space は親指キーにしない（§5） |
| 7 | 文字キー | 入力なし・入力中では常に文字。変換中より先の局面でだけ割り当てられる（§5） |
| 8 | 割り当てのないキー | 入力がある間は、確定してアプリに通す。Alt を押したときも確定する（MS-IME と同じ。§5.3） |
| 9 | オン/オフ・モードのキー | TIP が自分で実行する「常時」の割り当て。Alt 付きのものは TSF の PreservedKey に登録する（§8.5） |
| 10 | キーの出来事の扱い | `OnTestKeyDown` と `OnKeyDown` は同じ答えを返す。MS-IME と同じく、繰り返しも 1 打ずつ実行し、up は食べない（§8.3、§8.4） |
| 11 | 反映 | 設定ウィンドウで保存 → エンジンが読み直す（再起動しない）→ 全アプリの TIP に配る（§9.3） |

---

## 2. 今の作りで困る所

1. **キーの意味が 3 か所に直書きされている。** TIP の `WantKey()`（送る前に食べるか）、`EatAfterReply()`（返事のあと食べたか）、
   エンジンの `ImeSession.on_key()`（何をするか）。3 つは同じ規則を別々に書いたもので、1 つ変えると残りも手で合わせる必要がある。
2. **TIP が Ctrl・Alt・Win 付きのキーを、Ctrl+↓ 以外すべてアプリに通す。** エンジンには届かないので、Ctrl+U などを割り当てられない。
3. **`on_key()` が if の連なりで、判定の順序が意味を持つ。** 「変換中の数字は候補の番号、それ以外では文字」のような規則が、順序で表されている。
4. **TIP の手元の状態が 4 つのフラグ**（`composing`、`converted`、`candidates`、`awaiting`）で、予測の候補窓かどうかは分からない。
5. **割り当てのないキーの扱いが MS-IME と違う。** 入力中の矢印キーはアプリに通る（MS-IME は食べる）。PageUp や Ctrl+C は確定せずにアプリに通る
   （MS-IME は確定してから通す。[ms-ime.md](keybind/ms-ime.md) §1.5）。
6. **切り替えキーだけが `tip.json` にあり、TIP が読む。** サンドボックス内のアプリは利用者のフォルダを読めないので、そこでは既定のキーに戻る。
7. **`OnTestKeyDown` で食べると答えたキーを、返事を見て `OnKeyDown` で通すことがある**（返事が `pass_through`、準備中の返事など）。
   Word など `OnTestKeyDown` を先に呼ぶアプリでは、このキーは失われる（[windows.md](keybind/windows.md) §1.1）。

---

## 3. 用語とモデル

```
打鍵 ──→ 和音（キー＋修飾） ──→ [ 局面 ] で表を引く ──→ コマンド ──→ 実行
                                    │                      │
                                    │                      └ キーの行き先（食べる／通す／確定して通す）
                                    └ 無ければ親の局面 → 「常時」 → 割り当てなしの規則
```

| 用語 | 中身 |
|---|---|
| 和音（chord） | キー 1 つと修飾（Shift・Ctrl・Alt）の組。`Ctrl+U`、`Shift+Left`、`Space` |
| 局面（phase） | 入力の進み具合。直接入力／入力なし／入力中／変換中／候補選択中／文節長変更中／予測の候補 |
| コマンド | 名前の付いた操作 1 つ。`convert`、`commit`、`segment_shrink` など（§4.2） |
| キー表（keymap） | （局面, 和音）→ コマンド の全体。プリセットに利用者の差分を重ねたもの |
| 食べる表（eat table） | キー表から作る、TIP 用の（局面, 和音）→ 食べる／通す。コマンドの中身は持たない |
| 打鍵層 | 文字キーと Space のうち、Ctrl も Alt も付かないもの。同時打鍵の判定に入る（§5） |

「状態」という語は、通信の `state`（`ready`・`starting`・`down`）と利用者に見える状態（通常・準備中・停止・対象外）で使っているので、
キー表の区分は**局面**と呼び、通信の項目名は `phase` にする。

---

## 4. 局面とコマンド

### 4.1 局面

局面は MS-IME の状態（[ms-ime.md](keybind/ms-ime.md) §2 の ①〜⑤、§1.5 の予測）に合わせる。

| 局面 | ID | 条件 | 親 | MS-IME の状態 |
|---|---|---|---|---|
| 常時 | `global` | どの局面でも（直接入力、準備中も） | — | — |
| 直接入力 | `direct` | 直接入力 | `global` | オフ |
| 入力なし | `empty` | かな入力で、入力中の文字が無い | `global` | ① |
| 入力中 | `composing` | 入力があり、まだ変換していない。自動で出る予測候補（フォーカスなし）もここ | `global` | ② |
| 変換中 | `converting` | 変換済みで、候補窓は閉じている | `global` | ③ |
| 候補選択中 | `selecting` | 変換済みで、候補窓が開いている | `converting` | ④ |
| 文節長変更中 | `resizing` | 文節を伸ばすか縮めた直後。変換し直すか、ほかの操作をすると `converting` に戻る | `converting` | ⑤ |
| 予測の候補 | `predicting` | 予測候補にフォーカスがある | `composing` | 予測 |

- 表を引くときは、今の局面に無ければ親をたどり、最後に `global` を見る。子の局面には、親と違う行だけを書けばよい。
- `converting`（候補窓を閉じたままの変換中）は**今のゆらぎには無い局面**。MS-IME と同じく、1 回目の変換では候補窓を出さず、2 回目で出す。
  それを作るまでは、変換すると必ず `selecting` になる（今と同じ）。
- `resizing` も今のゆらぎには無い。今は文節を伸縮しても `selecting` のまま。
- MS-IME の ⑥（変換済み文節内入力）は、F2 の文字編集と再変換を作るときに、局面 `editing` として足す。
- 「英数の続き」は局面にしない。文字キーの打たれ方が変わるだけで、使えるコマンドは `composing` と同じ。
- 準備中・停止・対象外では、`global` の中の TIP が実行するコマンドだけが効く（§8.5）。

### 4.2 コマンド

コマンドは引数を持たない名前にする（`select_candidate_3` のように 1 つずつ別の名前）。編集画面で 1 つの一覧から選べるため。

各コマンドは次の属性を持つ。属性はエンジンの中のコマンド表（§7.2）に 1 か所だけ書く。

| 属性 | 中身 |
|---|---|
| `id` | 名前。設定ファイルと通信で使う。一度公開したら変えない |
| `phases` | 割り当てられる局面。それ以外の局面の行は、読み込みで落とす |
| `key` | キーの行き先。`eat`（食べる）／`pass`（アプリに通す）／`commit_pass`（確定してから通す） |
| `where` | `engine`（エンジンが実行）／`tip`（TIP が自分で実行。オン/オフなど） |
| `label` | 編集画面に出す日本語の名前 |

コマンドの一覧。「今」が ○ のものは、今ある操作をそのまま名前にしたもの。× は新しく作る操作で、
名前だけ先に決めておく（プリセットの行に書ける。まだ無いコマンドの行は読み込みで無視する。§6.4）。
局面の列の「composing 以降」は入力がある局面の全部、「converting 以降」は `converting`・`selecting`・`resizing`、「selecting 以降」は `selecting`・`predicting`。

| コマンド | 局面 | 今 | 中身 |
|---|---|---|---|
| `ime_toggle` / `ime_on` / `ime_off` | global | ○ / × / × | 直接入力とかな入力の切り替え。入力があれば確定してから切り替える。TIP が実行 |
| `mode_hiragana` / `mode_katakana` | global | × / × | ひらがな／カタカナの入力モードにする（直接入力ならオンにする）。TIP が実行 |
| `open_settings` / `open_word_register` | global | ○ / × | 設定ウィンドウを開く（後者は単語登録のタブ）。TIP が実行 |
| `insert_space` | empty, composing | ○ | 空白を入れる（幅は入力モードに従う。ひらがなでは全角） |
| `insert_alt_space` | empty | × | `insert_space` と別の幅の空白 |
| `insert_full_space` / `insert_half_space` | empty 以降 | × | 幅を決めた空白 |
| `undo_commit` | empty | × | 直前の確定を取り消す |
| `reconvert` | empty, direct | × | 選んだ文字を変換し直す |
| `convert` | composing | ○ | 変換する |
| `predict` | composing | ○ | 予測候補に入る |
| `commit` | composing 以降 | ○ | 全部確定する |
| `commit_first_segment` | composing 以降 | ○ | 先頭の文節だけ確定する |
| `commit_one_char` | composing | × | 先頭の 1 字を確定する |
| `commit_to_focus` | converting 以降 | × | 注目文節までを確定する |
| `delete_before` | composing | ○ | 最後の 1 打を消す |
| `alnum_mode` | composing 以降 | × | 入力中の文字を残したまま、英数の続きに入る |
| `delete_after` / `cursor_left` / `cursor_right` / `cursor_home` / `cursor_end` | composing | × | 入力中のカーソル移動と削除（カーソルの仕組みが要る） |
| `cancel` | composing | ○ | 入力を全部消す |
| `cancel_conversion` | converting 以降 | ○ | 変換をやめて、入力中に戻る |
| `to_hiragana` / `to_katakana` / `to_half_katakana` / `to_full_alnum` / `to_half_alnum` | composing 以降 | ○ | 字種を変える（今の F6–F10） |
| `next_candidate` / `prev_candidate` | converting 以降 | ○ | 次／前の候補。`converting` では候補窓を開く |
| `next_page` / `prev_page` | selecting 以降 | ○ | 次／前の 9 件 |
| `select_candidate_1` … `select_candidate_9` | selecting 以降 | ○ | 番号の候補を選ぶ |
| `segment_left` / `segment_right` | converting 以降 | ○ | 前／次の文節へ |
| `segment_first` / `segment_last` | converting 以降 | × | 先頭／末尾の文節へ |
| `segment_shrink` / `segment_expand` | converting 以降 | ○ | 文節を 1 打縮める／伸ばす |
| `forget_candidate` | selecting 以降 | ○ | 今の候補の学習を忘れる |
| `noop` | global 以外の全部 | — | 食べて何もしない。親の局面の割り当てを止めるのに使う |
| `pass_through` | global 以外の全部 | — | 何もせずアプリに通す |
| `commit_and_pass` | composing 以降 | × | 確定してから、そのキーをアプリに通す。割り当ての無いキーの既定（§5.3）。キーは TIP が食べて、確定のあとに送り直す（§8.6） |

Mozc のコマンド名との対応は、プリセットを作るときに `tools/` の変換スクリプトの中に持つ（この設計の外）。

---

## 5. キー

### 5.1 和音の書き方

設定ファイルと編集画面での書き方。

```
[Ctrl+][Alt+][Shift+]<キー名>          例: Ctrl+U   Shift+Left   Ctrl+Shift+Space   F7   1
```

- 修飾の順は Ctrl、Alt、Shift に決める。読み込みでは順不同・大文字小文字の違いを受け付け、書き出しではこの順にそろえる。
- キー名: `A`–`Z`、`0`–`9`、記号は US 配列の刻印（`` ` `` `-` `=` `[` `]` `\` `;` `'` `,` `.` `/`）、
  `Space` `Enter` `Backspace` `Tab` `Esc` `Delete` `Insert` `Home` `End` `PageUp` `PageDown` `Left` `Right` `Up` `Down`
  `F1`–`F24` `CapsLock` `Numpad0`–`Numpad9` `NumpadAdd` `NumpadSubtract` `NumpadMultiply` `NumpadDivide` `NumpadDecimal`。
- キー名は US 配列の刻印で、**利用者が押した形**を表す。内部では和音を整数 1 つで持つ:
  `code = US 配列の仮想キーコード | 修飾 << 8`（修飾は Shift=1、Ctrl=2、Alt=4。`tip.json` の `toggle_mods` と同じ値）。
  Alt+`` ` `` は `VK_OEM_3 | 4 << 8` で、TSF に届く `VK_KANJI` ではない。届いた形から和音への戻し方は §8.4。
- Win キー付きの和音は割り当てられない（Windows のもの）。
- 左右の修飾キーの区別（`LCtrl+` など）、修飾キーだけの単独打鍵、2 打の連続（Ctrl+X のあと Ctrl+S、など）は、MS-IME に無いので入れない。
  読み込みで知らない書き方に出会ったら、その行だけを無視する（§6.4）。
- Ctrl+`` ` ``（半角／全角）と、修飾付きの CapsLock（英数・ひらがな・カタカナ・カナ）は、配列ドライバが IME 用のキーに変えて渡し、
  押したときに up と down を対で出す（[windows.md](keybind/windows.md) §3.5）。これらは「押したら 1 打」として和音に戻す（§8.4）。
  MS-IME は Ctrl+`` ` `` を使わず、アプリに通す（[ms-ime.md](keybind/ms-ime.md) §1.5）。
  Ctrl+Shift+CapsLock はカナのロックを切り替える（直接入力の文字が半角カナになる）ので、プリセットには使わない。

### 5.2 割り当てられる範囲

文字キーと Space は入力そのものに使うので、割り当てられる局面を限る。**この規則は固定**で、設定では変えられない。

| 和音の種類 | direct | empty | composing | converting 以降 |
|---|---|---|---|---|
| 文字キー（修飾なし、Shift 付き） | × | × 文字を打つ | × 文字を打つ | ○ 無ければ「確定して次の入力」 |
| `Space`（修飾なし） | × | ○ 単独打鍵 | ○ 単独打鍵 | ○ 単独打鍵 |
| 修飾付きの Space | global だけ | ○ | ○ | ○ |
| Ctrl 付きの文字キー（Ctrl+Alt も） | global だけ | ○ | ○ | ○ |
| Alt 付き（Ctrl なし）の和音 | global だけ | global だけ | global だけ | global だけ |
| それ以外のキー（Enter、矢印、F1 など。修飾は自由） | global だけ | ○ | ○ | ○ |

- **文字キー**（修飾なし、Shift 付き）は、`empty` と `composing` では必ず文字になる。Shift は小指のシフト面（英字、上段の記号）。
  `converting` 以降では割り当てを先に見る（今の「変換中の 1–9 は候補の番号」を一般にしたもの）。
  割り当てが無ければ今と同じく、確定して次の入力を始める。
- **`Space`** は親指キーで、同時打鍵の判定を通る。キー表の `Space` は、判定の結果が**単独打鍵**（今の `ThumbTap`）になったときに引く。
  文字キーと同時に押した Space は親指シフトで、キー表を見ない。
  先行の親指シフト実装（ibus-anthy、fcitx5-anthy、やまぶきR、awase）と同じ扱いなので、他の IME のプリセットの `Space` の行はそのまま使える。
- **修飾付きの Space**（Shift+Space、Ctrl+Space など）は親指キーにしない。押した時点で、ふつうの機能キーとして表を引く。
- **`global` の行は、局面の行が無いときに効く**（親をたどった最後）。Shift+CapsLock のように、`global` で切り替え、`composing` では英数の続き、と局面で意味を変えられる。
  ただし Alt 付き（Ctrl なし）の和音は、次のとおり `global` にしか書けない。
- **Alt 付き（Ctrl なし）の和音は `global` だけ。** TSF は Alt+文字 などを `OnTestKeyDown`／`OnKeyDown` に渡さず、
  PreservedKey に登録したものだけが届く（[windows.md](keybind/windows.md) §1.3）。PreservedKey は局面に関係なく先に食べるので、局面ごとに意味を変えられない
  （`OnPreservedKey` で FALSE を返したときにキーがアプリに通るかは定まっていない。[windows.md](keybind/windows.md) §9）。
  Ctrl+Alt の和音はふつうのキーと同じく届くので、局面ごとに割り当てられる。
- **テンキー**は今「その他のキー」で、入力中に押すとアプリに通る。MS-IME と同じく、テンキーの数字と記号は、Shift 面と同じリテラル（半角の数字・記号を 1 字入れる）として
  打鍵層に入れる。`converting` 以降では、数字の段と同じく割り当てを先に見る。

### 5.3 割り当てのないキー

表を親までたどっても行が無いときの扱い。これも固定の規則にする。MS-IME の動き（[ms-ime.md](keybind/ms-ime.md) §1.5）に合わせる。

| 局面 | 修飾なし・Shift・Ctrl 付き | Alt 付き・Win 付き |
|---|---|---|
| direct、empty | アプリに通す | アプリに通す |
| composing 以降 | **確定してアプリに通す**（`commit_and_pass`） | アプリに通す（Alt を押したときに確定している） |

- MS-IME は、入力がある間、働きの無いキーの多くを確定してからアプリに通す（Insert、PageUp、Ctrl+C、Ctrl+V、Ctrl+Shift+矢印など）。
  食べて何もしないキー（Shift+Enter など）と、確定せずに通すキー（F1、Ctrl+Tab、Ctrl+Home など）もある。これらは MS-IME のプリセットに `noop`・`pass_through` の行として書く。
- **入力がある間に Alt を押すと、全部確定する。** MS-IME は Alt だけを押して離しても、割り当ての無い Alt+Z でも確定する。
  Alt キーそのものはキーの呼び出しに届く（[windows.md](keybind/windows.md) §1.3）ので、TIP がそれを見て確定を頼み、Alt は通す（§8.2）。
- Alt 付き（Ctrl なし）の和音は TIP に届かず、アプリのメニューなどに行く。`global` に割り当てたものだけを PreservedKey で受け取る（§5.2）。

---

## 6. 設定ファイル

### 6.1 置き場所

| ファイル | 中身 | 書く人 |
|---|---|---|
| `<インストール先>/yuragi/data/keymaps/<名前>.json` | プリセット。読むだけ | 配布物 |
| `~/.yuragi-ime/keymap.json` | 利用者の設定（どのプリセットを使うか、そこからの差分） | 設定ウィンドウ。手で書いてもよい |

`keymap.json` が無ければ、MS-IME のプリセット（`ms-ime.json`）をそのまま使う。

MS-IME のプリセットは、新 MS-IME を実機で見た動き（[keybind/ms-ime.md](keybind/ms-ime.md) §1.5。食べるか、確定して通すか、そのまま通すか）のとおりにする。
働きの名前と、実機で見ていないキーは、旧 MS-IME のテンプレート「Microsoft IME」のキー設定の表（ms-ime.md §2）による。
US 配列に無いキー（変換・無変換・かな・英数・半角/全角・ひらがな・カタカナ）の行は持たず、
新 MS-IME の US 配列での代わり（オン/オフの Alt+`` ` ``、入力モードの Ctrl/Shift/Alt+CapsLock。ms-ime.md §1.2、§1.5）を使う。
TIP はどちらのファイルも読まない（§9）。

### 6.2 プリセットの形式

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
- 同じ（局面, 和音）の行が 2 つあったら、後の行を使い、読み込みの記録に残す。編集画面では保存させない。
- プリセットは全部の行を書く（他のプリセットを土台にしない）。プリセット同士が独立なので、1 つを直しても他に響かない。

### 6.3 利用者の設定の形式（ユーザー定義）

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
- `tip.json` の `toggle_vk`・`toggle_mods` は読み続ける。`keymap.json` が無いときに限り、その値を MS-IME のプリセットに重ねる `ime_toggle` の差分として扱う
  （今の設定がそのまま効く。古い DLL が残っているアプリとも食い違わない）。

### 6.4 読み込みの規則

読むのはエンジンだけ（`yuragi/ime/keymap.py`）。DESIGN「互換の規則」と同じ考え方で、**悪い行だけを落とし、残りは使う**。

| 起きたこと | 扱い |
|---|---|
| `keymap.json` が無い | MS-IME のプリセット |
| `keymap.json` が JSON として読めない、`use`・`base` のプリセットが無い | MS-IME のプリセット。注意 `keymap` を出す |
| 知らないコマンド、知らない局面、読めない和音 | その行を無視。記録に残す（新しい版で作った設定を古い版が読んでも壊れない） |
| その局面で使えないコマンド（`phases` の外） | その行を無視。記録に残す |
| §5.2 で割り当てられない和音（`composing` の `A` など） | その行を無視。記録に残す |
| `global` の和音が他の局面にもある | 他の局面の行を無視。記録に残す |
| まだ実装していないコマンド | その行を無視（記録には残さない。プリセットに先に書いておける） |
| `version` が知らない値 | 読める行だけ読む |

- 無視した行の一覧は、エンジンのログと、設定ウィンドウの「キー」タブに出す。
- 注意 `keymap` は、今の注意 `lm` と同じ道（エンジン → ブローカー → 設定ウィンドウの「状態」タブ）で出す。通知は出さない。
- 読み込みの結果は、どの入力でも例外にならない。キー表が作れないときは必ず MS-IME のプリセットになる
  （MS-IME のプリセットが読めないのは配布物の破損で、エンジンは内蔵の同じ表を使う。§10）。

---

## 7. エンジン

### 7.1 モジュール

| ファイル | 中身 |
|---|---|
| `yuragi/chord/keys.py` | 今の `classify()` に加えて、和音の型 `Chord(vk, mods)`、和音の書き方の読み書き、打鍵層の判定 |
| `yuragi/ime/keymap.py`（新） | プリセットと `keymap.json` を読み、検査し、**引くだけの表**に直す。食べる表を作る |
| `yuragi/ime/commands.py`（新） | コマンド表。コマンドの属性と、`ImeSession` のどのメソッドを呼ぶか |
| `yuragi/ime/session.py` | `on_key()` を表引きに変える。操作の中身（`_commit`、`_cycle`、`_resize` など）は変えない |
| `yuragi/data/keymaps/*.json`（新） | プリセット |

キー表はエンジンに 1 つ（`Engine.keymap`）で、全部のセッションが同じものを参照する。中身は作ったあと変えない
（読み直しのときは、新しい表を作って参照ごと入れ替える）。

### 7.2 コマンド表

```python
@dataclass(frozen=True)
class Command:
    id: str
    label: str
    phases: frozenset[str]
    key: str = "eat"            # eat / pass / commit_pass
    where: str = "engine"       # engine / tip
    run: Callable[[ImeSession], str | None] | None = None   # 確定した文字を返す。tip のコマンドは None

COMMANDS = {c.id: c for c in (
    Command("convert", "変換", COMPOSING, run=lambda s: s._convert()),
    Command("commit", "全確定", INPUT, run=lambda s: s._commit()),
    Command("segment_shrink", "文節を縮める", CONVERTED, run=lambda s: s._resize(-1)),
    Command("select_candidate_3", "候補 3 を選ぶ", SELECTING, run=lambda s: s._select_row(2)),
    ...
)}
```

- コマンドの追加は、この表に 1 行足すことで終わる。TIP・ブローカー・通信は変えない（食べる表が自動で変わる）。
- `run` を持たないエンジンのコマンドは「まだ実装していない」で、キー表を作るときにその行を落とす。
- 今の `_edit(vk)`・`_on_cand_key(vk)`・`_select_script(vk)` は仮想キーコードで分岐している。これを操作ごとのメソッドに分ける
  （`_select_script(vk)` → `_to_script("hiragana")` など）。分けたあと、仮想キーコードを知っているのは `keys.py` と `keymap.py` だけになる。

### 7.3 局面

`ImeSession` に、今のフィールドから求めるプロパティを足す。新しく持つ状態は、文節長変更中かどうか（`resizing`。文節を伸縮すると立ち、ほかの操作で倒れる）だけ。

```python
@property
def phase(self) -> str:
    if self.direct:      return "direct"
    if not self.tokens:  return "empty"
    if self.predicting:  return "predicting"
    if not self.converted: return "composing"
    if self.resizing:    return "resizing"
    return "selecting" if self.candidates else "converting"
```

### 7.4 打鍵の処理

`on_key()` の新しい流れ。**表を引くのは、コマンドを実行する時点**にする（下の 2 と 3）。
同時打鍵の判定待ちや LM 待ちが残っている間に次のキーが来ても、待ちが片づいたあとの局面で意味が決まる。
今の Enter・BS・Esc はすでにこの順序で動いており、それを全部のキーに広げる。

```
on_key(down, vk, t, mods):
  0. 直接入力なら何もしない。修飾キー自体は、押されているかの記録だけ。
     ただし Alt キーの down は、入力があれば判定待ちを締めて全確定する（§5.3。eat は false）。
     up は、同時打鍵の判定に入った down の分だけ判定に渡す。コマンドとして使った down の up は捨てる。
  1. 和音を作る。chord = Chord(vk, mods)
  2. 打鍵層でない和音（機能キー、Ctrl/Alt 付き、修飾付きの Space）:
       a. 判定待ちの打鍵を締める（今の _finish_pending）
       b. LM 待ちがあれば、残りを待ちのあとに回す（今の _then）
       c. その時点の局面で表を引く → コマンドを実行。行が無ければ §5.3
  3. 打鍵層の和音（文字キー、修飾なしの Space）:
       a. 局面が converting 以降（LM 待ちがあれば、2b と同じく待ちのあとの局面で見る）で、
          表に行があれば → 判定待ちを締めて、コマンドを実行（同時打鍵の判定には入れない）
       b. それ以外 → 今と同じ。Shift 面・英数の続き・同時打鍵の判定へ
  4. 同時打鍵の判定が「Space の単独打鍵」（ThumbTap）を出したとき:
       その時点の局面で、和音 `Space` として表を引く → コマンドを実行。行が無ければ何もしない
```

- 4 が、今 `_ingest()` の中に直書きされている「入力があれば変換、変換済みなら次の候補、無ければ全角空白」に当たる。
  MS-IME のプリセットでは `empty`→`insert_space`、`composing`→`convert`、`converting`→`next_candidate`（候補窓を開く）などの行になる（Space の割り当ては ms-ime.md §1.4、§2.1）。
- 2c で LM 待ちがあるとき、今の `ConversionRequest` と `_continuation` の仕組みをそのまま使う。回すものが「表を引いて実行する」1 つになる。
- 押しっぱなしの繰り返しの down も、1 打として表を引いて実行する（MS-IME と同じ。§8.4）。
- コマンドが例外を出したときは、今と同じく DESIGN「要求 1 件ごとの防壁」で受ける。

### 7.5 返事に足す項目

| 項目 | 中身 |
|---|---|
| `phase` | 返事の時点の局面（§7.3）。同時打鍵の判定待ち・LM 待ちがあっても、求め方は同じ |
| `eat` | この要求のキーを食べたか。`true`／`false`。down の要求の返事にだけ付く（TIP は up を食べない。§8.4） |

`eat` の決め方:

| 起きたこと | `eat` |
|---|---|
| コマンドを実行した | コマンドの `key` が `eat` なら `true`、`commit_pass` なら `false`（TIP はこれを見て、確定のあとにキーを送り直す。§8.6）。`pass` のコマンドは食べる表の `pass` に入り、TIP が送らないので返事は無い |
| 同時打鍵の判定に入った（文字キー、Space） | `true` |
| 割り当てなし | §5.3 のとおり（「通す」なら `false`） |
| 直接入力 | `false`（今の `pass_through` と同じ） |

TIP は `OnKeyDown` の答えをこの `eat` では変えない（§8.3）。これで、TIP の `EatAfterReply()` が持っている「返事を見て、食べたかを推測する」規則が要らなくなる。

---

## 8. TIP

### 8.1 食べる表

TIP が持つのは、エンジンが作った次の形の表だけ。親の局面の引き継ぎも検査も済んでいて、TIP は探すだけ。

```json
{"rev": "3f9a1c",
 "phases": {
   "empty":      {"eat": [520, 544], "pass": []},
   "composing":  {"eat": [13, 8, 27, 9, 117, 597, 552], "pass": [], "rest": "eat"},
   "converting": {"eat": [...], "pass": [...], "rest": "eat"},
   "selecting":  {"eat": [...], "pass": [...], "rest": "eat"},
   "resizing":   {"eat": [...], "pass": [...], "rest": "eat"},
   "predicting": {"eat": [...], "pass": [...], "rest": "eat"}},
 "global": [{"code": 1216, "command": "ime_toggle"}]}
```

- 数字は和音の整数（§5.1）。`eat` は「受け取って、エンジンに送る」、`pass` は「送らずに通す」（`pass_through` の行）。
  `commit_pass` のコマンドは `eat` に入る（エンジンに送って食べ、確定のあとに送り直す。§8.6）。
- `rest` は、どちらにも無い和音の扱い（§5.3）。`"eat"` は「受け取ってエンジンに送る」（エンジンが確定して `eat:false` を返し、TIP が送り直す）。Alt 付き・Win 付きは通す。
- `global` は `direct` と準備中にも効く行で、TIP が自分で実行する（§8.5）。局面の表に同じ和音があれば、局面の表が先。
- 打鍵層の和音（文字キー、修飾なしの Space）は表に入れない。かな入力の間は常に受け取る（今と同じ）。
  `converting` 以降で文字キーに割り当てがあっても、TIP から見れば「受け取る」で同じ。
- `rev` は表の中身から作った短い識別子。同じ表を配り直したとき、TIP が何もしないで済む。
- 大きさは数 KB。接続のときと、変わったときにだけ届く。

### 8.2 `tip_logic.h` の変更

```cpp
enum class Phase { Empty, Composing, Converting, Selecting, Resizing, Predicting };
enum class Take { Pass, Send };              // アプリに通す／エンジンに送る

struct KeyTable { ... };                     // ParseKeyTable(json) で作る。Lookup(phase, code) → Eat/Pass/Rest
struct Local {
    Phase phase = Phase::Empty;              // 最後に反映した返事の phase
    bool unsettled = false;                  // 返事を待つ要求がある、または判定のタイマーが掛かっている
};

Take WantKey(uint32_t vk, Mods mods, const Local& local, const KeyTable& table);
```

`WantKey()` の規則（`OnTestKeyDown`。通信しない）:

1. Win 付き → 通す。
2. Alt キーそのもの → 通す。局面が `composing` 以降（または `unsettled`）なら、同じ down をエンジンにも送る。
   エンジンは確定し（§7.4 の 0）、TIP は確定を書くが、Alt は送り直さない（もうアプリに渡っている）。
3. 打鍵層の和音 → 送る。
4. `unsettled` でない → `table.Lookup(local.phase, code)` のとおり。
5. `unsettled` → **`composing` 以降のどれかの局面で受け取る和音なら、送る。** 局面がまだ決まっていないので、広く受け取る。
   今の「返事を待っている要求があれば変換中とみなす」を、表に合わせて言い直したもの。

返事が来たあと:

- `WantKey()` が送ると決めたキーは、`OnKeyDown` でも食べる（§8.3）。返事が `eat:false` なら、そのキーはアプリに渡すべきだったので、
  確定などを文書に書き終えたあとで送り直す（§8.6）。`commit_pass` のコマンド、割り当ての無いキー（§5.3）、規則 5 で広く受け取ったキーがこれに当たる。`EatAfterReply()` の今の規則は消す。
- 返事が `KEY_BUDGET_MS` に間に合わなかったら、今と同じく `WantKey()` の判定どおりに食べる。
  `commit_pass` のコマンドは、確定が後から届き、書き終えたところで送り直す（§8.6）。
- TIP の手元のフラグ `composing_`・`converted_` は、`phase` から求める（表示の制御には引き続き使う）。

表がまだ届いていないとき（ブローカーにつながる前、古いブローカー）は、DLL に埋め込んだ MS-IME のプリセットの食べる表を使う。
埋め込む表はビルドのときにプリセットから作り、食い違いは試験で見つける（§10）。

### 8.3 キーの処理の流れ

DESIGN「打鍵の処理」の 1–4 は変えない。変わるのは、「食べるか」の答えの出どころだけ。

```
OnTestKeyDown:  和音に戻す（§8.4）→ 常時のキーか（§8.5）→ WantKey(…, table)
OnKeyDown:      同上（同じ答え）
OnKeyUp:        食べない。エンジンに送った down の up は、エンジンにも送る（§8.4）
返事:           phase を覚える。eat:false なら送り直す（§8.6）
```

**`OnTestKeyDown` と `OnKeyDown` は、同じキーに必ず同じ答えを返す。** アプリには `OnKeyDown` だけを呼ぶものと、先に `OnTestKeyDown` を呼んで
TRUE のときだけ `OnKeyDown` を呼ぶものがあり、後者では `OnTestKeyDown` に TRUE と答えたキーは、`OnKeyDown` で FALSE を返してもアプリに届かない
（[windows.md](keybind/windows.md) §1.1）。答えは食べる表と手元の局面だけで決め、エンジンの返事では変えない。食べる表とエンジンが食い違わないことは試験で保つ（§10.2）。

### 8.4 キーの出来事の扱い

MS-IME と同じく、届いた出来事を 1 つずつ、届いた時点の形で扱う（[ms-ime.md](keybind/ms-ime.md) §1.5）。前提の事実は [windows.md](keybind/windows.md)。

| 出来事 | 扱い | 前提の事実 |
|---|---|---|
| down | 仮想キーコードと、その出来事の時点の修飾から和音に戻す。`VK_KANJI` は Alt+`` ` ``、`VK_DBE_*` は修飾付きの CapsLock・Ctrl+`` ` ``（表で戻す） | `kbd101` の読み替えは出来事ごとの修飾で決まる（windows.md §3.1、§3.2、§3.5） |
| 繰り返しの down | ふつうの down と同じ。1 打ずつ表を引いて実行する。オン/オフも繰り返しのたびに切り替わる。Alt を先に離したあとの繰り返しは `` ` `` として届くので、`` ` `` を打つ | MS-IME も同じ（ms-ime.md §1.5）。修飾を先に離したあとの繰り返しは修飾なしのキーとして届く（windows.md §3.4） |
| up | 食べない。エンジンに送った down の up は、エンジンにも送る（同時打鍵の判定に要る）。返事は待たない | MS-IME も、食べた down の up をアプリに渡す（ms-ime.md §1.5） |
| up が来ない | 次の down を、ふつうの down として扱う（up が来なかったキーを、押されたままとして扱い続けない） | 順 C の Ctrl+`` ` ``・Shift+CapsLock、Alt でメニューに入ったあとの up は来ない（windows.md §3.2） |

- 押されているかを、`VK_KANJI`・`VK_OEM_3` の `GetKeyState` で判定しない。順 B・順 C で押されたままに見える（windows.md §3.3）。
- キーの up を作って送らない。`VK_KANJI` が押されたままに見えるのは配列ドライバの動きで、どの IME でも起きる（windows.md §3.3）。

### 8.5 常時のキー（オン/オフ・モードなど）

`global` の行は、TIP が自分で実行する。直接入力の間も、準備中も効く必要があるため。

- 実行できるコマンドは `where: tip` のものだけ: `ime_toggle`・`ime_on`・`ime_off`・`mode_hiragana`・`mode_katakana`（手元の入力モードを変え、今の `set_direct` などを送る。
  入力があれば、先にエンジンに確定を頼む）、`open_settings`・`open_word_register`（ブローカーに `open_admin` を送る）。
- **Alt 付き（Ctrl なし）の行だけを TSF の PreservedKey に登録する。** Alt 付きの和音は PreservedKey にしか届かない（[windows.md](keybind/windows.md) §1.3）。
  ほかの行は `OnKeyDown` で照合する（局面の表に同じ和音があれば、そちらが先。§8.1）。
- 登録の形は、TSF に届く形に合わせる。**Alt+`` ` `` は `{VK_KANJI, TF_MOD_IGNORE_ALL_MODIFIER}` で登録する**
  （`{VK_OEM_3, TF_MOD_ALT}` や `{VK_KANJI, TF_MOD_ALT}` には届かない。[windows.md](keybind/windows.md) §3.6）。同じ理由で、§5.1 の IME 用のキーに変わる和音（Alt+CapsLock など）は、変わったあとの仮想キーコードで登録する。
- PreservedKey には 1 つずつ GUID が要る。決まった GUID の列から、Alt 付きの行に順に当てる。1 スレッドで 40 個まで登録できる（[windows.md](keybind/windows.md) §1.4）。
  それより多い行は読み込みで落とし、記録に出す。
- 表が変わったら、登録を全部外して登録し直す。アクティブなまま登録し直せて、すぐ効く。
  登録は TIP のスレッドで行う（読み取りスレッドから届いた表は、今の非同期の返事と同じ道で UI スレッドに渡す）。
- PreservedKey は押し続けると繰り返しのたびに呼ばれる。そのたびに実行する（MS-IME と同じ。§8.4）。
- 準備中に効くのはオン/オフとモードの切り替えだけ（今の `tip_logic::Toggles` を広げる）。停止・対象外では、`open_settings` だけを受け取る。
- パスワード欄では、今と同じくどれも食べない。

### 8.6 食べたキーをアプリに渡す（送り直し）

`OnTestKeyDown` で食べると答えたキーを、あとから通すことはできない（§8.3）。返事が `eat:false` のキー（`commit_and_pass`、割り当ての無いキー、§8.2 の規則 5 で受け取ったキー）は、

1. キーは食べる。
2. エンジンの返事の確定を、いつもどおり文書に書く。
3. 書き終えたあと、同じキーを `SendInput` で送り直す。送り直すキーには `dwExtraInfo` に印を付け、TIP はその印のあるキーを見ずに通す。

送り直すまでのあいだに利用者が次のキーを押すと、順序が入れ替わるので、そのあいだのキーは送り直しが済むまで手元に溜める。`dwExtraInfo` が TIP のキーの呼び出しの中で読めない場合（[windows.md](keybind/windows.md) §9）は、
送り直すキーを手元で覚えておき、次に来た同じキーを 1 回だけ通す。

---

## 9. 通信

プロトコル 1 のまま、項目を足すだけにする（DESIGN「互換の規則」）。

### 9.1 足す項目

| 向き | 足すもの | 中身 |
|---|---|---|
| TIP → ブローカー | `{"op":"set_mode","mode":"katakana"}` | 入力モード（`hiragana`・`katakana`）。`mode_hiragana`・`mode_katakana`（§8.5） |
| TIP → ブローカー | `{"op":"open_admin","tab":"words"}` | 開くタブ。無ければ今と同じ |
| エンジン → ブローカー | `ready` に `"keymap":{…}` | 食べる表（§8.1） |
| エンジン → ブローカー | `{"event":"keymap","keymap":{…}}` | 読み直したあとの表 |
| ブローカー → エンジン | `{"op":"reload_keymap"}` | 設定ファイルを読み直す |
| ブローカー → TIP | hello の返事に `"keymap":{…}` | ブローカーが持っている最新の表。無ければ項目ごと無い |
| ブローカー → TIP | `{"event":"keymap","keymap":{…}}` | 表が変わった |
| エンジン → TIP（返事） | `"phase"`、`"eat"` | §7.5 |
| 設定ウィンドウ → ブローカー | `{"op":"reload_keymap"}` | 保存したあとに送る |

ブローカーは表の中身を解釈しない。エンジンから受け取った JSON の値を覚えておき、そのまま配る。
エンジンが落ちても、ブローカーは最後の表を持ち続ける（新しいエンジンが `ready` で言い直すまで）。

### 9.2 表をパイプで配る理由

TIP に `keymap.json` を読ませない。理由は 3 つ。

1. **読み方が 1 つで済む。** 引き継ぎ・差分・検査を C++ にも書くと、エンジンと食い違う。
2. **サンドボックス内のアプリにも届く。** パイプは「すべてのアプリパッケージ」に開いているが、利用者のフォルダは読めない。
3. **全部のアプリに同時に届く。** ファイルだと、アプリごとに読む時機がずれる。

### 9.3 設定を変えたときの流れ

```
設定ウィンドウ: keymap.json を書く（一時ファイルに書いて置き換える。今の config.json と同じ）
      │ {"op":"reload_keymap"}
      ▼
ブローカー ──→ エンジン: 読み直して、新しいキー表に入れ替える（要求と要求の間で。再起動しない）
      ▲            │ {"event":"keymap","keymap":{…}}
      └────────────┘
ブローカー: 表を覚え、つながっている全部の TIP に {"event":"keymap",…} を送る
TIP: rev が違えば表を入れ替え、常時のキーを登録し直す
```

- 入れ替えの間に入力中だったセッションは、そのまま新しい表で続ける（表を引くのは毎回その時点なので、食い違いは起きない）。
- 読み直しに失敗したら（§6.4）、エンジンは前の表を使い続け、設定ウィンドウに理由を返す。
- エンジンが `ready` でないときに保存した設定は、次の起動で読まれる。

### 9.4 版が混ざるとき

更新のあと、開いたままのアプリには古い DLL が残る。

| 組み合わせ | 動き |
|---|---|
| 古い DLL ＋ 新しいエンジン | DLL は `keymap`・`phase`・`eat` を無視し、今の `WantKey`・`EatAfterReply` で動く。今の `WantKey` が通すキー（Ctrl 付きなど）の割り当ては、そのアプリを開き直すまで届かない。切り替えキーは `tip.json` の値（§6.3） |
| 新しい DLL ＋ 古いエンジン | 更新の途中の短い間だけ。表が届かないので内蔵の表、`eat` が無いので `WantKey` の判定どおり |

設定ウィンドウの「キー」タブに、「変更は、開いたままのアプリでは開き直すまで一部が効かないことがある」と 1 行書く
（更新の直後だけ起きる。ふだんは全部のアプリにすぐ届く）。

---

## 10. 設定ウィンドウと試験

### 10.1 「キー」タブ

今の 4 つのタブ（単語登録・学習・設定・状態）に足す。作りは旧 MS-IME のキー設定の画面（[ms-ime.md](keybind/ms-ime.md) §3.2）に合わせる。

| 部品 | 中身 |
|---|---|
| キー設定 | プリセットの一覧と「ユーザー定義」から選ぶ。表を変えると「ユーザー定義」になる（§6.3） |
| 表 | 行がキー、列が局面（常時・入力なし・入力中・変換中・候補選択中・文節長変更中・予測の候補）。欄に機能の名前を出し、割り当てなしは「–」 |
| 変更 | 欄をダブルクリックするか［変更］を押すと、その局面で使える機能の一覧が開き、そこから選ぶ |
| キー追加 | 表に無いキーを、キーと修飾の一覧から選んで足す。§5.2 で割り当てられない和音は一覧に出さない。Alt 付き（Ctrl なし）の和音は、常時の列だけを変えられる |
| 読み込みの記録 | `keymap.json` に無視した行があれば、理由と一緒に出す（§6.4） |

- 選べるのは用意したキーと機能だけなので、§5.2 に反する行や、同じ（局面, キー）の重なりは作れない。
- 保存は「保存」を押したとき。押すと §9.3 の流れで、すぐ全部のアプリに効く。

### 10.2 試験

黙って壊れる所だけを試験する。

| 試験 | 見つけるもの |
|---|---|
| 今の試験（`tests/transcripts/`、`test_partial_commit` など）を、MS-IME のプリセットで通す。MS-IME と違っていたキーは期待値を MS-IME に直す | 表引きにしたときの、意図しない挙動の変化 |
| **TIP とエンジンの突き合わせ**: 局面 × 和音の全部の組について、エンジンに実際にキーを送ったときの `eat` と、C++ の `WantKey()` が食べる表から出す答えが同じ。Python が期待値のファイルを作り、`tip_logic_test.cpp` がそれを読む。ファイルが古いと Python 側の試験が落ちる | TIP とエンジンの食い違い（キーがアプリに抜ける、食べたまま何も起きない） |
| DLL に埋め込んだ表 ＝ MS-IME のプリセットから作った表 | 埋め込みの作り忘れ |
| 悪い行の混ざった `keymap.json` で、良い行は効き、悪い行だけが落ちる | 1 行の誤りで設定の全部が消えること |
| 判定待ち・LM 待ちの間に機能キーを押す（Space の直後の Enter、変換待ちの間の ←） | 表を引く時機の誤り（待ちが片づく前の局面で引いてしまう） |
| コマンドとして使った文字キーの up が、同時打鍵の判定に入らない | 候補を番号で選んだ直後の誤入力 |
| TIP のキーの出来事の扱い（§8.4）: TSF の呼び出しの列（[windows.md](keybind/windows.md) §3.2 の順 A〜D、押し続け、up が来ない列、対で届く IME 用のキー、PreservedKey の繰り返し）を `tip_logic_test.cpp` で与え、和音と食べるかが ms-ime.md §1.5 の MS-IME と同じ | 和音への戻し誤り、up を食べること、繰り返しで実行しないこと |
| 実機: ブランチ `keyprobe` の `msime_tsf_table.py` と同じ表を、ゆらぎで採り、MS-IME の表と比べる（食べるか、確定して通すか、そのまま通すか） | プリセットと MS-IME の食い違い |
| 実機: [keybind/windows.md](keybind/windows.md) §1・§3 の表の項目を、ブランチ `keyprobe` の道具（`tools/keyprobe/README.md`）で、変更のたびに確かめる | TSF・配列ドライバの前提の崩れ（自動の試験では見つからない） |

---

## 11. 作る順序

各段は、それだけで出荷できる（前の段までで挙動が閉じている）。

| 段 | 中身 | 利用者に見える変化 |
|---|---|---|
| 1 | エンジン: 和音、局面、コマンド表、キー表（MS-IME のプリセット）。`on_key()` を表引きに。返事に `phase`・`eat` | 今の TIP がエンジンに送っているキーが、MS-IME の割り当てで動く（Shift+Space、LM 待ちの間のキーなど） |
| 2 | TIP: 食べる表、`WantKey()` を表引きに、`OnTestKeyDown` と `OnKeyDown` の答えをそろえる、キーの出来事の扱い（§8.4）、常時のキー。ブローカーが表を配る | Ctrl 付きのキー、入力中の機能キー、Alt での確定が MS-IME と同じになる |
| 3 | `keymap.json`（ユーザー定義）、読み直し、設定ウィンドウの「キー」タブ | キーを変えられる |
| 4 | ほかのプリセットを足す（ATOK など。[keybind/ime-survey.md](keybind/ime-survey.md) §4）。足りないコマンドを作る（§4.2 の × の行） | プリセットを選べる。MS-IME の表のうち、まだ効かなかった行が効く |

段 1 と 2 のあいだは、古い DLL と新しいエンジンの組み合わせ（§9.4）と同じ状態なので、段 1 だけを先に出しても壊れない。
