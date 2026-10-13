# Third-party notices

このアプリは以下のソフトウェアを利用します。配布物の`licenses/`に原文を同梱します。
実際に同梱した版は`build-info.json`と各ライセンス文書を参照してください。

| ソフトウェア | 用途 | 主なライセンス／出典 |
|---|---|---|
| Python | 実行環境 | PSF License, https://www.python.org/ |
| NumPy | 数値計算 | BSD-3-Clause、同梱数値ライブラリの表示を含む, https://numpy.org/ |
| Flask / Werkzeug / Jinja2 / MarkupSafe / Click / ItsDangerous | ローカル画面 | BSD系、各パッケージの原文参照, https://palletsprojects.com/ |
| Blinker | Flask依存 | MIT, https://blinker.readthedocs.io/ |
| Waitress | ローカルHTTPサーバー | ZPL-2.1, https://docs.pylonsproject.org/projects/waitress/ |
| Pillow | PNG静止画 | MIT-CMU等、wheelに含まれる依存物の表示を含む, https://python-pillow.github.io/ |
| FFmpeg 8.0.3 | 動画解析・フレーム取得 | このUbuntuビルドはLGPL-2.1-or-later, https://ffmpeg.org/ |
| zlib | 圧縮処理 | zlib License, https://zlib.net/ |
| PyInstaller | 配布物生成・bootloader | GPL＋例外、生成アプリへの適用は例外に従う, https://pyinstaller.org/ |
| yt-dlp | YouTube動画の取得 | Unlicense, https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | YouTubeのJavaScript処理 | Unlicense、同梱コードはMIT・ISC等, https://github.com/yt-dlp/ejs |
| QuickJS | 上記処理の実行環境 | MIT, https://bellard.org/quickjs/ |
| Requests、urllib3、certifi、charset-normalizer、idna、Brotli、Mutagen、PyCryptodomex、websockets | yt-dlpの依存物 | 各パッケージの原文参照 |

yt-dlp-ejsのwheelに含まれるAstring（MIT）とMeriyah（ISC）の表示は
`licenses/bundled-js/`へ同梱します。原文の取得元はそれぞれ
`https://github.com/davidbonnet/astring/blob/master/LICENSE`、
`https://github.com/meriyah/meriyah/blob/main/LICENSE.md`です。

## FFmpeg

FFmpegはFFmpeg開発者によるソフトウェアです。このアプリの推薦・認定を意味しません。
このUbuntuビルドではGPL、nonfree、version3オプションを有効にしていません。
ネットワークを無効にし、FFmpeg／ffprobeを別実行ファイルとして利用します。

ソースは`https://ffmpeg.org/releases/ffmpeg-8.0.3.tar.xz`。
配布物の`sources/`に同じソースアーカイブ、署名、公開鍵、再ビルド用スクリプトを含めます。
スクリプトはこのプロジェクトの`scripts/build_ffmpeg.py`です。
利用者はFFmpegを改変・再ビルドし、配布フォルダーの`_internal/vendor/bin/`のバイナリを交換できます。
元ソースに対するパッチはありません。コンパイル構成はスクリプトに記録します。

## QuickJS

Ubuntu版はQuickJS 2026-06-04の公式ソースを改変せずにビルドしています。
配布物の`sources/`にソースと`scripts/build_quickjs.py`、`licenses/QuickJS-LICENSE`に原文を含みます。
バイナリは`_internal/vendor/bin/qjs`にあり、交換できます。

## NumPyのUbuntu構成

Ubuntu配布版のNumPyは外部BLAS/LAPACKなしでビルドしています。
OpenBLAS・libgfortran・libquadmathは同梱していません。
具体的な構成と再ビルド方法は`build-info.json`と`docs/distribution.md`を参照してください。

## 開発専用

pytest、Playwright、imageio-ffmpegはテストに使用します。
imageio-ffmpegに含まれる別のFFmpegは合成動画生成専用で、アプリ配布物には含めません。

## 本体

SEN-CHA本体はMITライセンスです。原文は`LICENSE`を参照してください。
この表に記載した第三者ソフトウェアには、それぞれのライセンスが適用されます。
外部公開はしていません。

生成物に含まれるSetuptoolsの補助モジュール、Packaging、GCCランタイムについても
`licenses/`へ表示を収録します。GCCランタイムの利用条件は同梱のRuntime Library Exceptionを参照してください。
