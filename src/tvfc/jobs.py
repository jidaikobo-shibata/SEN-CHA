import json
import multiprocessing as mp
import os
from pathlib import Path
import queue
import secrets
import shutil
import signal
import tempfile
import threading
import time

from .analysis import analyze
from .media import Cancelled, MediaError, Unsupported
from .settings import REGION_GRIDS
from .youtube import canonical_url, download_video


def worker(path, filename, sensitivity, region_mode, directory, events, cancel,
           source_url=None, retain_input=False):
    def progress(value):
        try:
            events.put_nowait(value)
        except queue.Full:
            pass
    outcome = {}
    try:
        report = analyze(path, sensitivity, progress, cancel, region_mode=region_mode)
        report["filename"] = filename
        if source_url:
            report["source_url"] = source_url
        if cancel.is_set():
            raise Cancelled("解析を中止しました。")
        (Path(directory) / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        outcome = {"state": "completed", "message": "解析が完了しました。"}
        if retain_input:
            outcome["playback_file"] = Path(path).name
    except Cancelled as error:
        outcome = {"state": "cancelled", "message": str(error)}
    except Unsupported as error:
        outcome = {"state": "unsupported", "message": str(error)}
    except (MediaError, OSError, ValueError) as error:
        outcome = {"state": "failed", "message": str(error)}
    except Exception:
        outcome = {"state": "failed", "message": "解析中に予期しないエラーが発生しました。"}
    finally:
        if not (retain_input and outcome.get("state") == "completed"):
            Path(path).unlink(missing_ok=True)
        try:
            (Path(directory) / "outcome.json").write_text(json.dumps(outcome), encoding="utf-8")
        except OSError:
            pass
        events.cancel_join_thread()


def youtube_worker(url, sensitivity, region_mode, directory, events, cancel):
    if os.name == "posix":
        os.setsid()
    def progress(value):
        try:
            events.put_nowait(value)
        except queue.Full:
            pass
    try:
        path, filename = download_video(url, directory, progress, cancel)
        try:
            events.put({"phase": "running", "percent": 0, "elapsed": 0}, timeout=2)
        except queue.Full:
            pass
        worker(path, filename, sensitivity, region_mode, directory, events, cancel,
               source_url=url, retain_input=True)
    except Cancelled as error:
        outcome = {"state": "cancelled", "message": str(error)}
    except Unsupported as error:
        outcome = {"state": "unsupported", "message": str(error)}
    except (MediaError, OSError, ValueError) as error:
        outcome = {"state": "failed", "message": str(error)}
    except Exception:
        outcome = {"state": "failed", "message": "動画の取得中に予期しないエラーが発生しました。"}
    else:
        return
    (Path(directory) / "outcome.json").write_text(json.dumps(outcome), encoding="utf-8")
    events.cancel_join_thread()


def stop_download_process(process):
    if not process or not process.is_alive():
        return
    if os.name == "posix":
        try:
            if os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, signal.SIGTERM)
                return
        except ProcessLookupError:
            return
    process.terminate()


class Jobs:
    ACTIVE = {"uploading", "downloading", "running", "cancelling"}

    def __init__(self):
        self.context = mp.get_context("spawn")
        self.lock = threading.RLock()
        self.directory = None
        self.process = None
        self.events = None
        self.cancel_event = None
        self.state = "idle"
        self.message = "動画を選択してください。"
        self.progress = {}
        self.report = None
        self.playback_path = None
        self.playback_token = None
        self.started = None
        self.upload_id = None
        self.upload_expected = 0
        self.upload_written = 0
        self.upload_updated = None
        self.upload_filename = None
        self.upload_sensitivity = None
        self.upload_region_mode = None

    def _clean(self, preserve_playback=False):
        if self.directory and not preserve_playback:
            shutil.rmtree(self.directory)
            self.directory = None
            self.playback_path = None
            self.playback_token = None
        if self.events:
            self.events.close()
            self.events = None

    def begin_upload(self):
        with self.lock:
            self.poll()
            if self.state in self.ACTIVE:
                raise ValueError("別の処理が進行中です。")
            self._clean()
            self.directory = tempfile.mkdtemp(prefix="tvfc-")
            self.cancel_event = self.context.Event()
            self.report = None
            self.progress = {}
            self.process = None
            self.started = time.monotonic()
            self.upload_id = secrets.token_hex(16)
            self.upload_written = 0
            self.upload_updated = time.monotonic()
            self.state, self.message = "uploading", "動画を端末内の作業領域へコピーしています。"
            return Path(self.directory) / "input.video"

    def begin_youtube(self, url, sensitivity, region_mode="fine"):
        url = canonical_url(url)
        if sensitivity not in ("standard", "high"):
            raise ValueError("感度が不正です。")
        if not isinstance(region_mode, str) or region_mode not in REGION_GRIDS:
            raise ValueError("検出領域の設定が不正です。")
        with self.lock:
            self.poll()
            if self.state in self.ACTIVE:
                raise ValueError("別の処理が進行中です。")
            self._clean()
            self.directory = tempfile.mkdtemp(prefix="tvfc-")
            self.report = None
            self.progress = {}
            self.started = time.monotonic()
            self.cancel_event = self.context.Event()
            self.events = self.context.Queue(maxsize=16)
            self.process = self.context.Process(target=youtube_worker,
                args=(url, sensitivity, region_mode, self.directory, self.events, self.cancel_event))
            try:
                self.process.start()
            except Exception:
                self.process = None
                self._clean()
                raise
            self.state, self.message = "downloading", "YouTubeから動画を取得しています。"

    def upload_failed(self, message, cancelled=False):
        with self.lock:
            self.state = "cancelled" if cancelled else "failed"
            self.message = message
            self._clean()

    def launch(self, path, filename, sensitivity, region_mode="fine"):
        with self.lock:
            if not isinstance(region_mode, str) or region_mode not in REGION_GRIDS:
                raise ValueError("検出領域の設定が不正です。")
            if self.cancel_event.is_set():
                self.upload_failed("コピーを中止しました。", True)
                return
            self.events = self.context.Queue(maxsize=16)
            self.process = self.context.Process(target=worker, args=(str(path), filename, sensitivity, region_mode,
                                                self.directory, self.events, self.cancel_event))
            self.process.start()
            self.state, self.message = "running", "動画を解析しています。"

    def poll(self):
        with self.lock:
            if self.state == "uploading" and time.monotonic()-self.upload_updated > 120:
                self.upload_failed("コピーの操作が途切れたため、一時データを削除しました。")
            if self.events:
                try:
                    while True:
                        self.progress = self.events.get_nowait()
                        if self.state != "cancelling" and (
                            self.progress.get("phase") == "running" or
                            self.state == "downloading" and "frames" in self.progress
                        ):
                            self.state, self.message = "running", "動画を解析しています。"
                except queue.Empty:
                    pass
            if self.process and not self.process.is_alive():
                self.process.join()
                try:
                    outcome = json.loads((Path(self.directory)/"outcome.json").read_text(encoding="utf-8"))
                    self.state, self.message = outcome["state"], outcome["message"]
                    if self.state == "completed":
                        self.report = json.loads((Path(self.directory)/"report.json").read_text(encoding="utf-8"))
                        playback_name = outcome.get("playback_file")
                        if playback_name and Path(playback_name).name == playback_name:
                            path = Path(self.directory) / playback_name
                            if path.is_file() and not path.is_symlink():
                                self.playback_path = path
                                self.playback_token = secrets.token_urlsafe(32)
                except (OSError, ValueError, KeyError):
                    if self.cancel_event and self.cancel_event.is_set():
                        self.state, self.message = "cancelled", "処理を中止しました。"
                    else:
                        self.state, self.message = "failed", "処理プロセスが正常に終了しませんでした。"
                self.process.close()
                self.process = None
                self._clean(preserve_playback=self.playback_path is not None)
            return {"state": self.state, "message": self.message, "progress": self.progress,
                    "elapsed": time.monotonic()-self.started if self.started and self.state in self.ACTIVE else self.progress.get("elapsed", 0),
                    "candidate_count": len(self.report["candidates"]) if self.report else None}

    def cancel(self):
        with self.lock:
            if self.state in self.ACTIVE:
                self.cancel_event.set()
                downloading = self.state == "downloading"
                self.state, self.message = "cancelling", "中止して作業領域を片付けています。"
                if downloading and self.process and self.process.is_alive():
                    stop_download_process(self.process)
                if self.process is None:
                    self.upload_failed("コピーを中止しました。", True)

    def close(self):
        self.cancel()
        if self.process:
            self.process.join(timeout=10)
            if self.process.is_alive():
                # Worker is cancellation-aware. A stuck worker must not be called complete.
                self.message = "解析プロセスの終了を待っています。"
                self.process.join(timeout=60)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=3)
            if not self.process.is_alive():
                self.poll()
        if not self.process:
            self._clean()
