# yuragi_tip（TSF テキストサービス、DESIGN「TIP」）

他人のアプリの中で動く DLL（`yuragi_tip.dll`。32 ビットのアプリ用に同じソースを x86 でビルドした `yuragi_tip32.dll`）。**できることを減らしてある**: 打鍵をブローカーへ送り、
返事を画面に書く。それだけ。Python を起動せず、再試行せず、ファイルを持たない。
起動してよいのはブローカーだけで、条件は DESIGN「ブローカーを起動する条件」の 3 つ。

| ファイル | 中身 |
|---|---|
| `yuragi_tip.cpp` | TSF とのやりとり（キー、変換中の文字の描画、表示属性、候補ウィンドウ、言語バー、トグル）と、ブローカーとの接続（`BrokerLink`） |
| `tip_logic.h` | TSF に依存しない判断: 返事の読み取り（知らない項目は無視、無い項目は既定値）、食べるかどうか、返事の順序、状態と表示 |
| `tip_json.h` | 小さな JSON 解析器（ブローカーと共有） |
| `default_keymap.h`（ビルド時に生成） | 同梱の `ms-ime.json` から作る食べる表（`python -m yuragi.ime.keymap`）。ブローカーから表が届くまで使う。ビルドに Python が要る |
| `yuragi_tip.rc` `resource.h` | 製品アイコン（`assets/icon/yuragi.ico`）を DLL に持たせる。登録時に `RegisterProfile` がこの DLL とリソース番号を渡し、入力方式の切り替え一覧に出る。言語バーの「ゆ/Y」は実行時に描くモード表示で、これとは別 |
| `tests/tip_logic_test.cpp` `tests/tip_json_test.cpp` | 上の 2 つの単体試験（どの OS でも動く） |
| `tests/mingw/ctffunc.h` | Linux で llvm-mingw を使って型検査するときだけの補い（製品のビルドでは使わない） |

設定ファイルは `%USERPROFILE%\.yuragi-ime\tip.json`。各項目の既定値を示す。

```json
{"toggle_vk":192,"toggle_mods":["alt"],"log":false,"log_text":false,"document_context":true}
```

`document_context` を `false` にすると、文書の左文脈の読み取り、確定位置の監視、打鍵への文脈情報の付加を停止する。
`log` を有効にすると、本文を含めずに文書取得とキー処理の経過時間を `%TEMP%\yuragi_tip.log` に記録する。

ビルドと試験は [DEVELOPMENT.md](../../docs/DEVELOPMENT.md)。
