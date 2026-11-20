# 開発と技術文書

使う人向けの説明は [README](../README.md) と [USAGE.md](USAGE.md) にあります。
この文書は、技術文書の一覧と、開発環境・ビルド・試験・リリースの入口です。

## 技術文書

- [DESIGN.md](DESIGN.md) — 全体の設計（構成、置き場所、通信、ブローカー、エンジン、TIP、インストール・更新・アンインストールの手順、利用者に見えるもの、実地試験、定数）
- [CONVERSION.md](CONVERSION.md) — 変換の仕様（キーとトークン、同時打鍵の判定、左右交互、変換、セッション、文節と候補、学習、n-best、LM、設定）
- [EVALUATION.md](EVALUATION.md) — 変換の評価と診断、実打鍵の記録と再生
- [PERFORMANCE.md](PERFORMANCE.md) — CPU・GPU での LM の速さと精度の調査（モデルの比較、較正、遅い PC、GPU と電池）

同時打鍵の状態機械（S1〜S7）の表と各状態の出口は、`yuragi/chord/fsm.py` 冒頭の説明にあります。
TIP は [`src/tip/README.md`](../src/tip/README.md)、ブローカーは [`src/broker/README.md`](../src/broker/README.md)。

## 開発環境

### Linux（変換エンジン・ブローカー・TIP の判断の試験）

Python 3.12 以上、CMake、C++17 のコンパイラ。Windows が無くても、Python の試験（ブローカーを実プロセスで
動かす `tests/test_broker.py` は Windows だけ）、ブローカーの中核（`broker_core`）の試験、TIP の判断
（`tip_logic.h`）の試験が回る。CI の Linux ジョブと同じ。

`tests/test_installer_scripts.py` の PowerShell の部分は `pwsh` を使う（無ければ飛ばす。`YURAGI_PWSH` で場所を指定できる）。

### Windows（TIP の DLL とブローカーの exe）

管理者で入れるもの: Visual Studio Build Tools（C++。MSVC、Windows SDK、CMake を含む）。管理者のコマンドプロンプトで:

```bat
winget install --id Microsoft.VisualStudio.BuildTools -e --accept-package-agreements --accept-source-agreements --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

`dev-build.ps1` は `vswhere` で最新の Build Tools を探し、開発者環境を自分で読み込む。

利用者の権限で入れるもの: Python 3.13（64 ビット）。CMake と Ninja は Build Tools の CMake コンポーネントに入っている
（無ければ `python -m pip install cmake ninja`）。エンジンを開発用に動かすなら、
`packaging/requirements.txt` の依存と torch（CPU 版で足りる）も。

## ビルドと試験

```sh
python -m tools.eval.fetch_mozc_dict                 # 初回のみ。Mozc OSS 辞書
python -m yuragi.lattice.dict_manifest verify       # 辞書がマニフェストと一致するか（write で書き出し）
python -m unittest $(ls tests/test_*.py | sed 's#/#.#;s#\.py$##')   # 全試験
cmake -S src/broker -B build/broker -DCMAKE_BUILD_TYPE=Release && cmake --build build/broker && ctest --test-dir build/broker
cmake -S src/tip -B build/tip -DCMAKE_BUILD_TYPE=Release && cmake --build build/tip && ctest --test-dir build/tip
```

- ブローカーと TIP の CMake は、Linux では単体試験（`broker_core_test`、`tip_logic_test`、`tip_json_test`）だけを
  ビルドする。Windows では `yuragi-broker.exe` と `yuragi_tip.dll` もできる（TIP のタグは `-DYURAGI_TAG=<tag>`。
  x86 の開発者環境でビルドすると、32 ビットのアプリ用の `yuragi_tip32.dll` になる）。
- ブローカーを実プロセスで動かす試験は Windows だけ:
  `python -m unittest tests.test_broker`（`YURAGI_BROKER=dist\yuragi-broker.exe`）。

Windows でのビルドと登録（DESIGN「開発時」）:

```powershell
powershell -ExecutionPolicy Bypass -File .\src\tip\dev-build.ps1      # ビルドと試験（管理者不要）。リリースのワークフローもこれ
powershell -ExecutionPolicy Bypass -File .\src\tip\dev-register.ps1   # タグ dev として登録（UAC 1 回）
```

- TSF を通さずにセッションを試す窓: `python -m yuragi.ime.host_win32`。
- 設定ウィンドウ: `python -m yuragi.ime.admin_ui`（tkinter、標準ライブラリだけ）。ロジックは tkinter に
  依存しない `AdminModel`（試験は `tests/test_admin_ui.py`）にあり、画面は薄い殻。画面の文言はすべて日本語
  （`admin_ui.SETTINGS` などの表）。DPI 対応を申告する。`--runtime-dir` と `--config` で置き場所を変えられる。

> **注意**: TIP の登録は `ITfInputProcessorProfileMgr` だけで行う。HKCU への手書きの登録や、古い
> `Register` / `AddLanguageProfile` との二重登録をすると、一覧に出ても別のエンジンを掴んだり、
> ホットキーがおかしくなったりする。

## リリース

タグ `v*` を push すると `.github/workflows/release.yml` が作ります
（ビルド・試験・依存の検証のあと、プレリリースとして公開し、まっさらな Windows で入れて消す）。
インストール試験では、配置済みの Python・辞書・固定モデルを使い、`--require-lm` 付きの自己試験で zenz の変換を確認する。
リリースに置く `setup.ps1` と `uninstall.ps1` の元は `packaging/setup.ps1` と
`packaging/uninstall-entry.ps1` です（手順は DESIGN「インストール・更新・アンインストール」）。
実機で確かめたら `gh release edit <tag> --prerelease=false --latest` で正式リリースにします
（README の 1 行が使う `releases/latest` はプレリリースを指さず、正式リリースが無いと 404 になります）。

## ライセンス

自前のコードは [MIT](../LICENSE)。Mozc の OSS 辞書（`suffix.txt`・`id.def`・README も含めて全部取得物で、git には無い）は
Google の BSD-3-Clause に加え、IPAdic（NAIST / ICOT）と沖縄辞書の条件が付きます。
条文は [NOTICE.md](../NOTICE.md) と、取得した `third_party/mozc_oss_dict/README.txt`。
インストール時に取得する Python ランタイム・PyTorch などの依存・LM モデルのライセンスも NOTICE.md にまとめてあります。
かな配列と同時打鍵の判定規則は NICOLA 配列規格書（日本語入力コンソーシアム、http://nicola.sunicom.co.jp/spec/kikaku.htm）に基づきます。
