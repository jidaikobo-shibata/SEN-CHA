# ビルドと配布

## 対象と検証方針

最初の配布対象はUbuntu 24.04 / x86_64。ビルド環境と同等のglibcが必要。
Ubuntuの専用ウィンドウにはOS側の`/usr/bin/python3`、`python3-gi`、GTK 3、WebKitGTK 4.1が必要。
検証端末では`python3-gi`と`gir1.2-webkit2-4.1`を確認した。
不足する環境では`serve --browser`でブラウザー画面を利用できる。
Windows・macOSは共通ソースとビルドスクリプトを用意するが、実行・配布は未検証。
OS間のクロスコンパイルは行わず、各OS上でビルドする。
署名、ストア申請、外部への公開は今回行わない。

## FFmpeg（Linux／macOS）

今回使用するソースはFFmpeg公式の8.0.3。
公式ソースは以下から取得する。

- https://ffmpeg.org/releases/ffmpeg-8.0.3.tar.xz
- https://ffmpeg.org/releases/ffmpeg-8.0.3.tar.xz.asc
- https://ffmpeg.org/ffmpeg-devel.asc

配置先はプロジェクトの`vendor/sources/`。
ソースSHA256:

```text
6136812ea6d4e68bdba27e33c2a94382711cdf4f8602ffef056ff792bd6f9818
```

今回、公式公開鍵のfingerprint
`FCF986EA15E6E293A5644F10B4322F04D67658D8`と署名を検証した。
ビルドスクリプトもソースのSHA256を照合する。

Cコンパイラー、make、zlibの開発ファイルを準備し、以下を実行する。

```bash
.venv/bin/python scripts/build_ffmpeg.py
```

sudoは不要。ソースは`vendor/build/`に展開し、バイナリは`vendor/bin/`へ配置する。
`--disable-network --disable-autodetect`を指定し、GPL・nonfreeオプションを有効にしない。
FFmpegのコードは静的リンクだが、Ubuntu版はOSのlibc・libm・zlibへ動的リンクする。
`--disable-x86asm`は追加のアセンブラーを不要にするためで、最高速度を狙う構成ではない。
変更してビルドする場合は構成とライセンス情報を更新する。

## QuickJSとYouTube取得

YouTube取得にはyt-dlp 2026.8.19とyt-dlp-ejs 0.8.0を同梱する。
EJSの実行にはQuickJSを使用し、外部JSスクリプトの自動ダウンロードは有効にしない。
QuickJSは[公式ソース](https://bellard.org/quickjs/)の2026-06-04版を使用する。
`vendor/sources/quickjs-2026-06-04.tar.xz`のSHA256:

```text
b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a
```

```bash
.venv/bin/python scripts/build_quickjs.py
```

スクリプトはハッシュを照合して`vendor/bin/qjs`を生成する。QuickJSはMITライセンス。
ソース、再ビルド用スクリプト、ライセンスを配布物にも収録する。
YouTube側の仕様変更に合わせ、yt-dlpとEJSを対応する組み合わせで更新する必要がある。
任意URL、Cookie、ログイン動画、ライブ配信、プレイリストの取得は実装していない。

## アプリのパッケージ

開発依存物を用意し、以下を実行する。

```bash
.venv/bin/python scripts/build.py
```

出力は`dist/SEN-CHA/`とOS・CPU名を含むアーカイブ。
Python、NumPy等の実行時依存物、FFmpeg、ffprobe、ライセンス、FFmpegソース、ビルド手順を含む。
フォルダー全体で利用し、実行ファイルだけを取り出さない。
Ubuntuでは、アーカイブ展開先の実行ファイルを起動すると専用ウィンドウが開く。`serve --browser`を指定すると既定のブラウザーを使える。Windows・macOSでは現在、既定のブラウザーが開く。
端末内の動画ファイルを解析する場合、実行時のインターネット接続は不要。
URL解析では動画取得のための接続が必要。
専用ウィンドウには上記のOS提供GTK/WebKitが必要で、これらは配布アーカイブには同梱しない。

配布物内の`SHA256SUMS`は自己確認用で、第三者による署名・真正性保証ではない。
`build-info.json`にビルド環境と実行時依存物を記録する。

## Windows（未検証）

1. Windows上でPython 3.13と開発依存物を準備する。
2. Windows用FFmpeg／ffprobeとQuickJSの`qjs.exe`を`vendor/bin/`へ置く。
3. バイナリはLGPL構成を優先し、元ソース・ビルド構成・同梱DLLのライセンスを確認する。
4. 必要なDLLも`vendor/bin/`に置く。元ソースとライセンスを`vendor/sources/`へ保存する。
5. WindowsのPythonで`scripts/build.py`を実行する。
6. ZIPを別のWindows環境に展開し、起動・入力・解析・中止・保存・終了を検証する。

macOS/Linux用にビルドしたバイナリは流用しない。
未署名の実行ファイルのため警告が出る可能性がある。一般配布用の署名は別の作業とする。

## macOS（未検証）

1. 対象CPU（Apple SiliconまたはIntel）のmacOSでPython 3.13と開発依存物を準備する。
2. Command Line Tools、make、zlibを用意し、`scripts/build_ffmpeg.py`と`scripts/build_quickjs.py`を実行する。
3. `scripts/build.py`を実行する。
4. 同じCPUの別環境で、起動・入力・解析・中止・保存・終了を検証する。

初期スクリプトはフォルダー形式のコマンド実行ファイルを作る。
.app化、Universal Binary、署名、公証は未対応。

## 配布前の確認

- 各OSの実機で検証していないものを動作保証しない。
- LGPL対象のFFmpegは別実行ファイルとして配置し、利用者による交換を妨げない。
- FFmpegソースとビルドスクリプトを配布物に同梱する。
- 同梱ライブラリの著作権・ライセンスを`licenses/`で確認する。
- 公開名と本体ライセンスを確定する。現在はローカル評価用。
- 外部公開、外部CI、署名や証明書設定は利用者の承認を受ける。

## 数値処理依存物の構成

Ubuntu配布版では、行列分解等に使う外部BLAS/LAPACKを必要としないため、NumPyをそれらなしでビルドする。
NumPy標準wheelをそのまま再配布する場合は、libquadmath等の同梱物についてもソース提供条件を別途確認する。

```bash
uv pip install --python .venv/bin/python \
  --reinstall-package numpy --no-binary numpy numpy==2.5.3 \
  --config-setting=setup-args=-Dblas=none \
  --config-setting=setup-args=-Dlapack=none \
  --config-setting=compile-args=-j4
```

NumPyの実際の構成は配布物の`build-info.json`に記録する。
NumPy 2.5のこのx86_64ビルドはX86_V2（SSE4.2等）をベースラインとする。
別OSでビルドするときは数値ライブラリの構成・必要なCPU命令・ライセンスを確認する。
OS固有の追加ライセンスは`vendor/licenses/`に置くと配布物へコピーされる。

配布物からソースを再ビルドする場合は、`sources/application-source.tar.gz`を新しい作業ディレクトリに展開し、
その下に`vendor/sources/`を作って同梱FFmpegソースをコピーする。
その作業ディレクトリからREADMEと本書のビルド手順を実行する。
