# ATOK のキー操作とカスタマイズ

ATOK Passport（ATOK for Windows / ATOK for Mac、Tech Ver.36 世代）の既定キー、キーカスタマイズの仕組み、機能をまとめる。出典は末尾の「出典」の略号で示す。

「状態」は、ATOK のキーカスタマイズ画面の状態区分（文字未入力・入力中など）を指す。

---

## 1. 既定のキー割り当て（ATOK スタイル）

### 1.1 Windows 版 [W36 p.98–101]

#### 変換操作

| 機能 | キー |
|---|---|
| 変換／次候補 | スペース／変換／Ctrl+↓／Shift+スペース |
| 変換／前候補 | ↑／Ctrl+↑ |
| 推測変換 | Tab |
| 再変換（読みへの復帰） | Shift+変換 |
| 連想変換 | Ctrl+Tab |
| ひらがな（後）変換 | F6／Ctrl+U |
| カタカナ（後）変換 | F7／Ctrl+I |
| 半角（後）変換 | F8／Ctrl+O |
| 全角無変換（後）変換 | F9／Ctrl+P |
| 半角無変換（後）変換 | F10／Ctrl+@ |
| 読みの英字／カナ置換 | F11 |
| 人名変換辞書セットで変換 | F2 |
| 郵便番号辞書セットで変換 | F3 |
| アクセサリ辞書セットで変換 | F4 |
| オプション辞書セットで変換 | F5 |
| 一文字入力辞書セットで変換 | Shift+F6 |

#### 文字編集、確定、取消操作

| 機能 | キー |
|---|---|
| 全文確定 | Enter／Ctrl+M |
| 部分確定 | ↓／Ctrl+N |
| 1 音確定 | Shift+↓ |
| 自動表示候補確定（推測候補の確定） | Shift+Enter／Ctrl+Enter |
| 先頭 1 文字を確定 | PageDown |
| 末尾 1 文字を確定 | PageUp |
| 変換取消 | Backspace／Ctrl+H |
| 全文字削除 | Esc／Ctrl+[ |
| 前文字削除 | Backspace／Ctrl+H |
| 1 文字削除 | Delete／Ctrl+G |
| 注目文節削除 | Shift+Delete |
| 読みの入力誤り位置へジャンプ | Ctrl+J |
| 自動修復取消 | Shift+Backspace |
| カーソルを前へ移動 | ←／Ctrl+K |
| カーソルをうしろへ移動 | →／Ctrl+L |
| カーソルを先頭へ移動 | Ctrl+← |
| カーソルを末尾へ移動 | Ctrl+→ |

#### 起動操作

| 機能 | キー |
|---|---|
| プロパティ（環境設定） | Ctrl+F12 |
| 文字パレット | Ctrl+F11 |
| お気に入り文書メニュー | Shift+Ctrl+F11 |
| お気に入り文書リピート | Shift+Ctrl+F12 |
| 校正支援 見逃し指摘ビューア | Shift+Ctrl+F10 |
| ATOK MiRA | Shift+Ctrl+M |

#### 候補操作（候補ウィンドウ表示中）

| 機能 | キー |
|---|---|
| 次の候補群を表示 | 変換 |
| 前の候補群を表示 | Shift+変換 |
| 次のグループへ移動 | Tab／Ctrl+J |
| 前のグループへ移動 | Shift+Tab |
| 先頭文字並べ替え | Ctrl+PageDown |
| 末尾文字並べ替え | Ctrl+PageUp |
| 情報ウィンドウ表示／表示切替 | End |
| 情報ウィンドウ非表示 | Shift+End |
| 情報ウィンドウ次ページへ移動 | Shift+Ctrl+PageDown |
| 情報ウィンドウ前ページへ移動 | Shift+Ctrl+PageUp |
| 電子辞典 部分一致検索 | Shift+Ctrl+End |
| 全候補を表示 | Ctrl+スペース |
| IVS 選択ウィンドウオープン／クローズ | Home |

- 候補番号の 1〜9 キーでも確定できる。
- 0 キーは「0 番」の別機能の候補（カタカナ・英字、訂正候補、日付形式、別文節区切り、連想変換、ATOK ダイレクトなど）を順に切り替える [W36 p.48–50]。

#### 文節操作（文節区切り直し中・変換中）

| 機能 | キー |
|---|---|
| 文節の区切りを前へ移動（縮める） | ←／Ctrl+K |
| 文節の区切りをうしろへ移動（伸ばす） | →／Ctrl+L |
| 注目文節を前へ移動 | Shift+← |
| 注目文節をうしろへ移動 | Shift+→ |
| 注目文節を先頭へ移動 | Ctrl+← |
| 注目文節を末尾へ移動 | Ctrl+→ |

- ローマ字単位区切りの移動（Shift+Ctrl+← / →）は [W36] の表に無い。[FAQ08] と [GIST34] にはある（§1.3）。
- 縦書きでは、文節の確定は ←、文節の区切り直しは ↑・↓ [W36 p.47]。

#### 機能操作

| 機能 | キー |
|---|---|
| 日本語入力オン／オフ | 半角全角 |
| 単語登録 | Ctrl+F7 |
| 単語削除 | Ctrl+Delete |
| 確定のアンドゥ | Ctrl+Backspace |
| 確定のリピート | Ctrl+F8／Shift+Ctrl+R |
| ATOK メニュー | Ctrl+F10 |
| 入力文字種切替メニュー | Ctrl+F9 |
| 変換辞書切替メニュー | Ctrl+F8（下の注を参照） |
| 漢字／半角モード切替 | 変換 |
| 固定入力英字順次切替 | Shift+無変換 |
| 固定入力カナ順次切替 | Ctrl+無変換 |
| 漢字入力モード順次切替 | ローマ字（Alt+カタカナひらがな）※109/106 のみ |
| 半角無変換固定入力（A）オン／オフ | 無変換 |
| 英語入力モード オン／オフ | Caps Lock英数 |
| カナ入力切替 | カタカナひらがな |

変換辞書切替メニューのキーは出典で食い違う: [W36] は Ctrl+F8 を「確定のリピート」と「変換辞書切替メニュー」の両方に載せる。[FAQ08]（ATOK 2008）と [GIST34]（ATOK 34）は変換辞書切替メニューを Shift+F8 とする。

**その他の注記**

- ATOK スタイルでは、変換キーで ATOK をオンにでき、変換キーで漢字入力と半角入力を切り替えられる [W36 p.37, p.52]。
- 推測候補の操作 [W36 p.70]: 先頭候補を確定は Shift+Enter、ほかの推測候補を表示は Tab または ↓、推測候補を削除は Ctrl+Delete。
- [SOZOU] は、再変換は Windows 標準の Win+/ でもできると書く。[W36] には無い。
- **101/104 英語キーボードでの読み替え** [W36 p.2]: Caps Lock英数キー → Caps Lock、カタカナひらがなキー → Shift+Ctrl+Caps Lock。半角／全角（日本語入力オン／オフ）の代わりのキーは資料に無い。

### 1.2 Mac 版 [M-KEY]

Mac のキー名の対応:

| Mac での表記 | Windows のキー |
|---|---|
| `delete` | Backspace（後退） |
| `del` | Delete（前方削除） |
| `return` | Enter |

ファンクションキーやページキーは、キーボードによっては fn キーと一緒に押す [M-KEY]。

#### 変換操作

| 機能 | キー |
|---|---|
| 変換／次候補 | スペースバー／option+スペースバー／control+↓／option+↓ |
| 変換／前候補 | shift+スペースバー／↑／control+↑／option+↑ |
| 推測変換 | tab |
| 再変換 | control+shift+Y |
| 連想変換 | control+A |
| ひらがな（後）変換 | control+U／F6 |
| カタカナ（後）変換 | control+I／F7 |
| 半角（後）変換 | control+O／F8 |
| 全角英字（後）変換 | control+P／F9 |
| 半角英字（後）変換 | control+@／F10 |
| 順次後変換 | option+tab |
| 読みの英字／カナ置換 | control+;／F11 |
| 継続変換（自動変換時） | control+shift+J |
| 辞書セット 1 変換 | control+1／F1 |
| 辞書セット 2 変換（人名変換辞書セット） | control+2／F2 |
| 辞書セット 3 変換（郵便番号辞書セット） | control+3／F3 |
| 辞書セット 4 変換（アクセサリ辞書セット） | control+4／F4 |
| 辞書セット 5 変換（オプション辞書セット） | control+5／F5 |
| 辞書セット 6 変換（一文字入力辞書セット） | control+shift+6／shift+F6 |

#### 確定操作

| 機能 | キー |
|---|---|
| 全文確定 | return／control+M／enter |
| 部分確定 | ↓／control+N |
| 1 音確定 | shift+↓ |
| 自動表示候補確定 | shift+return／shift+enter／control+return／control+enter |
| 無学習全文確定 | option+return／option+enter |
| 自動表示候補選択を前へ移動 | control+↑／shift+tab／option+↑ |
| 自動表示候補選択をうしろへ移動 | control+↓／tab／option+↓ |
| 自動表示候補を閉じる | esc |
| 先頭 1 文字を確定 | page up／control+shift+N |

#### 取消操作

| 機能 | キー |
|---|---|
| 変換取消 | delete／control+H／clear／shift+esc |
| 全変換取消 | control+shift+J |

#### 編集操作

| 機能 | キー |
|---|---|
| 全文字削除 | esc／clear／shift+esc |
| 前文字削除 | delete／control+H |
| 1 文字削除 | control+G／del |
| 注目文節を削除 | shift+del |
| 読みの入力誤り位置へジャンプ | control+J |
| 自動修復取消 | shift+delete |
| 挿入ポイントを前へ移動 | ←／control+K |
| 挿入ポイントをうしろへ移動 | →／control+L |
| 挿入ポイントを先頭へ移動 | control+←／option+← |
| 挿入ポイントを末尾へ移動 | control+→／option+→ |

#### 候補操作

| 機能 | キー |
|---|---|
| 次の候補群を表示 | option+スペースバー |
| 前の候補群を表示 | option+shift+スペースバー |
| 次のグループへ移動 | tab／control+J |
| 前のグループへ移動 | shift+tab |
| 先頭文字並べ替え | control+page up／control+shift+, |
| 末尾文字並べ替え | control+page down／control+shift+. |
| 情報ウインドウを表示／表示切替 | control+W／end |
| 情報ウインドウを閉じる | control+shift+W／shift+end |
| 情報ウインドウ 前ページへ移動 | control+shift+page up |
| 情報ウインドウ 次ページへ移動 | control+shift+page down |
| 電子辞典 部分一致検索 | option+shift+W／control+shift+end |

#### 全候補操作

| 機能 | キー |
|---|---|
| 全候補を表示 | control+shift+スペースバー／control+スペースバー |
| 全候補次へ移動 | スペースバー／→／control+shift+スペースバー／control+スペースバー |
| 全候補前へ移動 | ← |
| 全候補次の行へ移動 | ↓ |
| 全候補前の行へ移動 | ↑ |
| 全候補選択確定 | return／control+M／enter |
| 全候補選択取消 | esc |

#### 文節操作

| 機能 | キー |
|---|---|
| 文節の区切りを前へ移動 | ←／control+K |
| 文節の区切りをうしろへ移動 | →／control+L |
| ローマ字単位区切りを前へ移動 | control+shift+← |
| ローマ字単位区切りをうしろへ移動 | control+shift+→ |
| 注目文節を前へ移動 | shift+← |
| 注目文節をうしろへ移動 | shift+→ |
| 注目文節を先頭へ移動 | control+←／option+← |
| 注目文節を最後へ移動 | control+→／option+→ |

#### 機能操作

| 機能 | キー |
|---|---|
| 単語登録 | control+shift+E／control+F7 |
| 単語削除 | control+D／control+del |
| 確定のアンドゥ | control+delete（＝Ctrl+後退） |
| 確定のリピート | control+shift+R／control+F8 |
| 漢字／半角モード切替 | option+スペースバー |
| ひらがな入力文字種（あ） | control+shift+Z／かな |
| カタカナ入力文字種（ア） | control+shift+X／shift+かな |
| 全角英字入力（Ａ） | control+shift+V／shift+英数 |
| 半角英字入力（A） | control+shift+B／control+英数 |
| 英字入力（A） | control+shift+C／英数 |
| スピーチで英文読み上げ | control+shift+S |

#### 起動操作

| 機能 | キー |
|---|---|
| ヘルプ | control+shift+H |
| 文字パレット | control+shift+D／control+F11 |
| ATOK パレット表示 | control+shift+A |
| 環境設定 | control+shift+F／control+F12 |
| LogoVista 電子辞典で検索（LogoVista がインストールされている場合） | control+shift+0 |
| Spotlight で検索 | control+shift+1 |
| お気に入り文書メニュー | control+shift+F11 |
| お気に入り文書リピート | control+shift+F12 |
| 校正支援 見逃し指摘ビューア | control+shift+9／control+shift+F10 |
| ATOK MiRA | control+shift+M |
| ATOK ダイレクト すべてのプラグインで検索 | control+T |
| ATOK ダイレクト プラグインを指定して検索 | control+shift+T |
| ATOK ダイレクト プラグイン 1〜5 で検索 | 割付けなし |

**Mac の確定のアンドゥ:** 直前の確定だけでなく、さかのぼって繰り返しアンドゥできる。アンドゥできるときは「さらに確定アンドゥ control＋delete」というツールチップが出る。確定のあとに別の文字を入力したり、カーソルを動かしたりするとアンドゥできない [M-UNDO]。

### 1.3 状態 × キー（Windows 版）

**状態区分（8 つ）** [GIST34]。前半の 6 つは [TERRA] にもある。

1. 文字未入力
2. 入力中
3. 変換中
4. 次候補表示中（＝候補ウィンドウ表示中）
5. 全候補表示中
6. 文節区切り直し中
7. 半角入力
8. 記号入力

- 推測候補表示中という独立した状態は無い。推測候補（自動表示候補）の操作は「入力中」などの状態の中に、「自動表示候補確定」「自動表示候補前移動」「自動表示候補次移動」「自動表示候補クローズ」という機能として入っている [GIST34]。
- Mac 版のヘルプには「状態を選択」とある [M-KINO]。Mac 版の状態の名前の一覧は資料に無い。

以下の表は [GIST34]（ATOK 34 のキーカスタマイズを「テキストファイルに出力」したもの）による。機能名はエクスポートでの表記のまま。[GIST34] は ATOK スタイルを利用者が**改変**したもので、改変点は次のとおり（gist の説明文による）。改変に関わるセルには「改変」と書いた。

- Shift+Space をカナ後変換にした。既定では次候補。
- 英数を半角無変換固定入力(A) ON/OFF にした。既定の Caps Lock英数は英語入力モード。
- 変換を次候補群表示にした。
- 文字未入力のときの変換を日本語入力 ON にした。既定は漢字／半角モード切替。

#### 状態 1: 文字未入力

| 機能（エクスポート表記） | キー |
|---|---|
| 再変換 | Shift+変換 |
| 自動表示候補確定／前移動／次移動／クローズ | Ctrl+Enter／Ctrl+↑／Ctrl+↓／Esc |
| 日本語入力ON/OFF | 半角／全角 |
| 日本語入力ON | 変換（改変。既定は漢字／半角モード切替 [W36]） |
| 単語登録 | Ctrl+F7 |
| 確定アンドゥ | Ctrl+BackSpace |
| 確定リピート | Ctrl+F8／Shift+Ctrl+R |
| メニュー | Ctrl+F10 |
| 全入力文字メニュー（＝入力文字種切替メニュー） | Ctrl+F9 |
| 入力モード順次切替 | F10 |
| 固定入力英字順次切替 | Shift+無変換 |
| 固定入力カナ順次切替 | Ctrl+無変換 |
| 漢字モード順次切替 | ローマ字 |
| 半角無変換固定入力(A)ON/OFF | 英数（改変。既定は無変換 [W36]） |
| カナロックON/OFF | ひらがな |
| 文字パレット／お気に入り文書メニュー／お気に入り文書リピート／校正支援 見逃し指摘ビューア | Ctrl+F11／Shift+Ctrl+F11／Shift+Ctrl+F12／Shift+Ctrl+F10 |

#### 状態 2: 入力中（読み入力中。推測候補の自動表示もこの状態）

| 機能 | キー |
|---|---|
| 変換/次候補 | スペース |
| 推測変換 | Tab |
| 確定文字への復帰 | Shift+変換 |
| 連想変換 | Ctrl+Tab |
| ひらがな／カタカナ／半角／全角無変換／半角無変換（後）変換 | F6・Ctrl+U／F7・Ctrl+I（＋Shift+スペースは改変）／F8・Ctrl+O／F9・Ctrl+P／F10・Ctrl+@ |
| 読みの英字/カナ置換 | F11 |
| 継続変換(自動変換時) | Insert |
| 辞書セット 2〜6 変換 | F2／F3／F4／F5／Shift+F6 |
| 全文確定 | Enter／Ctrl+M／Shift+Enter |
| 部分確定 | ↓／Ctrl+N |
| 1音確定 | Shift+↓ |
| 自動表示候補確定／前移動／次移動 | Ctrl+Enter／Ctrl+↑・Shift+Tab／Ctrl+↓ |
| 全文字削除 | Esc／Ctrl+[ |
| 前文字削除 | BackSpace／Ctrl+H |
| 1文字削除 | Delete／Ctrl+G |
| 読みの入力誤り位置へジャンプ | Ctrl+J |
| カーソル前移動／後移動／先頭移動／末尾移動 | ←・Ctrl+K／→・Ctrl+L／Ctrl+←／Ctrl+→ |
| 情報ウィンドウ オープン/表示切替・クローズ・前ページ・次ページ | End／Shift+End／Shift+Ctrl+PageUp／Shift+Ctrl+PageDown |
| 電子辞典 部分一致検索 | Shift+Ctrl+End |
| スペルチェックAa展開 | Ctrl+A |
| 確定アンドゥ | Ctrl+BackSpace |
| 変換辞書切替メニュー | Shift+F8 |
| 注目文節コピー | Ctrl+C |
| ATOKダイレクト すべてのプラグイン／プラグインを指定 | Ctrl+Insert／Shift+Ctrl+Insert |
| （ほか: 日本語入力ON/OFF、メニュー、全入力文字メニュー、固定入力切替、カナロック、文字パレット、お気に入り文書） | 文字未入力と同じ |

入力中の Shift+Enter は出典で食い違う: [GIST34] は「全文確定」、[W36] は「自動表示候補確定」。[GIST34] の改変点の一覧にこのキーは無い。

#### 状態 3: 変換中（スペースで変換した直後。候補ウィンドウは未表示）

入力中の機能に加えて、次の機能が使える。

| 機能 | キー |
|---|---|
| 自動表示候補次移動 | Tab／Ctrl+↓ |
| 先頭1文字確定／末尾1文字確定 | PageDown／PageUp |
| 変換取消 | BackSpace／Ctrl+H |
| 全変換取消 | Insert |
| 注目文節削除 | Shift+Delete |
| 自動修復取消 | Shift+BackSpace |
| IVS選択ウィンドウ オープン/クローズ | Home |
| 文節区切り伸張／収縮 | →・Ctrl+L／←・Ctrl+K |
| ローマ字単位区切り伸張／収縮 | Shift+Ctrl+→／Shift+Ctrl+← |
| 文節前移動／後移動／先頭移動／最終移動 | Shift+←／Shift+→／Ctrl+←／Ctrl+→ |
| 単語削除 | Ctrl+Delete |

#### 状態 4: 次候補表示中（候補ウィンドウ表示中）

変換中とほぼ同じ機能に加えて、次の機能が使える。

| 機能 | キー |
|---|---|
| 変換/次候補 | スペース／Ctrl+↓ |
| 変換/前候補 | ↑／Ctrl+↑ |
| 次候補群表示／前候補群表示 | 変換／Shift+変換 |
| 次グループ移動／前グループ移動 | Tab・Ctrl+J／Shift+Tab |
| 先頭文字並べ替え／末尾文字並べ替え | Ctrl+PageDown／Ctrl+PageUp |
| 再変換別読み | Ctrl+Home |
| スペルチェックAa展開 | Ctrl+A |

[GIST34] では改変により Shift+スペースがカナ後変換になっている。既定の ATOK スタイルでは Shift+スペースは次候補 [W36][FAQ08]。

#### 状態 5: 全候補表示中

| 機能 | キー |
|---|---|
| 全候補次移動／前移動／次行移動／前行移動 | スペース・→／←／↓／↑ |
| 全候補選択確定／取消 | Enter・Ctrl+M／Esc・Ctrl+[ |
| 次候補群表示／前候補群表示／グループ移動／並べ替え | 次候補表示中と同じ |
| 後変換（F6〜F10、Ctrl+U/I/O/P/@）／辞書セット変換 | 入力中と同じ |
| 変換取消／全変換取消 | BackSpace・Ctrl+H／Insert |

[M-KEY]（Mac）と [FAQ08]（Windows 2008）では、全候補表示中に Ctrl+スペースも「全候補次へ移動」になっている。

#### 状態 6: 文節区切り直し中（←→で区切りを変えた状態）

| 機能 | キー |
|---|---|
| 変換/次候補 | スペース／Shift+変換 |
| 後変換・辞書セット変換 | 入力中と同じ |
| 全文確定／部分確定／1音確定 | Enter・Ctrl+M／↓・Ctrl+N／Shift+↓ |
| 変換取消／全文字削除 | BackSpace・Ctrl+H／Esc・Ctrl+[ |
| 読みの入力誤り位置へジャンプ | Ctrl+J |
| 文節区切り伸張／収縮 | →・Ctrl+L／←・Ctrl+K |
| ローマ字単位区切り伸張／収縮 | Shift+Ctrl+→／Shift+Ctrl+← |
| 確定アンドゥ | Ctrl+BackSpace |

#### 状態 7: 半角入力（直接入力に近い状態）

| 機能 | キー |
|---|---|
| 再変換 | Shift+変換 |
| 日本語入力ON/OFF | 半角／全角 |
| 確定アンドゥ | Ctrl+BackSpace |
| メニュー | Ctrl+F10 |
| 入力モード順次切替 | F10 |
| 漢字モード順次切替 | ローマ字 |
| 半角無変換固定入力(A)ON/OFF | 英数（改変） |
| カナロック | ひらがな |
| 文字パレット／お気に入り文書／見逃し指摘ビューア | Ctrl+F11 ほか |

#### 状態 8: 記号入力（記号入力モード。F10 で入る）

| 機能 | キー |
|---|---|
| 記号確定 | Enter |
| 記号次候補移動／前候補移動 | →・スペース／←・Shift+スペース |
| 記号次候補群表示／前候補群表示 | ↓・変換／↑・Shift+変換 |
| 記号次区点表示／前区点表示 | Tab／Shift+Tab |
| 記号先頭表示／外字先頭表示 | Home／Shift+Home |
| コード体系順次切替 | Shift+F7 |

[FAQ08]（ATOK 2008）の「記号操作」の表も同じ内容。

### 1.4 Windows 版と Mac 版の主な違い（ATOK スタイル）

| 機能 | Windows [W36] | Mac [M-KEY] |
|---|---|---|
| Shift+スペース | 次候補 | **前候補** |
| 次の候補群 | 変換 | option+スペース |
| 前の候補群 | Shift+変換 | option+shift+スペース |
| 再変換 | Shift+変換 | control+shift+Y |
| 連想変換 | Ctrl+Tab | control+A |
| 全角英字・半角英字（後）変換の名前 | 全角無変換（後）変換・半角無変換（後）変換（F9／F10） | 全角英字（後）変換・半角英字（後）変換（F9／F10） |
| 読みの英字／カナ置換 | F11 | control+;／F11 |
| 順次後変換 | （ATOK スタイルには無い。MS-IME スタイルでは無変換、Shift+無変換） | option+tab |
| 辞書セット変換 | F2〜F5、Shift+F6（Ctrl+数字は無い） | control+1〜5／F1〜F5、control+shift+6／shift+F6 |
| 先頭 1 文字を確定 | PageDown | page up／control+shift+N |
| 末尾 1 文字を確定 | PageUp | 資料に無い |
| 全変換取消／継続変換 | Insert（[FAQ08]・[GIST34]。[W36] の表には無い） | control+shift+J |
| 無学習全文確定 | 割付けなし [SOZOU] | option+return |
| 単語登録 | Ctrl+F7 | control+shift+E／control+F7 |
| 単語削除 | Ctrl+Delete | control+D／control+del |
| 情報ウィンドウ表示 | End | control+W／end |
| 入力文字種の直接切替 | 無変換・Shift+無変換・Ctrl+無変換・カタカナひらがな | control+shift+Z/X/V/B/C、かな／英数（＋shift/control） |
| 漢字／半角モード切替 | 変換 | option+スペース |
| ATOK ダイレクト | Ctrl+Insert／Shift+Ctrl+Insert（[FAQ08]・[GIST34]。[W36] の表には無い） | control+T／control+shift+T |
| ヘルプ／ATOK パレット表示 | 資料に無い | control+shift+H／control+shift+A |
| 環境設定 | Ctrl+F12 | control+shift+F／control+F12 |
| 見逃し指摘ビューア | Shift+Ctrl+F10 | control+shift+9／control+shift+F10 |
| IVS 選択ウィンドウ | Home | 資料に無い |
| スペルチェック Aa 展開 | Ctrl+A（[FAQ08]・[GIST34]） | 資料に無い |
| スピーチ／Spotlight／LogoVista | 資料に無い | control+shift+S／1／0 |

### 1.5 プリセット（スタイル）

| プラットフォーム | プリセット | 出典 |
|---|---|---|
| Windows | **ATOK**（ATOK スタイル）、**MS-IME**（MS-IME スタイル） | [W36 p.98, p.102]、[FAQ752] |
| Windows | 旧版では「ATOK 2011」のような版名付きのスタイル名で表示された。利用者が作ったものは「ユーザー」「ユーザー（ATOK ○○）」 | [FAQ349]、[FAQ752] |
| Windows | 「ATOK: ↓次候補←→文節移動」という名前がスタイル一覧にある。[KHYODA] にだけある | [KHYODA] |
| Mac | ATOK スタイル、macOS 標準風スタイル（旧ことえり風。ページ名は `ap_key_kotoeri.htm`）、egbridge 風スタイル、MacVJE-Delta 風スタイル、MS-IME 風スタイル | [M-STYLE]、[M-FN]、[M-OTHER] |

- 公式マニュアル [W36] が挙げる Windows 版のプリセットは ATOK と MS-IME の 2 つだけ。WXG 風・VJE 風などは現行の Windows 版の資料に無い。
- 初回は、スタートアップツールで「ATOK 標準のキー操作」か「Microsoft IME と同じようなキー操作」を選ぶ [W36 p.18]。
- MS-IME 風と ATOK 標準の違いは [FAQ041355] にもある。

#### Windows 版 MS-IME スタイルの主な差分 [W36 p.102–105]

**変換・確定・取消**

| 機能 | キー |
|---|---|
| 次候補 | スペース／変換／↓／Ctrl+X |
| 前候補 | Shift+スペース／Shift+変換／↑／Ctrl+E |
| 再変換 | 変換／Shift+変換 |
| 半角無変換（後）変換 | F10／Ctrl+T |
| 順次無変換後変換 | Shift+無変換 |
| 順次カタカナ後変換 | 無変換 |
| オプション辞書セット変換 | Ctrl+F5 |
| 一文字入力辞書セット変換 | F5 |
| 全文確定 | Enter／Ctrl+M／Ctrl+Enter |
| 部分確定 | Ctrl+↓／Ctrl+N |
| 変換取消 | Backspace／Ctrl+H／Esc／Ctrl+Z |
| 全文字削除 | Esc／Shift+Esc／Ctrl+Z |

**カーソル・文節**

| 機能 | キー |
|---|---|
| カーソルを前へ移動 | ←／Shift+←／Ctrl+S／Ctrl+K |
| カーソルをうしろへ移動 | →／Shift+→／Ctrl+D／Ctrl+L |
| カーソルを先頭へ移動 | Home／Ctrl+←／Ctrl+E／↑ |
| カーソルを末尾へ移動 | End／Ctrl+→／Ctrl+X／↓ |
| 文節の区切りを前へ移動 | Shift+←／Ctrl+K |
| 文節の区切りをうしろへ移動 | Shift+→／Ctrl+L |
| 注目文節を前へ移動 | ←／Shift+S |
| 注目文節をうしろへ移動 | →／Shift+D |
| 注目文節を先頭へ移動 | Ctrl+←／Home／Ctrl+A |
| 注目文節を末尾へ移動 | Ctrl+→／End／Ctrl+F |

「Shift+S」「Shift+D」は [W36] の表記のまま。

**候補ウィンドウ**

| 機能 | キー |
|---|---|
| 次の候補群 | PageDown／Shift+↓ |
| 前の候補群 | PageUp／Shift+↑ |
| 先頭候補へ移動 | Home |
| 最終候補へ移動 | End |
| 情報ウィンドウ表示 | Ctrl+End |
| IVS 選択ウィンドウ | Ctrl+Home |

**入力文字種の切替**

| 機能 | キー |
|---|---|
| 入力文字種（A／A）順次切替 | Shift+無変換 |
| 入力文字種（あ／ア／ｱ）順次切替 | 無変換 |
| 入力文字種 全角ひらがな（あ） | カタカナひらがな |
| 入力文字種 全角カタカナ（ア） | Shift+カタカナひらがな |

---

## 2. カスタマイズ

### 2.1 Windows 版: ATOK プロパティ（環境設定）→［キー・ローマ字・色］シート

**開き方** [W36 p.81]: Ctrl+F12、またはタスクバーの［あ］を右クリック →［ATOKメニュー］→［基本のメニュー］→［プロパティ（環境設定）］。

**シート構成** [W36 p.81–82]: ［入力・変換］［辞書・学習］［校正支援］［パレット］［キー・ローマ字・色］［電子辞典検索］［インターネット設定］。ボタンは［プロパティ登録編集］と［かんたん設定］（カスタム ATOK を起動する）。

**［キー・ローマ字・色］シート**

| 要素・操作 | 内容 | 出典 |
|---|---|---|
| ［スタイル一覧］ | ATOK、MS-IME、利用者のスタイルを並べた一覧。現在のスタイルには赤丸の印が付く | [FAQ349]、[CHIE] |
| ［スタイルの選択］ | 一覧で選んだスタイルを現在のスタイルにする | [FAQ349]、[XTECH] |
| ［キーカスタマイズ］ | 「ATOK キーカスタマイズ」ダイアログを開く | [FAQ349] |
| ［ローマ字カスタマイズ］ | ローマ字とかなの対応表を編集する | [KHYODA] |
| 色の設定 | 入力中・変換中の文字の色を設定する | [W36 p.81] |
| 保存 | プリセット（ATOK や MS-IME）を変えて［OK］を押すと、［スタイル名］の入力を求められ、**新しいスタイルとして保存される**。プリセットは上書きされない | [FAQ349] |
| ファイル出力 | キーカスタマイズのダイアログで［メニュー-テキストファイルに出力］→［キー設定のファイル出力］→ 保存先を指定して［実行］。形式は [GIST34] のようなテキストで、状態ごとに機能とキーを並べる | [FAQ349]、[GIST34] |
| 引き継ぎ | スタートアップツールで旧版のキー・ローマ字・色の設定を引き継ぐ。新しい版で追加された機能のキー割り付けを**マージ**するかを確認するメッセージが出る | [FAQ349] |
| アプリ別の切り替え | プロパティ関連付けツールで、アプリケーションごとに環境設定（プロパティ）を関連付ける | [W36 p.83] |
| ATOK Sync での同期 | スタイル名が「ATOK Sync 同期用スタイル」となっている例がある。公式に挙がる ATOK Sync One の同期対象は変換学習、確定履歴、登録単語、削除単語。スタイルが同期されるかは資料に無い | [GIST34]、§3.1 |
| スタイルファイルの実体 | レジストリの `HKEY_CURRENT_USER\Software\Justsystem\ATOK\34.0\Style\...` | [GIST34] |
| 取り込み | 出力した一覧はそのままの形式では取り込めない。別に、スタイルファイル（`IDCode=ATOKSTYLE32` 形式）でインポート／エクスポートできる | [AOUR] |
| 印刷 | 資料に無い。「テキストファイルに出力」はある | — |

**キーカスタマイズのダイアログ**

- 行が機能またはキー、列が 8 つの状態（§1.3）。下部の［キー(K)］［機能］で、どちらを行にするかを切り替える。
- セルをダブルクリックして機能を選ぶ。
- その状態に割り当てられない機能のセルはグレーで表示される。
- ［キーを検索］で、押したキーがどの機能に割り当てられているかを探す。
- 機能を選ぶダイアログに「変換中」「次候補選択表示中」のチェックボックスがあり、ほかの状態にも同じ割り当てを入れられる [KHYODA]。

このダイアログの記述の出典は [TERRA]、[KHYODA]、[AOUR]。ダイアログ、機能の全リスト、状態の定義を載せた Windows 版の公式資料は無い。

**割り当ての制限** [AOUR]

- 修飾キーとして使えるのは Shift と Ctrl の組み合わせだけ。Alt との組み合わせは定義できない。
- 文字キーは単独では割り当てられない。Mac ヘルプにも同じ記述がある [M-KINO]。

### 2.2 Mac 版: キー・ローマ字カスタマイザ

| 項目 | 内容 | 出典 |
|---|---|---|
| 起動 | 入力メニュー、ATOK パレット、ATOK メニューの［環境設定-キー・ローマ字カスタマイザ］ | [M-CU-START] |
| ［キー・ローマ字スタイル］一覧 | プリセット 5 種（§1.5）と利用者のスタイル。利用者のスタイルは一覧の下に追加される | [M-CU-RD] |
| ［キー設定］ | 左上で［機能］か［キー］を選び、一覧で「状態」を選んで［変更］を押す。キーは実際に押して指定するか、［一覧から選択］で選ぶ。キーを押して機能を探す［キーを検索］もある | [M-KINO]、[M-KEYKINO] |
| 割り当て済みの警告 | 「”☆☆(状態)＋××(キー)”は”△△(機能)”にすでに割り当てられています。設定を更新しますか？」と出る。更新すると前の割り当ては無効になる | [M-MSG] |
| ［他のスタイルから読み込み］ | ほかのスタイルのキー割り付けを一括で読み込む | [M-KEYSTYLE] |
| ［テキストファイルに出力］ | キー割り付けをテキストにする。表示中の［機能］／［キー］の切り替えに関係なく、全情報を出力する | [M-KEYFILE] |
| 複製・削除・名前変更 | 複製（コピーボタン）、削除（プリセットは削除できない）、［スタイル名の変更］（プリセットは変更できない）。スタイル名は 30 文字まで。ファイルは `StUser0.plist`〜`StUser24.plist`。スタイルの数の上限は資料に無い | [M-CU-RD]、[M-MSG] |
| ［スタイルコンバート］ | ATOK 2009 以降の旧版のスタイルファイルを変換する | [M-CU-RD] |
| ［ローマ字設定］ | ローマ字に対応するかなの変更・追加、特殊設定（shift キーで拗音・促音を入力する、ヘボン式撥音で MB/MM/MP を「ん」にする）、他のスタイルから読み込み、テキストファイルに出力 | [M-KANA] |
| プリセットの扱い | プリセットを変更すると、必ず新しいスタイルとして名前を付けて保存する。元のプリセットが現在のスタイルだった場合は、新しいスタイルが現在のスタイルになる | [M-KINO] |
| 他社風スタイルの注意 | 操作体系が違うので同じ操作を実現できない場合がある。ATOK のすべての機能が割り当てられているわけではない。「変更するときの土台として」使う | [M-CU-RD] |
| メニューでの表示 | メニューに出すショートカットとして、機能キー（F キーなど）と文字キーのどちらを優先するか選べる | [M-MENUKEY] |

他社風のスタイルへの切り替え方は [M-EVOTHER] にある。

### 2.3 ローマ字カスタマイズの仕様（Windows）[AOUR]

- 定義数の上限は概ね 550。MS-IME は 320 程度。
- 1 キーで入るかなを割り当てると、そのキーから始まる綴りは定義できない。
- `, . /` などの句読点キーには定義を割り当てられない。
- 子音の連打で促音になる規則と、NN で「ん」になる規則は、割り当てに関係なく働く（QWERTY ローマ字の規則に依存）。
- 同時打鍵の定義は資料に無い。

### 2.4 割り当てできる機能（コマンド）

公式の表（[W36]、[M-KEY]、[FAQ08]）と [GIST34]（エクスポート表記）に出てくる機能名を合わせた一覧。キーカスタマイズのダイアログにある機能の全リストは資料に無い。

#### 変換

- 変換/次候補、変換/前候補
- 推測変換（旧名: 省入力変換）
- 再変換、確定文字への復帰（読みへの復帰）、再変換別読み
- 連想変換
- ひらがな(後)変換、カタカナ(後)変換、半角(後)変換、全角無変換(後)変換（Mac は全角英字(後)変換）、半角無変換(後)変換（Mac は半角英字(後)変換）
- 順次無変換後変換、順次カタカナ後変換（MS-IME スタイル）、順次後変換（Mac）
- 読みの英字/カナ置換
- 継続変換(自動変換時)
- 辞書セット 0〜9 変換（Mac の MacVJE-Delta 風では辞書セット 6〜0 まで出てくる [M-FN]）
- 部首変換（[FAQ08] では Shift+F6。現行版では一文字入力辞書セットに統合）
- AMET1／AMET4、AMETメニュー（[FAQ08] のみ。旧機能）

#### 確定と取消

- 全文確定、部分確定、1音確定
- 自動表示候補確定（推測変換確定）、自動表示候補前移動、自動表示候補次移動、自動表示候補クローズ
- 無学習全文確定
- 先頭1文字確定、末尾1文字確定
- 変換取消、全変換取消

#### 編集

- 全文字削除、前文字削除、1文字削除、注目文節削除
- 読みの入力誤り位置へジャンプ
- 自動修復取消
- カーソル前移動、カーソル後移動、カーソル先頭移動、カーソル末尾移動
- 注目文節コピー

#### 文節

- 文節区切り伸張、文節区切り収縮
- ローマ字単位区切り伸張、ローマ字単位区切り収縮
- 文節前移動、文節後移動、文節先頭移動、文節最終移動

#### 候補

- 次候補群表示、前候補群表示
- 次グループ移動、前グループ移動
- 先頭候補へ移動、最終候補へ移動
- 先頭文字並べ替え、末尾文字並べ替え
- 情報ウィンドウ オープン/表示切替、情報ウィンドウ クローズ、情報ウィンドウ 前ページ移動、情報ウィンドウ 次ページ移動
- 電子辞典 部分一致検索
- スペルチェックAa展開
- IVS選択ウィンドウ オープン/クローズ
- 解説表示オン/オフ（[FAQ08]）

#### 全候補

- 全候補を表示、全候補次移動、全候補前移動、全候補次行移動、全候補前行移動、全候補選択確定、全候補選択取消

#### 記号入力

- 記号確定、記号次候補移動、記号前候補移動、記号次候補群表示、記号前候補群表示、記号次区点表示、記号前区点表示、記号先頭表示、記号外字先頭表示、コード体系順次切替

#### モード

- 日本語入力ON/OFF、日本語入力ON、日本語入力OFF
- 入力モード順次切替
- 漢字／半角モード切替
- 漢字モード順次切替
- 固定入力英字順次切替、固定入力カナ順次切替
- 半角無変換固定入力(A)ON/OFF
- 英語入力モード オン/オフ
- カナロックON/OFF（カナ入力切替）
- 入力文字種(あ／ア／ｱ)順次切替、入力文字種(Ａ／A)順次切替、入力文字種(あ／Ａ)順次切替
- 入力文字種 全角ひらがな、入力文字種 全角カタカナ
- Mac のみ: ひらがな／カタカナ／全角英字／半角英字／英字入力文字種、全角／半角文字切替、固定入力オン/オフ
- 推測候補モード オン/オフ（[FAQ08]）

#### ツールの起動

- 単語登録、単語削除
- 確定アンドゥ、確定リピート
- メニュー（ATOK メニュー）、全入力文字メニュー（入力文字種切替メニュー）、変換辞書切替メニュー
- 文字パレット
- プロパティ（環境設定）
- お気に入り文書メニュー、お気に入り文書リピート
- 校正支援 見逃し指摘ビューア
- ATOK MiRA
- ATOK ダイレクト（すべてのプラグイン／プラグインを指定／プラグイン 1〜5）
- Mac のみ: ヘルプ、ATOK パレット表示、LogoVista で検索、Spotlight で検索、スピーチで英文読み上げ

### 2.5 第三者の評価

- [KHYODA]: カスタマイズ項目が多い。Google 日本語入力の操作感は完全には再現できない。
- [TERRA]: 同じ機能を状態ごとに設定する。無変換キー 1 つのために 6 状態を個別に設定している。

---

## 3. 機能一覧

### 3.1 入力・変換の機能

| 分類 | 機能 |
|---|---|
| 推測・省入力 | 推測変換（以前の入力と省入力データから候補を出す。Tab／↓で候補ウィンドウに切り替え、Shift+Enter で先頭を確定）、省入力データ（標準、慣用表現、英語など）、確定のリピート、お気に入り文書、ATOK＠ブンコレ、定型文書入力 |
| 変換補助 | 連想変換「類語ファインダー」、専門用語変換辞書（F2〜F4 の辞書セット）、郵便番号から住所、町名から住所、人名辞書、カタカナ語英語辞書、日本語英語辞書、部首変換、文字コード辞書、記号辞書、顔文字、IVS 辞書、日付入力（「きょう」「いま」などのキーワードから変換、日付形式の候補、日付入力パレット） |
| 表現モード | 話し言葉（関西、北海道東北、関東、中部北陸、中国四国、九州）、文語。入力内容によって自動で切り替わる |
| 校正支援 | 同音語の誤り、くだけた表現、誤りやすい表現、読み・仮名遣いの誤り、慣用句の誤り、助詞の連続などを指摘する。見逃し指摘ビューア。クラウド文章校正もある |
| 入力ミスの修正 | 自動修復（入力ミスを自動で直す。自動修復取消は Shift+Backspace）、訂正学習、付属語の入力ミスの訂正、修復強度の調整 |
| 英語入力の支援 | 英語入力モード（Caps Lock英数、Shift+文字キー）、英単語の推測、スペルチェック（Aa 展開）、英単語のつづりからカタカナ語への変換（Mac） |
| 学習 | ATOK インサイト（一時文書学習）、文書学習ツール、RSS・Atom からの単語登録、プライバシーモード、プロテクトモード（オンライン会議中は推測候補を出さない） |
| パレット・UI | ATOK パレット、文字パレット、手書き文字入力（**Windows のみ**。Mac は非搭載 [SPEC]）、クリックパレット、顔文字パレット（Mac）、候補ウィンドウのデザイン切替（クラシック、ダークモード向けなど。表示倍率 100〜400%）、ATOK アトカラ（通知） |
| 辞書を引く | ATOK 連携電子辞典（変換中に End で情報ウィンドウ）、ATOK イミクル（閲覧中の文章の語の意味を調べる）、クラウド辞典（広辞苑 第七版、大辞林、ウィズダム英和／和英、故事ことわざ・慣用句辞典、敬語のお辞典） |
| 連携 | ATOK ダイレクト（プラグインで Web サービスや外部アプリと連携）、URL トリガー変換（Mac）、8 カ国語クラウド翻訳変換、ATOK ナントカ変換（後半しか思い出せない語を変換）、クラウド推測変換（237 万語） |
| 生成 AI | **ATOK MiRA**: 入力中・選択中の文章を生成 AI で書き換える。「わたしらしく」をオンにすると、普段の入力傾向を反映する。Windows は 2026-02、Mac・iOS・Android は 2026-06 に提供開始。キーは Shift+Ctrl+M |
| 同期 | **ATOK Sync One**（2026-09 に ATOK Sync AP を置き換え）: 変換学習、確定履歴、登録単語、削除単語を 4 つの OS で同期する。ATOK キーワード Express（新語の配信）。ATOK My Passport |
| 設定の管理 | プロパティ関連付けツール（アプリ別の設定）、カスタム ATOK（質問に答える形の設定）、環境のバックアップ、辞書ユーティリティ |

出典: [W36] 目次（p.3–5）と本文、[FEAT]、[PLAN]、[SPEC]。

### 3.2 プランと動作環境

- プラン: ATOK Passport プレミアムのみ。月 660 円、年 7,920 円（いずれも税込）[PLAN]。
- 利用できるアプリ: Windows、Mac、「ATOK for Android [Professional]」、「ATOK for iOS [Professional]」。台数は最大 10 台 [W36 p.2]。
- Windows 版 Tech Ver.36: Windows 11 のみ（x64 と Arm64 のネイティブ）。Windows 10 以前にはインストールできない [SPEC]。
- Mac 版: macOS 14〜27 [SPEC]。

### 3.3 入力方式

- 「ローマ字漢字入力（R漢）」と「カナ漢字入力（カナ漢）」の 2 つ [M-MODE]。
- カナ漢字入力は、キーボードに書かれているかなの配置（JIS かな）に従う。
- ローマ字表は変えられ、AOUR 配列などの独自配列をローマ字テーブルで作れる [AOUR]。ローマ字テーブルの仕様は §2.3。

### 3.4 親指シフト（NICOLA）

| 項目 | 内容 | 出典 |
|---|---|---|
| 公式の対応 | 公式 FAQ が親指シフトに触れているのは DOS 版 ATOK8（CONFIG.SYS に `OYAYUBI.UCF` を書く）だけ。現行の Windows 版・Mac 版の親指シフト対応は資料に無い（[W36] にも Mac 版のヘルプにも無い） | [FAQ012324]（1999 年） |
| 現行版での使い方 | 親指シフトのエミュレータ（やまぶき、やまぶきR、親指ひゅんQ、DvorakJ など）が親指シフトの打鍵を JIS かなまたはローマ字の打鍵に変換して ATOK に渡す。エミュレータ側と IME 側の両方で切り替えが要る | [OKWAVE]、[NIXE]、[OYAYUBI] |

---

## 出典

| 略号 | 資料名 | URL |
|---|---|---|
| W36 | ATOK for Windows 基本的な使い方（公式 PDF、©2026、Tech Ver.36 相当）。キー一覧 p.98–105、文節 p.47、候補 p.48–50、設定 p.81–83、表記 p.2 | https://atok.com/other/support/howtouse/windows/atok36w.pdf |
| M-KEY | ATOK for Mac ヘルプ「キーの機能一覧：ATOKスタイル」 | https://atok.com/other/support/howtouse/mac/ap/pgs/ap_key.htm |
| M-FN | ATOK for Mac ヘルプ「ファンクションキーに割り当てられている機能」 | https://atok.com/other/support/howtouse/mac/ap/pgs/ap_key_function.htm |
| M-STYLE | ATOK for Mac ヘルプ（スタイルファイル） | https://atok.com/other/support/howtouse/mac/shrd/shrd_stylefile.htm |
| M-OTHER | ATOK for Mac ヘルプ（他社風スタイルのキー一覧） | https://atok.com/other/support/howtouse/mac/ap/pgs/ap_key_kotoeri.htm ／ ap_key_egbridge.htm ／ ap_key_vje-d.htm ／ ap_key_msime.htm |
| M-EVOTHER | ATOK for Mac ヘルプ（他社風にする） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_ev_other.htm |
| M-CU-RD | ATOK for Mac ヘルプ（キー・ローマ字カスタマイザ） | https://atok.com/other/support/howtouse/mac/mn/pgs/mn_tool_custom_r_d.htm |
| M-CU-START | ATOK for Mac ヘルプ（カスタマイザの起動） | https://atok.com/other/support/howtouse/mac/shrd/shrd_custom_start.htm |
| M-KINO | ATOK for Mac ヘルプ（キーに機能を割り当てる） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_key_kino.htm |
| M-KEYKINO | ATOK for Mac ヘルプ（機能にキーを割り当てる） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_kino_key.htm |
| M-KEYSTYLE | ATOK for Mac ヘルプ（他のスタイルから読み込み） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_key_style.htm |
| M-KEYFILE | ATOK for Mac ヘルプ（テキストファイルに出力） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_key_file.htm |
| M-KANA | ATOK for Mac ヘルプ（ローマ字設定。ev_kana_shift.htm、ev_kana_n.htm、ev_kana_file.htm、ev_kana_style_new.htm も） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_kana.htm |
| M-MSG | ATOK for Mac ヘルプ（カスタマイザのメッセージ） | https://atok.com/other/support/howtouse/mac/ap/pgs/ap_msg_cu.htm |
| M-MENUKEY | ATOK for Mac ヘルプ（メニューのショートカット表示） | https://atok.com/other/support/howtouse/mac/ev/pgs/ev_menu_key.htm |
| M-UNDO | ATOK for Mac ヘルプ（確定のアンドゥ） | https://atok.com/other/support/howtouse/mac/cr/pgs/cr_undo.htm |
| M-MODE | ATOK for Mac ヘルプ（入力方式） | https://atok.com/other/support/howtouse/mac/bs/pgs/bs_basic_mode.htm |
| FAQ08 | ジャストシステム FAQ 040816「ATOK標準のキー操作」（ATOK 2008、2008-02-08 更新。ATOK 2007 版は QID=032743） | https://support.justsystems.com/faq/1032/app/servlet/qadoc?QID=040816 |
| FAQ349 | ジャストシステム FAQ 050349 | https://support.justsystems.com/faq/1032/app/servlet/qadoc?QID=050349 |
| FAQ752 | ジャストシステム FAQ 050752 | https://support.justsystems.com/faq/1032/app/servlet/qadoc?QID=050752 |
| FAQ041355 | ジャストシステム FAQ 041355（MS-IME 風と ATOK 標準の違い） | https://support.justsystems.com/faq/1032/app/servlet/qadoc?QID=041355 |
| FAQ012324 | ジャストシステム FAQ 012324（ATOK8 と親指シフト、1999） | https://support.justsystems.com/faq/1032/app/servlet/qadoc?QID=012324 |
| GIST34 | 利用者による Windows 版 ATOK 34.0（レジストリパス `ATOK\34.0`）のキーカスタマイズのエクスポート（2022-02、ATOK スタイルを改変） | https://gist.github.com/takatakata/c31ac544e09283d777fa1e82c8c248fb |
| TERRA | terraconti.jp（ATOK Tech Ver.32、無変換キーの状態別設定） | https://terraconti.jp/atok-muhenkan/ |
| KHYODA | k-hyoda.hatenablog.com（個人ブログ、2024-12-08） | https://k-hyoda.hatenablog.com/entry/2024/12/08/163325 |
| AOUR | aourkbd.net（ATOK のカスタマイズ） | https://aourkbd.net/hasei/atokcustom.html |
| SOZOU | so-zou.jp（ATOK のショートカット） | https://so-zou.jp/software/usage/ime/atok/shortcut/ |
| CHIE | Yahoo! 知恵袋の回答 | URL 無し |
| XTECH | 日経 xTECH | URL 無し |
| SPEC | ATOK 動作環境 | https://atok.com/info/spec.html |
| FEAT | ATOK 機能紹介 | https://atok.com/features/ |
| PLAN | ATOK プラン | https://atok.com/plan/ |
| OKWAVE | OKWAVE（親指シフトのエミュレータ） | https://okwave.jp/qa/q5974506.html |
| NIXE | nixeneko ブログ（親指シフトのエミュレータ） | https://nixeneko.hatenablog.com/entry/2015/01/08/002200 |
| OYAYUBI | oyayubi.fan.coocan.jp（ローマ字から NICOLA への移行） | http://oyayubi.fan.coocan.jp/oya/switching_from_romaji_to_nicola.html |
