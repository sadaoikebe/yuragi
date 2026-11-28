# macOS の入力プログラム

InputMethodKit の入力プログラム（`Yuragi.app`）。方針は [docs/MACOS.md](../../docs/MACOS.md)。
アプリから打鍵を受け取り、子プロセスのエンジン（`yuragi.engine`）に 1 行 1 JSON で送り、返事のとおりに変換中の文字を描いて確定する。

| ファイル | 中身 |
|---|---|
| `main.swift` | 起動。`IMKServer` を作り、エンジンの見張りを始める |
| `Controller.swift` | 入力欄ごとのコントローラ。打鍵を食べるかの判断、要求、返事の反映、変換中の文字、確定、予測の問い合わせ、文書の左文脈、入力メニュー（「設定を開く」「もう一度試す」） |
| `Candidates.swift` | 候補窓と小さな表示。フォーカスもクリックも取らないパネル |
| `Engine.swift` | エンジンの子プロセスとその見張り、設定ウィンドウの起動（`engine.json` の `admin_args`）。起動（`engine.json`）、行の読み書き、終了の検知、見張りのタイマー、返事を待つ。起動し直すか・止めるかの判断は `src/broker/broker_core`（DESIGN「見張り」） |
| `Peers.swift` | 設定ウィンドウとの通信口。この利用者だけが開ける Unix ソケット（`~/Library/Application Support/yuragi-ime/broker.sock`）。相手は `yuragi/ime/broker_client.py` |
| `KeyTap.swift` | イベントの監視。押下の実際の時刻と解放を採り、起きた順にエンジンへ渡す |
| `Keys.swift` | macOS のキーコードから、エンジンが使う Win32 の仮想キーへの表（US キーボード） |
| `logic.h`・`logic.mm` | `src/tip/tip_logic.h` の判断（返事の解釈、食べる表）と `broker_core` の見張りを Swift から使うための層 |
| `Log.swift` | `~/Library/Logs/yuragi-ime/input.log` |
| `ctl.swift`・`icon.swift` | 入力ソースの登録・有効化・選択の道具、メニューバーのアイコンを作る道具 |
| `build.sh`・`dev-install.sh`・`dev-uninstall.sh` | ビルド、開発用のインストールと削除 |
| `dev-identity.sh` | この Mac だけの署名「Yuragi Dev」を専用のキーチェーンに作る（1 回）。あれば `build.sh` が使い、無ければ簡易の署名になる |

## 開発用に入れる

[DEVELOPMENT.md](../../docs/DEVELOPMENT.md) の macOS の開発環境（`.venv`、辞書、モデル）を用意してから:

```sh
src/mac/dev-install.sh        # ビルドし、~/Library/Input Methods/Yuragi.app に置く。エンジンはこの作業ツリーから動く
src/mac/dev-uninstall.sh      # 消す。利用者のデータ（~/.yuragi-ime）と記録は残す
```

- 先に `src/mac/dev-identity.sh` を 1 回動かす。簡易の署名のままだと、ビルドのたびに「入力監視」の許可が外れる（MACOS.md §6.2）。
- 初回だけ、「入力監視」の許可を求める表示で Yuragi を許可する。許可すると OS が入力プログラムを起動し直す。
- 初回だけ、システム設定 > キーボード > 入力ソース > 編集 > ＋ > 日本語 で「Yuragi」を追加する（MACOS.md §6.3）。入れ直しでは要らない。
- エンジンの起動のしかたは `~/Library/Application Support/yuragi-ime/versions/dev/engine.json`（形は `src/broker/support.h`）。`DATA_DIR=<フォルダ> src/mac/dev-install.sh` で、エンジンのデータの場所を利用者のもの（`~/.yuragi-ime`）から変えられる。
- 記録は `~/Library/Logs/yuragi-ime/` の `input.log`（入力プログラム）と `engine.log`（エンジンの標準エラー）。打った内容は書かない。同じフォルダに `debug` という名前のファイルを置いている間だけ、打鍵のキーコードを書く。
- 設定ウィンドウは、入力メニューの「設定を開く」か、`.venv/bin/python -m yuragi.ime.admin_ui`。2 つめを起動すると、開いている窓が前に出る（`<データの場所>/admin.lock`）。
- 見張りの確認: `pkill -f yuragi.engine`（起動し直す。3 回続けると止まる）、`pkill -STOP -f yuragi.engine` のあと 1 キー打つ（5 秒で終わらせて起動し直す）。`input.log` に出る。
- 合成したキーでの確認: `tools/keyprobe/mac/out/probe app io.github.yuragi.inputmethod.Yuragi.Japanese "wlhosdke {Space} {Return}" | python3 tools/keyprobe/mac/summary.py`（入力欄に「開発してきた」が入る）。先に入力ソースを選んで、`input.log` に `engine ready` が出るのを待つ。

## 注意

| 規則 | 理由 |
|---|---|
| 入力プログラムのプロセスは、ほかの入力ソースを選んでから止める | 選ばれている間に止めると、動いていたアプリは開き直すまでつながらない（MACOS.md §4.2）。`dev-install.sh` はこの順で行う |
| エンジンへの書き込みは `write(2)` で行い、`SIGPIPE` を無視する | エンジンが消えていても、入力プログラムは落とさない |
| 見張りが入力欄へ送る行は、見張りの呼び出しが戻ってから配る（`Engine.call`） | 配った先が次の要求を出すと、見張りの処理の途中に入り直す |
| エンジンの終了は、標準出力を読み切り、プロセスが終わってから見張りに伝える | 終了コード（75 は起動し直しの依頼）が要る。古いエンジンの行が新しいエンジンの行に混ざらない |
| 食べたキーで何も表示しないときは、文書の長さが 0 のアプリに限り、ゼロ幅の空白を変換中の文字として置く | Chromium 系は、変換中の文字も挿入も無いと、キーの文字を自分で入れる（MACOS.md §6.4） |
| 解放は、それより前の押下が `handle` に届くまでエンジンに送らない（`KeyTap.swift`） | イベントの監視は押下を InputMethodKit より先に見る。解放を先に送ると、エンジンに届く順序が実際と変わる |
| 入力メニュー（`menu()`）は、項目の無いメニューを返さない | 空のメニューを返すと、変換中の文字が変わるたびに OS が入力を打ち切る（`commitComposition` が呼ばれ、文字は入らない） |
| キーの返事は `KEY_BUDGET_MS`（200 ミリ秒）まで待ち、間に合わなければ食べる | アプリは `handle` の返事を待って止まる |

## まだ無いもの

- 食べると答えたあとで、エンジンが「食べない」と返したキーをアプリへ渡し直すこと。いまは記録して捨てる（MACOS.md §8）。
- 返事の `global` のうち、メニューを開くものと、別のキーをアプリに送るもの（`send_*`）。
- キーボードの種類。
- 変換が止まったときの OS の通知。いまは記録と、次にかなを打ったときの小さな表示、入力メニューの「もう一度試す」。
