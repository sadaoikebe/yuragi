# ゆらぎ

ゆらぎは、親指シフト（NICOLA）で日本語を打つための Windows の IME です。

専用の親指シフトキーボードがなくても、普通のノートPC で親指シフトが使えます。

**US 配列（ANSI）専用です。** JIS配列のキーボードでは、通常の親指シフトエミュレータをお使いください。
US 配列のキーボードでも、Windows の設定が「日本語キーボード（106/109 キー）」のままだと「ん」が「＝」になります。
[使い方の「困ったとき」](docs/USAGE.md#困ったとき)を見て、設定を変えてください。

## インストール・更新

管理者ではない普段の PowerShell で、次の1行を実行します。

```powershell
$f = "$env:TEMP\yuragi-setup.ps1"; Remove-Item $f -ErrorAction Ignore; iwr -UseBasicParsing https://github.com/sadaoikebe/yuragi/releases/latest/download/setup.ps1 -OutFile $f; if ($?) { powershell -ExecutionPolicy Bypass -File $f }
```

途中で、管理者の確認が1回出ます。アプリは開いたままで構いません。

## アンインストール

同じく PowerShell で、次の1行を実行します。

```powershell
$f = "$env:TEMP\yuragi-uninstall.ps1"; Remove-Item $f -ErrorAction Ignore; iwr -UseBasicParsing https://github.com/sadaoikebe/yuragi/releases/latest/download/uninstall.ps1 -OutFile $f; if ($?) { powershell -ExecutionPolicy Bypass -File $f }
```

学習した内容・登録した単語・設定は残ります。

全部消す場合は、次の1行を実行します。

```powershell
$f = "$env:TEMP\yuragi-uninstall.ps1"; Remove-Item $f -ErrorAction Ignore; iwr -UseBasicParsing https://github.com/sadaoikebe/yuragi/releases/latest/download/uninstall.ps1 -OutFile $f; if ($?) { powershell -ExecutionPolicy Bypass -File $f -RemoveData }
```

## 使い始め

1. **Win+Space** で「ゆらぎ」を選びます。
2. タスクバーの右下に、入力モードが出ます。

| 表示 | 意味 |
|---|---|
| ゆ | かな入力 |
| Y | 直接入力（英字がそのまま入る） |
| 薄い ゆ | 準備中。打った文字は、変換されずにそのまま（英字で）入ります |
| ! | 日本語変換が止まっています。右クリックで「もう一度試す」 |

「ゆ」と「Y」は、クリックで切り替わります。キーでは `` Alt+` `` です。

## 親指の使い方

親指は、専用の親指シフトキーボードと同じように左右を使い分けてください。片方の親指だけで打つと、変換の精度が落ちます。
速く打って左右の押下がつながっても、打ち間違いではありません。左右が交互だった手がかりとして、変換に使います。

## もっと詳しく

- [使い方](docs/USAGE.md) — キー操作、候補窓、設定ウィンドウ、困ったとき、更新とアンインストール
- [開発と技術文書](docs/DEVELOPMENT.md) — 技術文書の一覧、開発環境、ビルドと試験

## ライセンス

自前のコードは [MIT](LICENSE) です。インストール時に取得する Mozc の辞書・Python と PyTorch などの部品・言語モデルには、それぞれの条件が付きます。
詳しくは [NOTICE.md](NOTICE.md) を見てください。
