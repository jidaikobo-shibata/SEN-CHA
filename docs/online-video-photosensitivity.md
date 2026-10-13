# オンライン動画と光過敏性への対応

確認日: 2026-09-30。公開資料の要約であり、個々の動画の医学的な安全性やWCAG適合性を判定するものではない。

## 確認できたこと

- 米国の当事者支援団体 Epilepsy Foundation は、SNS上の動画やGIFが光過敏性のある人に影響し得ること、点滅を含む動画等によって発作が起きた事例があることを説明している。自動再生を無効にすることも勧めている。[Staying Safe on Social Media](https://www.epilepsy.com/preparedness-safety/staying-safe/social-media)
- 英国の当事者支援団体 Epilepsy Action は、SNSの動画やGIFを視覚的な発作誘因の一つとして挙げ、視聴前の注意表示の確認や自動再生の無効化を勧めている。[Photosensitive epilepsy](https://www.epilepsy.org.uk/info/seizure-triggers/photosensitive-epilepsy)
- Epilepsy Action は制作者側に、誘因となる映像の除去または開始前の十分な警告を求めている。同団体は、点滅を懸念してYouTubeの広告を避けるためにPremiumを購入した人がいた事例も紹介している。[Photosensitive epilepsy and online content](https://www.epilepsy.org.uk/press/photosensitive-epilepsy-and-online-content)
- YouTubeのヘルプには、光過敏性てんかんに影響し得る点滅を示す `F` というコンテンツ評価の説明がある。ただし、そのページは評価を適用できる対象を「有料コンテンツのみ」と明記している。通常の投稿動画に一律の評価が付くという説明ではない。[YouTube content rating](https://support.google.com/youtube/answer/146399)
- YouTubeは次の動画の自動再生を無効にする操作を案内している。これは視聴者が露出を減らすための設定であり、動画自体の安全性を示すものではない。[Auto-play videos](https://support.google.com/youtube/answer/6327615)

## 解釈上の注意

- 上記の `F` 評価のヘルプは現在も公開されているが、YouTubeは旧来の「有料コンテンツ」機能を2018年に廃止したと説明している。したがって、この評価を現在の一般投稿動画向けの網羅的な警告機能と扱わない。[有料コンテンツ機能の終了について](https://support.google.com/youtube/answer/7515570?hl=ja)
- 今回確認したYouTubeの公式資料には、通常の投稿動画をすべて閃光検査して安全性を保証するという説明は見当たらなかった。これは調査範囲についての記述であり、YouTubeの内部処理の有無を断定するものではない。
- 光過敏性のある人の反応には個人差があり、WCAGの閾値への適合と、すべての視聴者に対する安全性は同じ意味ではない。[Epilepsy Actionの説明](https://www.epilepsy.org.uk/info/seizure-triggers/photosensitive-epilepsy)、[W3Cの達成基準解説](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold)
- 公開されているYouTube動画のうち、どれほどの割合が閃光の基準を超えるかは、上記資料からは分からない。今回の1本の検査結果から全体の割合を推定しない。

## このプロジェクトへの示唆

SEN-CHA（旧Tiny Video Flash Checker）は、動画の公開状態や警告表示を安全性の根拠にせず、元動画の検出候補を時刻とともに提示する。候補なしも安全・適合を意味しない。検出品質を論じる場合は、動画を系統的に選び、同一の条件で検査した結果を別途集める。

次に確認するとよいこと: YouTubeの一般投稿動画に関する光過敏性への公式方針や機能が更新されていないか再調査する。上記リンクは将来変更され得る。
