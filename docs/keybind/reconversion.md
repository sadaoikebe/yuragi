# 再変換の仕組みと各 IME の動き

確定した文字を変換し直す「再変換」について、Windows・TSF の仕組み、Mozc の作り、MS-IME の動き、アプリごとの違いをまとめる。
略号は末尾の出典。各項目に、Microsoft の資料に書いてあるもの（資料）、ソースを読んで分かるもの（ソース）、ほかの人が見た動き（報告）の区別を付ける。

---

## 1. TSF の仕組み（資料）

- 再変換の入口は `ITfFnReconversion`。テキストサービス（TIP）が実装し、TSF マネージャーかアプリが使う [FNR]。
  - TSF マネージャーは、TIP の `ITfFunctionProvider::GetFunction` に `IID_ITfFnReconversion` を渡して受け取る。
  - アプリは TSF マネージャーの `ITfFunctionProvider::GetFunction` から受け取る。TSF マネージャーが仲立ちをする。
  - アプリの手順は `ITfThreadMgr::GetFunctionProvider(GUID_SYSTEM_FUNCTIONPROVIDER)` → `GetFunction(GUID_NULL, IID_ITfFnReconversion)` [BLOG1]。
- 3 つのメソッド:

| メソッド | 中身 | 出典 |
|---|---|---|
| `QueryRange(pRange, ppNewRange, pfConvertable)` | `pRange` は再変換する文字の全部か一部。`*ppNewRange` に再変換できる文字の全部を覆う範囲を返す（NULL を返して S_OK でもよい）。TIP が実装するときは `ppNewRange` が NULL で呼ばれることがある | [QR] |
| `GetReconversion(pRange, ppCandList)` | `QueryRange` で得た範囲の候補を `ITfCandidateList` で返す | [GR] |
| `Reconvert(pRange)` | 再変換を始める。画面を出すときも、閉じるのを待たずに戻る | [RC] |

- アプリが候補を自分で出すときは `QueryRange` → `GetReconversion` → `ITfCandidateList::SetResult`。TIP に候補を出させるときは `Reconvert` を呼ぶ [BLOG1]。
- `QueryRange` は、範囲を変換の単位のまとまりまで広げるのがよい。`QueryRange` と `GetReconversion` の中では、同期の編集セッションを必ず取れる [BLOG1]。
- 再変換のように、アプリが `ITfFunctionProvider` で TIP に頼む処理では、アプリは同期のロックを渡さなければならない [MAG]。
- 編集セッション [RES]:
  - `TF_ES_SYNC` は同期でなければ失敗する（`TF_E_SYNCHRONOUS`）。キー処理のような、資料に書かれた場面でだけ使う。
  - 読み取り専用の文書に `TF_ES_READWRITE` を頼むと `TS_E_READONLY` になる（`TS_SD_READONLY` [TSS]）。
  - `OnEndEdit`・`OnLayoutChange`・`OnStatusChange` の中では、同期の読み書きセッションは取れない。
- 読みのプロパティ `GUID_PROP_READING` がある。覆う文字の読みを持つ。Windows ストア アプリはこのプロパティに対応しない [PROP]。
  MS-IME が再変換でこれを書くか読むかは、資料に無い。
- `ITfReverseConversionMgr`・`ITfReverseConversion`（文字列を打つためのキーの並びを返す）は「内部用」とされている [REV]。

### 1.1 IMM32 のアプリ（資料）

- IME はアプリに `WM_IME_REQUEST` の `IMR_RECONVERTSTRING` を送る。`lParam` が NULL ならアプリは要る大きさを返し、そうでなければ `RECONVERTSTRING` を埋める [IMR]。
- IME は範囲を直してよく、直したら `IMR_CONFIRMRECONVERTSTRING` を送る。アプリが TRUE を返せば直した範囲、FALSE なら元の範囲で入力中の文字を作る [IMRC]。
- `RECONVERTSTRING` の長さは Unicode では文字数、位置は `dwStrOffset` からのバイト数 [RCS]。
- アプリから `ImmSetCompositionString(SCS_QUERYRECONVERTSTRING / SCS_SETRECONVERTSTRING)` で再変換を始めることもできる [RCS][URI]。

### 1.2 Win+/（資料）

- Windows のショートカット一覧に「IME の再変換を開始」として載っている [WINKEY]。
- Win+/ が TIP にどう届くかは、資料に無い。

---

## 2. Mozc の作り（ソース）

ファイルは `src/win32/tip/` の下 [MOZC]。

- 登録: `ActivateEx` で `ITfSourceSingle::AdviseSingleSink(client_id, IID_ITfFunctionProvider, this)`、`Deactivate` で外す。
  `GetFunction` は `IID_ITfFnReconversion` に `TipReconvertFunction` を返す（`tip_text_service.cc`）。再変換用の PreservedKey は登録しない。
- `TipReconvertFunction`（`tip_reconvert_function.cc`）:
  - `QueryRange`: 範囲の文字を読み、入力中の文字か埋め込み物（`TS_CHAR_EMBEDDED`）を含めば変換できないと返す。そうでなければ渡された範囲をそのまま返す（広げない）。
  - `GetReconversion`: 範囲の文字の候補を返す。候補を選ぶと、その範囲を書き換える。
  - `Reconvert`: `ReconvertFromApplicationSync(range)` を呼ぶ。範囲の文字が空なら何もしない。入力中と埋め込み物は断る。
    表記をサーバーに `CONVERT_REVERSE` で送り、結果を `TF_ES_READWRITE | TF_ES_SYNC` のセッションで反映する（`tip_edit_session.cc`）。
- キーで始めるとき:
  - MS-IME 風のキー表は `DirectInput Henkan Reconvert` と `Precomposition Henkan Reconvert`、ATOK 風は Shift+変換（[mozc.md](mozc.md)）。
  - サーバーは `CONVERT_REVERSE` を頼む返事を返すだけで、TIP が文書を読む（`session.cc` の `RequestConvertReverse`）。
  - TIP の `PrepareForReconversionFromIme`（`tip_surrounding_text.cc`）が、文書全体に `TF_ES_SYNC | TF_ES_READWRITE` のセッションを取り、選択範囲の文字と前後 20 字ずつを読む。
    埋め込み物で止まる。選択範囲は先頭に縮める。空の選択を広げない。
  - TSF で読めなければ `IMR_RECONVERTSTRING` を送り、その前後と対象をつなげて使う。
  - 選択が空なら、IME をオンにするだけ。入力中の再変換は無い。
- 読み: 確定したときの読みは残さず、表記から辞書を逆に引いて作る。
  `Session::ConvertReverse` は `GetReadingText(表記)` で読みを得て、入力中の文字にし、元の表記を覚えて変換する。
  状態は変換中で、候補窓を開いて始める。逆引き（`reverse_converter.cc`、`immutable_converter.cc` の `LookupReverse`）は 600 字まで、結果は 1 つ。
  候補の無い文節が 1 つでもあれば失敗する。
- 選択範囲が入力中の文字になる: `InsertTextAtSelection(TF_IAS_QUERYONLY)` の範囲で `StartComposition` する（`tip_edit_session_impl.cc`）。
- Excel は `IMR_RECONVERTSTRING` に 0 を返し、そのあと自分で `ITfFnReconversion` を呼ぶ。Mozc はそれを待つ [MZ1384]。
- 確定取消（Ctrl+Backspace、`Undo`）: 確定のたびに元に戻す情報を積む。取り消すと、確定した長さの削除範囲を返し、TIP が前の文字を消して入力中に戻す。
  消せなければ Backspace を送る（`tip_edit_session.cc`、`session.cc`）。
- IMM32 時代のコード（`win32/base/imm_reconvert_string.cc`）には、選択が空ならカーソルの後ろ（無ければ前）の 1 字から同じ字種の続く所までを対象にする処理がある。
  コメントは「既存の日本語 IME は最小の文節で入力中の文字を作るようだ」。TIP のコードからは呼ばれていない。

---

## 3. MS-IME の動き

- キー（資料）: テンプレート「Microsoft IME」では変換キーと Ctrl+ImeOn、「ATOK」では Shift+変換が再変換 [S2]（[ms-ime.md](ms-ime.md) §1.1）。
  設定アプリでは、再変換の働きを「直前に確定した文字を再変換します」と書く [HP]。
- 読みをどこから得ているかは、資料に無い。貼り付けた文字の読みを再変換で調べる使い方が紹介されている（旧 IME）[ATKANA]。
- 選択が空でカーソルが文字の中: カーソルの位置の文節が再変換の状態になる。確定すると、その文節が置き換わる（報告）[FOREST][OOO]。
- 選択が空でカーソルが確定した文字の直後: 再変換の候補が出る。MS-IME は、編集セッションの中で対象の範囲を選択範囲にしてから入力中の文字を始める（報告、TSF を記録した結果）[VSC324435]。
- 選択があるとき: 選んだ範囲を再変換して置き換える（報告）[FOREST][VSC324435]。
- 確定直後の Ctrl+Backspace（旧 IME、報告）: 1 番目の候補を選んだ変換中に戻る。変換キーで候補を順に選べ、続けて Backspace でかなに戻る [AT0702]。
  新 MS-IME で同じかは確かめていない。
- Win+/（報告）: どの IME でも再変換できる。MS-IME はカーソルの位置の文節を再変換する。Google 日本語入力は、選んでいないと何も起こらない [FOREST]。

---

## 4. アプリごとの違い（報告とソース）

| アプリ | 中身 | 出典 |
|---|---|---|
| Word | ふだんは同期の編集セッションを渡さないが、再変換を頼むときだけは渡す（資料）。ルーラーの字下げを動かしたあと、同期の読み書きを `TF_E_SYNCHRONOUS` で断り続けることがある（報告） | [BLOG2], [MZ819], [MZ821] |
| Excel | `IMR_RECONVERTSTRING` に 0 を返し、自分で `ITfFnReconversion` を呼ぶ。選択が空ならセルの文字を選んで再変換させる。TIP が文脈の選択範囲から読むと壊れ、渡された範囲から読むと直った | [MZ1384] |
| Chrome・Edge | TSF の文書は `TS_SS_TRANSITORY | TS_SS_NOHIDDENTEXT`。`GetText` で文字と選択範囲は読める（ソース）。IMM32 の `IMR_RECONVERTSTRING` は、入力中か選択が空なら 0 を返す（ソース）。Mozc は一時的な文書の周りの文字を使わない | [CRTSF], [CRIMM], [MZ1289] |
| IMM32・CUAS のアプリ（秀丸、サクラエディタ） | TSF の `GetText` は成功して空を返す。文字は `IMR_DOCUMENTFEED`・`IMR_RECONVERTSTRING` でしか得られず、CUAS はそちらへ自動では回さない | [MZ1293] |
| VS Code（Chromium の EditContext） | 選んだ文字の再変換はできる。カーソル位置での再変換は、置き換えずに足して二重になる | [VSC324435], [VSC230303] |
| メモ帳（Windows 11） | MS-IME のカーソル位置の再変換で正しく置き換わる（報告） | [VSC324435], [FOREST] |
| Windows Terminal・コンソール | 資料もソースの手がかりも無い（`microsoft/terminal` に `ITfFnReconversion`・`IMR_RECONVERTSTRING` は無い） | — |
| Avalonia、Flutter | `ITfFnReconversion` に対応していない | [AVA], [FLU] |

---

## 出典

| 略号 | 資料名 | URL |
|---|---|---|
| FNR | Microsoft Learn「ITfFnReconversion interface」 | https://learn.microsoft.com/en-us/windows/win32/api/ctffunc/nn-ctffunc-itffnreconversion |
| QR | Microsoft Learn「ITfFnReconversion::QueryRange」 | https://learn.microsoft.com/en-us/windows/win32/api/ctffunc/nf-ctffunc-itffnreconversion-queryrange |
| GR | Microsoft Learn「ITfFnReconversion::GetReconversion」 | https://learn.microsoft.com/en-us/windows/win32/api/ctffunc/nf-ctffunc-itffnreconversion-getreconversion |
| RC | Microsoft Learn「ITfFnReconversion::Reconvert」 | https://learn.microsoft.com/en-us/windows/win32/api/ctffunc/nf-ctffunc-itffnreconversion-reconvert |
| BLOG1 | Microsoft アーカイブ ブログ「Generating candidates from an application」(TSF Aware, 2007) | https://learn.microsoft.com/en-us/archive/blogs/tsfaware/generating-candidates-from-an-application |
| BLOG2 | Microsoft アーカイブ ブログ「Rules of Text Services」(TSF Aware) | https://learn.microsoft.com/en-us/archive/blogs/tsfaware/rules-of-text-services |
| MAG | MSDN Magazine「Support Dictation with Text Services Framework」(2007-07) | https://learn.microsoft.com/en-us/archive/msdn-magazine/2007/july/speak-up-support-dictation-with-text-services-framework |
| RES | Microsoft Learn「ITfContext::RequestEditSession」 | https://learn.microsoft.com/en-us/windows/win32/api/msctf/nf-msctf-itfcontext-requesteditsession |
| TSS | Microsoft Learn「TS_STATUS」 | https://learn.microsoft.com/en-us/windows/win32/api/textstor/ns-textstor-ts_status |
| PROP | Microsoft Learn「Predefined Properties」 | https://learn.microsoft.com/en-us/windows/win32/tsf/predefined-properties |
| REV | Microsoft Learn「ITfReverseConversionMgr」 | https://learn.microsoft.com/en-us/windows/win32/api/msctf/nn-msctf-itfreverseconversionmgr |
| IMR | Microsoft Learn「IMR_RECONVERTSTRING」 | https://learn.microsoft.com/en-us/windows/win32/intl/imr-reconvertstring |
| IMRC | Microsoft Learn「IMR_CONFIRMRECONVERTSTRING」 | https://learn.microsoft.com/en-us/windows/win32/intl/imr-confirmreconvertstring |
| RCS | Microsoft Learn「RECONVERTSTRING」 | https://learn.microsoft.com/en-us/windows/win32/api/imm/ns-imm-reconvertstring |
| URI | Microsoft Learn「Using Reconversion with an IME」 | https://learn.microsoft.com/en-us/windows/win32/intl/using-reconversion-with-an-ime |
| WINKEY | Microsoft サポート「Windows のキーボード ショートカット」 | https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec |
| S2 | Microsoft サポート「Microsoft 日本語 IME」（ja-jp） | https://support.microsoft.com/ja-jp/windows/microsoft-日本語-ime-da40471d-6b91-4042-ae8b-713a96476916 |
| HP | HP FAQ 93 | https://jp.ext.hp.com/v-ivr/common/os-howto/faq/93/ |
| ATKANA | @IT Windows TIPS（IME 2003 のころ） | https://atmarkit.itmedia.co.jp/fwin2k/win2ktips/861kanacon/kanacon.html |
| AT0702 | @IT（2007-02） | https://atmarkit.itmedia.co.jp/ait/articles/0702/03/news016.html |
| FOREST | 窓の杜「usefulkeys」(2025-12-29、2026-04-15 追記) | https://forest.watch.impress.co.jp/docs/shseri/usefulkeys/2074743.html |
| OOO | OpenOffice Wiki「Japanese Reconversion」（MS-IME 2002〜2007） | https://wiki.openoffice.org/wiki/Japanese_Reconversion |
| MOZC | google/mozc のソース（`src/win32/tip/`、`src/session/session.cc`、`src/converter/`） | https://github.com/google/mozc |
| MZ819 | google/mozc issue 819 | https://github.com/google/mozc/issues/819 |
| MZ821 | google/mozc issue 821 | https://github.com/google/mozc/issues/821 |
| MZ1289 | google/mozc issue 1289 | https://github.com/google/mozc/issues/1289 |
| MZ1293 | google/mozc issue 1293 | https://github.com/google/mozc/issues/1293 |
| MZ1384 | google/mozc issue 1384 | https://github.com/google/mozc/issues/1384 |
| CRTSF | Chromium `ui/base/ime/win/tsf_text_store.cc` | https://chromium.googlesource.com/chromium/src/+/main/ui/base/ime/win/tsf_text_store.cc |
| CRIMM | Chromium `ui/base/ime/win/input_method_win_base.cc` | https://chromium.googlesource.com/chromium/src/+/main/ui/base/ime/win/input_method_win_base.cc |
| VSC324435 | microsoft/vscode issue 324435 | https://github.com/microsoft/vscode/issues/324435 |
| VSC230303 | microsoft/vscode issue 230303 | https://github.com/microsoft/vscode/issues/230303 |
| AVA | AvaloniaUI/Avalonia issue 21948 | https://github.com/AvaloniaUI/Avalonia/issues/21948 |
| FLU | flutter/flutter issue 74547 | https://github.com/flutter/flutter/issues/74547 |
