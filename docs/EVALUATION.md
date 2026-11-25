# 変換の評価と診断

リポジトリ直下で実行する。評価の道具は標準ライブラリだけで動き、学習履歴・個人辞書・LM を使わない
（LM を使う変換の時間は、下の「LM を使う変換の応答時間」のとおりエンジンで測る）。

```sh
python3 -m tools.eval.fetch_mozc_dict          # 初回のみ。Mozc OSS 辞書（git には入れない）
python3 -m tools.eval.run_regression           # 回帰ゲート
python3 -m tools.eval.run_mozc_eval --details /tmp/mozc-results.jsonl
python3 -m tools.eval.run_mozc_eval --unambiguous
python3 -m tools.eval.classify_mozc_errors --output /tmp/mozc-errors      # Mozc 評価の失敗の分類（新しい空のフォルダに出す）
python3 -m tools.replay_stage1 <ログ>          # 実打鍵ログの再生と採点（下の「実打鍵の記録」）
```

回帰ゲート（`run_regression`）は、変換を変えたら必ず通す 5 項目（amb の打鍵）: 「おはよう」と「どうぞ」の
1-best がそのままの表記になる、「どうぞ」の n-best（k=8）に王族・翁が出ない、「きどく」の n-best（k=8）に
既読と記憶の両方が残る、「きどくにない」の n-best（k=8）に既読にないと記憶にないの両方が残る。

条件の呼び方:

- **una**: 読みが分かっている（各文字を単独面・既知の面のトークンにする）。
- **amb**: 親指面は左右不明（`AmbShift`）。実打鍵の FSM は通さない、理想の打鍵。

連接表の全 0 行へのペナルティと環境変数 `ZERO_ROW_PENALTY` は [CONVERSION.md](CONVERSION.md) の「変換」。

辞書キャッシュは `data/cache/` に作る。名前は辞書マニフェストのハッシュとキャッシュ形式で決まり、
変わったら初回だけ辞書テキストから作り直す。

## Mozc の評価（`run_mozc_eval`）

Mozc OSS 辞書に付く `evaluation.tsv` を使う。

- 読み一致・表記一致: 1-best の読み／表記が TSV の正解と一致するか。
- コマンド基準: TSV の 4〜5 列目の指示で合否を出す。3 列目は Mozc の実出力で、正解とは限らない。
  `Mozc recorded pass` は TSV の status 列の集計で、Mozc を実行した値ではない。
  - `Conversion Expected [N]`: 1-best を先頭に置き、n-best の表記を重複除去して補った上位 N 件に
    引数の全文があるか（省略時 N=1）。文全体の候補による**近似**で、Mozc 本来の文節候補の順位和とは異なる。
  - `Conversion Match`: 1-best に引数の部分文字列があるか。`Not` は判定を反転する。
  - `Suggestion` などは対象外として件数を出す。入力できない読みも別に出す。
- 読みのかなは NICOLA の表で、「。」「！」など IME が 1 字の記号として打つものはその記号のまま入れる。半角の英数字を含む読みは入力できない読み。
- `--details` は入力できる各行の `PASS` / `FAIL` / `SKIP` を JSONL に出す。

単語の全候補を調べるときは `nbest_tokens(..., k=十分大きな値)`（CONVERSION.md の「n-best」）。

## 文節境界の差分（`compare_bunsetsu`）

同じ辞書 1-best の語列で、各自立語の頭で区切った境界と、文節の境界（複合語をまとめる。CONVERSION「区切り」）を比べる。
境界が変わった行だけを、自立語ごとの区切り・文節の順で出し、集計には対象全体の文節数を含める。
入力は既定で `evaluation.tsv` の読み。`--readings` で UTF-8 のかな列を 1 行 1 文ずつ指定できる。

```sh
python3 -m tools.eval.compare_bunsetsu --output bunsetsu-diff.tsv
python3 -m tools.eval.compare_bunsetsu --readings kana.txt --output own-bunsetsu-diff.tsv
```

## 標準入出力のサーバ（試験と診断）

`python3 -m yuragi.ime.server` は 1 セッションを標準入出力の 1 行 1 JSON で動かす
（返事の項目は [DESIGN.md](DESIGN.md) の「通信」）。辞書の読み込み直後に `gc.freeze()` する。
標準エラーへの本文のログは既定で出さない。診断が要るときだけ `--log-text`。
処理できない例外は、本文を含みうるメッセージを出さず、例外の型だけを報告する。
LM の時間は `--lm-timing` で標準エラーに出る（本文は出さない）。

操作の記録（トランスクリプト）は `tests/transcripts/`（形式と試験が確かめる範囲は同じフォルダの README）。

## LM を使う変換の応答時間

エンジンの `--lm-timing` はジョブの実行可能・開始・完了・結果採用の時刻を記録する。実行可能から開始までが
キュー待ち、開始から完了までが推論処理時間。TIP は `tip.json` の `log` を有効にすると、打鍵要求・応答・候補窓の
表示時刻を `%TEMP%\yuragi_tip.log` に記録する。Space から初回応答（変換の表示）までを測る。候補窓は 2 回目の Space で出るので、その表示までは 2 回目の Space から測る。
接続を増やす場合は、変換中に別接続から送った打鍵の応答時間も測る。

## 実打鍵の記録と再生

ノート PC の標準キーボード（横長の Space 1 本）で、実際のキーイベントからトークンの正解率を測る。
記録は辞書・変換器・学習を使わない。TIP の登録も要らない。

### 記録（Windows）

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
python -m yuragi.ime.host_win32 --record "data\recordings\stage1-$stamp.jsonl"
```

- 既存のファイルには書かない（新しいファイル名で記録する）。お題は `data/stage1/prompts.json`
  （自作の 40 文。同音語・句読点・数字を含む）。`--prompts` で替えられる。
- 記録窓に、お題と「入力する読み」が出る。**普段の速度で、打ち直さずに**、表示した読みを NICOLA で打つ。
  「、」は `[` 単独、「。」は Q 単独、「？」は Space + 1。誤打してもそのまま最後まで打つ。
- 文を打ち終えたら、**全キーを離して F12 を押して離す**と次の文へ進む（Fn が要る機種もある）。
  他のキーが押されたままなら進まない。
- フォーカスを別の窓へ移すと、その文は `interrupted` になり採点から外れる。窓へ戻ると次の文へ進む。
- 記録はこの窓が受けたイベントだけ（グローバルなキーフックではない）。
- ログと採点レポートは、お題の本文と打鍵列を含む。`data/recordings/` は git に入れない。

### 再生と採点（どの OS でも）

```sh
python3 -m tools.replay_stage1 data/recordings/stage1-YYYYMMDD-HHMMSS.jsonl --report /tmp/stage1-report.json
python3 -m tools.replay_stage1 tests/fixtures/stage1_synthetic.jsonl --json   # 機械可読のレポートを標準出力へ
```

- `tests/fixtures/stage1_synthetic.jsonl` は手で書いた合成の記録。1 文に 1 つずつ、誤りの無い打鍵、下の表の
  失敗の型、余分・欠落、Backspace と Enter を入れてある（文の id がその名前）。
- 完了した文ごとに新しい `ChordFsm` へキーを時刻順に渡す。各イベントの前に期限の来たタイマーを発火し、
  **期限と同じ時刻のキーよりタイマーを先に処理する**。仮想時計による決定的な再生で、Win32 のタイマー配送の
  遅れは再現しない。
- 期待するトークン列は、ログの `reading` と `data/nicola_a.json` から逆引きする。単独面は `Plain(key)`、
  親指面は `AmbShift(key)`。複数の面にある文字は単独面を優先する。「、」は `[` のキーの `Plain`。
  数字は半角・全角ともその数字キーの `Plain`。対応の無い文字はエラーにする。
- **トークン正解率** = `max(0, 1 - (S + D + I) / N)`（N = 期待トークン数、S/D/I = 置換・欠落・余分、各 1）。
  全完了文の N と誤り数を合算して計算する（文ごとの率の平均ではない）。一致数も別に出す。
- `ThumbTap`（Space 単独）は採点から外す（`raw_tokens` と `thumb_taps` には残す）。Backspace・Enter・Esc は
  回数だけ数え、過去のトークンを消さない。
- 失敗は編集 1 件ごとに次の型に分ける（**推定であり、物理的な原因の断定ではない**）:

| キー | 条件 |
|---|---|
| `thumb_overlap_shift_loss` | 期待 `AmbShift(k)` → 実 `Plain(k)`。押下時に Space が押されたままで、その押下が先の `AmbShift` に使われている |
| `unintended_chord` | 期待 `Plain(k)` → 実 `AmbShift(k)` |
| `missed_chord` | 期待 `AmbShift(k)` → 実 `Plain(k)` で、上の条件を満たさない |
| `other` | 異なるキーへの置換、挿入、欠落、その他 |

- `interrupted` / `incomplete` の文は一覧を出して外す。壊れた JSON・不正な型・時刻の逆転・文 ID の
  不整合・途中で切れた最終行は、行番号つきのエラー（終了コード 2）。採点できる文が 0 なら率は `null`、
  終了コード 1。

### ログの形式（`yuragi.stage1.v1`）

UTF-8、1 行 1 JSON オブジェクト。全行に `type` と `ms` がある。`ms` は QPC 起点からの非負の整数ミリ秒で、
単調非減少（`floor((QPC_now - qpc_origin) * 1000 / qpc_frequency)`）。窓がメッセージを処理した時刻で、
キーの接点の時刻ではない。

| type | 追加の項目 |
|---|---|
| `session` | `schema`、`clock="QPC"`、`time_unit="ms"`、`qpc_frequency`（tick/秒）、`qpc_origin`（起点 tick）、`layout="NICOLA-A"`、`keyboard="single-space-laptop"`、`next_prompt_vk`（123 = F12）、`comma_key`（「、」のキー。`"["`）、`prompt_count` |
| `prompt_start` | `id`、`text`（表示文）、`reading`（入力する読み。句読点と数字を含む） |
| `key` | `id`（対象の文）、`vk`（Win32 VK、0〜255）、`action="down"` / `"up"` |
| `prompt_end` | `id`、`status="complete"` / `"interrupted"` / `"incomplete"`、`event_count`、`held_vks`（終了時に押されていたキー） |
| `focus` | `focused`（真偽値） |
| `session_end` | `reason="complete"` / `"window_closed"` |

```jsonl
{"type":"session","ms":0,"schema":"yuragi.stage1.v1","clock":"QPC","time_unit":"ms","qpc_frequency":10000000,"qpc_origin":123456789,"layout":"NICOLA-A","keyboard":"single-space-laptop","next_prompt_vk":123,"comma_key":"[","prompt_count":40}
{"type":"prompt_start","ms":0,"id":"daily-01","text":"おはよう、今日は少し早く起きた。","reading":"おはよう、きょうはすこしはやくおきた。"}
{"type":"key","ms":500,"id":"daily-01","vk":32,"action":"down"}
{"type":"key","ms":520,"id":"daily-01","vk":74,"action":"down"}
```

F12 自身の down/up も当該文の `key` として残り、離したあとに `prompt_end` → 次の `prompt_start` が同じ時刻で
並ぶ。最後の文の後は `session_end`。1 ファイル 1 セッションで、行ごとに追記して flush する。

記録の中核は `yuragi/ime/recording.py`、表示と QPC・Win32 のメッセージ処理は `yuragi/ime/host_win32.py`、
再生と採点は `tools/replay_stage1.py`。レポートの形式は `yuragi.stage1.report.v1`。

> **注意**: 実打鍵ログの失敗の型だけを見て、FSM のタイミング定数（`TIMEOUT_MS`・`OVERLAP_MS`）を変えない。
> 型は期待と実際のトークンの差から推定したもので、打ち手の読み違い・打ち間違いと判定の誤りを区別しない。
> 定数を変えるときは、その型の文の打鍵の時刻（Space と文字の down・up の間隔）を見て、判定がどの出口で分かれたかを確かめる。
