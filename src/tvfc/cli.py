import argparse
import multiprocessing
from pathlib import Path
import sys

from . import __version__
from .analysis import analyze
from .media import Cancelled, MediaError
from .reports import save_reports
from .settings import DEFAULT_SENSITIVITY, REGION_GRIDS


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="動画の点滅確認候補を抽出します（WCAG適合判定ではありません）。")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    gui = commands.add_parser("serve", help="ローカル画面を起動")
    gui.add_argument("--port", type=int, default=0)
    gui.add_argument("--no-browser", action="store_true")
    gui.add_argument("--browser", action="store_true", help="既定ブラウザーで開く")
    gui.add_argument("--ready-file", type=Path, help=argparse.SUPPRESS)
    scan = commands.add_parser("analyze", help="動画を解析してHTML/JSON/CSVを保存")
    scan.add_argument("video", type=Path)
    scan.add_argument("--sensitivity", choices=["standard", "high"], default=DEFAULT_SENSITIVITY,
                      help="high=標準設定、standard=低感度（保存JSONとの互換識別値）")
    scan.add_argument("--region-mode", choices=REGION_GRIDS, default="fine",
                      help="局所領域の細かさ。fine=8×6、broad=4×3、whole=画面全体のみ")
    scan.add_argument("--output", type=Path, default=Path.cwd()/"results")
    args = parser.parse_args()
    try:
        if args.command in (None, "serve"):
            from .web import serve
            browser = getattr(args, "browser", False) or sys.platform != "linux"
            no_browser = getattr(args, "no_browser", False)
            serve(getattr(args, "port", 0), browser, getattr(args, "ready_file", None),
                  desktop=not (browser or no_browser or getattr(args, "ready_file", None)))
        elif args.command == "analyze":
            report = analyze(args.video, args.sensitivity, region_mode=args.region_mode)
            paths = save_reports(report, args.output)
            print(f'正常完了：{report["frames"]}フレーム、{report["elapsed"]:.2f}秒、候補{len(report["candidates"])}件')
            if not report["candidates"]:
                print("今回の検出条件では候補なし")
            for path in paths:
                print(path.resolve())
        return 0
    except (MediaError, OSError, ValueError) as error:
        print(f"処理を完了できませんでした：{error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("中止しました。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
