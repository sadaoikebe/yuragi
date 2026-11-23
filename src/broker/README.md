# yuragi-broker（DESIGN「ブローカー」）

サインインごとに 1 つ動く小さな常駐プログラム。役目と仕様は [DESIGN.md](../../docs/DESIGN.md) の「ブローカー」、
ビルドと試験は [DEVELOPMENT.md](../../docs/DEVELOPMENT.md)。

| ファイル | 中身 |
|---|---|
| `broker_core.h/.cpp` | 判断のすべて（見張り、通信、使えない間の打鍵）。OS に依存しない |
| `support.h/.cpp` | 上限付きログ、`engine.json` の形と読み込み、`--selftest` |
| `platform_win.cpp` | Windows: 名前付きパイプ + IOCP、ジョブ、環境ブロック、通知とダイアログ |
| `broker.rc` `broker.manifest` | Windows の exe に入れるもの: マニフェスト（Common Controls 6、asInvoker）と製品アイコン（`assets/icon/yuragi.ico`） |
| `tests/broker_core_test.cpp` | 中核の単体試験（偽の Platform と時計） |
| `tests/support_test.cpp` | 上限付きログ、`notices.log`、`engine.json` の読み込みの試験 |
| `tests/fake_engine.py` | 偽エンジン（Windows の試験用） |
| `../../tests/test_broker.py` | Windows だけの試験。偽 TIP と偽エンジンを実プロセスで動かす |
