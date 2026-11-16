# yuragi-broker（REDESIGN §5）

サインインごとに 1 つ動く小さな常駐プログラム。変換エンジン（`python -m yuragi.engine`）を
起動・見張り・落ちたら起動し直し（10 分に 3 回落ちたら止める）、TIP からの打鍵を名前付きパイプで受けて
エンジンへ渡す。エンジンが使えない間の打鍵は預からない（TIP がアプリへ素通しにする）。止まったら 1 回だけ通知する。

| ファイル | 中身 |
|---|---|
| `broker_core.h/.cpp` | 判断のすべて（見張り §5.4、通信 §5.5、使えない間 §5.6）。OS に依存しない |
| `support.h/.cpp` | 上限付きログ、`engine.json` の読み込み、`--selftest` |
| `platform_win.cpp` | Windows: 名前付きパイプ + IOCP、ジョブ、環境ブロック、通知とダイアログ |
| `broker.rc` `broker.manifest` | Windows の exe に入れるもの: マニフェスト（Common Controls 6、asInvoker）と製品アイコン（`assets/icon/yuragi.ico`） |
| `tests/broker_core_test.cpp` | 中核の単体試験（偽の Platform と時計） |
| `tests/fake_engine.py` | §5.7 の偽エンジン（起動ごとの振る舞いを `plan.json` で決める） |
| `../../tests/test_broker.py` | §5.7 の試験（Windows のみ）。偽 TIP と偽エンジンを実プロセスで動かす |

```
cmake -S src/broker -B build/broker -DCMAKE_BUILD_TYPE=Release
cmake --build build/broker && ctest --test-dir build/broker   # 中核の単体試験（どの OS でも）
python -m unittest tests.test_broker          # Windows のみ。YURAGI_BROKER=dist\yuragi-broker.exe
```

`engine.json`（インストーラが `%LOCALAPPDATA%\yuragi-ime\versions\<tag>\` に書く）:

```json
{"format": 1, "python": "<python.exe の絶対パス>", "pythonw": "<pythonw.exe>",
 "app": "<作業フォルダ>", "args": ["-m", "yuragi.engine", "--dict-dir", "...", "--cache-dir", "..."],
 "admin_args": ["-m", "yuragi.ime.admin_ui"]}
```

ログは `%USERPROFILE%\.yuragi-ime\logs\`（`broker.log`、`engine.log`、`notices.log`。各 1MB × 2 世代）。
