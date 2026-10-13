"""Constrained, user-initiated YouTube video acquisition."""
from pathlib import Path
import os
import re
import shutil
import time
import unicodedata
from urllib.parse import parse_qs, urlsplit

from .media import Cancelled, MediaError, Unsupported, tool
from .settings import DEFAULT

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def canonical_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("YouTubeの単一動画URLを入力してください。")
    try:
        url = urlsplit(value.strip())
        port = url.port
    except ValueError as error:
        raise ValueError("URLが不正です。") from error
    if (url.scheme != "https" or url.hostname not in YOUTUBE_HOSTS or
            url.username or url.password or port not in (None, 443) or url.fragment):
        raise ValueError("https://youtube.com または https://youtu.be の動画URLを入力してください。")
    parameters = parse_qs(url.query, keep_blank_values=True)
    if "list" in parameters:
        raise ValueError("プレイリストではなく単一動画のURLを指定してください。")
    if url.hostname == "youtu.be":
        video_id = url.path.removeprefix("/")
    elif url.path == "/watch":
        if len(parameters.get("v", [])) != 1:
            raise ValueError("プレイリストではなく単一動画のURLを指定してください。")
        video_id = parameters["v"][0]
    elif url.path.startswith(("/shorts/", "/live/")):
        video_id = url.path.split("/")[2]
        if url.path != f"/shorts/{video_id}" and url.path != f"/live/{video_id}":
            raise ValueError("YouTubeの単一動画URLを入力してください。")
    else:
        raise ValueError("YouTubeの単一動画URLを入力してください。")
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("動画IDが不正です。")
    return f"https://www.youtube.com/watch?v={video_id}"


def download_video(url, directory, progress=None, cancel=None, settings=DEFAULT):
    """Return (file path, user-facing title). Does not use browser cookies."""
    os.environ["YTDLP_NO_PLUGINS"] = "1"
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = canonical_url(url)
    directory = Path(directory)
    if shutil.disk_usage(directory).free < 128*1024**2:
        raise MediaError("動画の取得に必要な空き容量がありません。")
    started = time.monotonic()

    def check_cancel():
        if cancel and cancel.is_set():
            raise Cancelled("動画の取得を中止しました。")

    def check_info(info, *, incomplete=False):
        check_cancel()
        if incomplete:
            return None
        if info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
            return "ライブ配信は対象外です。"
        duration = info.get("duration")
        if duration is None or duration > settings.max_duration or duration <= 0:
            return "動画の長さが不明、または4時間を超えています。"
        size = info.get("filesize") or info.get("filesize_approx")
        if size and size > settings.max_upload_bytes:
            return "動画の取得サイズが4GiBを超えています。"
        return None

    def on_progress(data):
        check_cancel()
        if data.get("status") != "downloading":
            return
        received = data.get("downloaded_bytes", 0)
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        if received > settings.max_upload_bytes or (total and total > settings.max_upload_bytes):
            raise Unsupported("動画の取得サイズが4GiBを超えました。")
        if shutil.disk_usage(directory).free < 64*1024**2:
            raise MediaError("動画の取得中に空き容量が不足しました。")
        if progress:
            progress({"phase": "downloading", "percent": min(99, 100*received/total) if total else 0,
                      "received_bytes": received, "total_bytes": total,
                      "elapsed": time.monotonic()-started})

    options = {
        "format": "bestvideo[ext=mp4][vcodec^=avc1][height<=720]/"
                  "bestvideo[ext=webm][vcodec^=vp9][height<=720]/"
                  "best[ext=mp4][vcodec^=avc1][height<=720]",
        "outtmpl": str(directory / "input.%(ext)s"),
        "noplaylist": True, "ignoreconfig": True, "cachedir": False,
        "quiet": True, "no_warnings": True, "socket_timeout": 15,
        "retries": 1, "fragment_retries": 1, "extractor_retries": 1,
        "match_filter": check_info, "progress_hooks": [on_progress],
        "js_runtimes": {"quickjs": {"path": tool("qjs")}},
        "remote_components": [], "nooverwrites": True,
    }
    try:
        with YoutubeDL(options) as client:
            info = client.extract_info(url, download=True)
    except (Cancelled, MediaError):
        raise
    except DownloadError as error:
        raise MediaError("YouTube動画を取得できませんでした。公開状態、形式、接続状況を確認してください。") from error
    check_cancel()
    if info is None:
        raise Unsupported("この動画は取得対象外です。長さ、ライブ配信、形式を確認してください。")
    files = [path for path in directory.glob("input.*") if path.is_file() and not path.name.endswith(".part")]
    if len(files) != 1:
        raise MediaError("取得した動画ファイルを確認できませんでした。")
    path = files[0]
    if path.stat().st_size > settings.max_upload_bytes:
        raise Unsupported("動画の取得サイズが4GiBを超えました。")
    title = str(info.get("title") or info.get("id") or "YouTube動画")[:200]
    title = "".join(char for char in title if unicodedata.category(char) not in ("Cc", "Cf"))
    title = title.replace("/", "／").replace("\\", "＼").strip() or "YouTube動画"
    return path, title + path.suffix
