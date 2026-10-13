# pse-test-mediaによる試験動画

生成した動画は`tests/generated/pse-test-media/`に置く。このディレクトリはGit管理から除外している。**すべて点滅を含み、光過敏性てんかんのある人には危険になり得る。画面で再生せず、ファイルとして解析する。**

出典は[traceRERC/pse-test-media](https://github.com/traceRERC/pse-test-media)（BSD-3-Clause）、使用したコミットは`ef78542aad496827f25064f57aaf13d6a741ba75`。生成にはPython 3.13.12、opencv-python-headless 4.14.0.94、NumPy 2.5.3、Pillow 12.3.0を一時環境で使った。元リポジトリの`video_config.json`どおり、FFV1/AVIの可逆圧縮を使った。

| ファイル | 元の定義 | 元データのWCAG 2.3.1想定 | Tiny Video Flash Checker標準 | 高感度 |
| --- | --- | --- | --- | --- |
| `wcag-area-pass-a002f038.avi` | `wcagc_30fps_area01/a002f038.json` | 合格 | 候補0件 | 候補1件 |
| `wcag-area-fail-f002f038.avi` | `wcagc_30fps_area01/f002f038.json` | 不合格 | 候補0件 | 候補1件 |
| `alternating-fail-f001f037.avi` | `30fps_alternating_01/f001f037.json` | 不合格 | 候補1件 | 未実施 |

3本とも1920×1080、30fps、44フレーム、FFV1/AVI。`ffprobe`で動画形式を確認し、アプリのCLIで再生せずに解析した。合否は出典のCSVとJSONに書かれた**期待結果**であり、このアプリが適合性を判定した結果ではない。面積の不合格例は標準感度で見逃し、高感度では合格例も候補になる。現在の簡易検出器は境界付近の合否を区別できない。

生成物のSHA-256:

```text
alternating-fail-f001f037.avi    a25e6db95c204faa8e35d14d12113e95f22c05c5dbbc5a79f319e197e015bc41
wcag-area-fail-f002f038.avi      28ccc1ceb961c7a2ab0ea09dc1549f717933c5b4aa518646ad1f7ac44d047a3d
wcag-area-pass-a002f038.avi      9a60e6cbedcf59c777632a16e82c22c04135b940af1acbcfa67400e718e7bdc2
```

## 再生成

同じコミットの出典リポジトリを取得し、その中で以下の3つの定義ファイルを`make_single_video.py`に渡す。生成物は各定義ファイルと同じディレクトリの`videos/`に保存される。OpenCV、NumPy、Pillowが必要。元スクリプトは内部で`python`を呼ぶので、依存物を入れた仮想環境を`PATH`の先頭に置いて実行する。

```text
video_creation/wcagc_30fps_area01/a002f038.json
video_creation/wcagc_30fps_area01/f002f038.json
video_creation/30fps_alternating_01/f001f037.json
```

生成後、上表のファイル名で`tests/generated/pse-test-media/`にコピーする。元リポジトリのREADMEは、試験動画の画面表示についても警告している。検証時は自動再生やサムネイル表示を避ける。
