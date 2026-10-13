"""Local-only decoding with bounded queues and display timestamps from showinfo."""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

import numpy as np

from .settings import DEFAULT


class MediaError(Exception):
    pass


class Unsupported(MediaError):
    pass


class Cancelled(MediaError):
    pass


def tool(name):
    suffix = ".exe" if os.name == "nt" else ""
    roots = [Path(__file__).resolve().parents[2] / "vendor" / "bin"]
    if hasattr(sys, "_MEIPASS"):
        roots.insert(0, Path(sys._MEIPASS) / "vendor" / "bin")
    for root in roots:
        path = root / (name + suffix)
        if path.is_file():
            return str(path)
    import shutil
    found = shutil.which(name)
    if not found:
        raise MediaError(f"{name}が見つかりません。配布物または開発手順を確認してください。")
    return found


def creation_flags():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


INPUT_OPTIONS = ["-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi"]


def inspect_video(path, cancel=None, settings=DEFAULT):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise MediaError("通常の動画ファイルを指定してください。")
    args = [tool("ffprobe"), "-v", "error", *INPUT_OPTIONS, "-select_streams", "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,color_transfer,color_primaries,color_space,avg_frame_rate:stream_side_data=rotation,side_data_type:format=duration",
            "-of", "json", str(path)]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **creation_flags())
    started = time.monotonic()
    try:
        while True:
            if cancel and cancel.is_set():
                raise Cancelled("解析を中止しました。")
            try:
                stdout, stderr = process.communicate(timeout=.2)
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() - started > settings.idle_timeout:
                    raise MediaError("動画情報の取得がタイムアウトしました。")
        if process.returncode:
            raise MediaError("動画を読み取れません。破損または未対応の形式です。")
        data = json.loads(stdout)
        streams = data.get("streams", [])
        if not streams:
            raise Unsupported("動画ストリームがありません。")
        stream = streams[0]
        width, height = stream.get("width", 0), stream.get("height", 0)
        if not (0 < width <= settings.max_dimension and 0 < height <= settings.max_dimension):
            raise Unsupported("解像度が未対応です（最大8192ピクセル／辺）。")
        transfer = stream.get("color_transfer", "unknown")
        primaries = stream.get("color_primaries", "unknown")
        color_space = stream.get("color_space", "unknown")
        if transfer not in ("unknown", "bt709", "smpte170m", "gamma22", "gamma28", "iec61966-2-1", "bt470m", "bt470bg"):
            raise Unsupported(f"未対応の伝達特性です: {transfer}（SDRのみ対応）")
        if primaries not in ("unknown", "bt709", "smpte170m", "bt470bg", "bt470m"):
            raise Unsupported(f"未対応の色域です: {primaries}")
        if color_space not in ("unknown", "bt709", "smpte170m", "bt470bg", "gbr", "smpte240m", "fcc"):
            raise Unsupported(f"未対応の色変換です: {color_space}")
        formats8 = {"yuv420p", "yuvj420p", "yuv422p", "yuvj422p", "yuv444p", "yuvj444p",
                    "yuv410p", "yuv411p", "yuv440p", "yuvj440p", "gray", "gray8",
                    "rgb24", "bgr24", "rgba", "bgra", "argb", "abgr", "pal8",
                    "nv12", "nv21", "uyvy422", "yuyv422", "0rgb", "rgb0", "bgr0", "0bgr", "gbrp"}
        if stream.get("pix_fmt", "") not in formats8:
            raise Unsupported("初期版は8ビットSDR動画に対応します。")
        if any("Mastering display" in item.get("side_data_type", "") or
               "Content light" in item.get("side_data_type", "")
               for item in stream.get("side_data_list", [])):
            raise Unsupported("HDRに関連するメタデータがあるため初期版では扱いません。")
        duration = float(data.get("format", {}).get("duration", 0))
        if not np.isfinite(duration) or duration <= 0 or duration > settings.max_duration:
            raise Unsupported("動画の長さが不明、または4時間を超えています。")
        # Explicitly do not autorotate; report coordinates in encoded image space.
        rotations = [s.get("rotation", 0) for s in stream.get("side_data_list", [])]
        if any(abs(float(r)) % 360 for r in rotations):
            raise Unsupported("回転情報付き動画は初期版では未対応です。向きを確定して書き出してください。")
        warnings = []
        if "unknown" in (transfer, primaries, color_space):
            warnings.append("色情報の一部が不明です。FFmpegのSDR推定とsRGB近似を使用しました。")
        return {"width": width, "height": height, "duration": duration,
                "codec": stream.get("codec_name"), "pixel_format": stream.get("pix_fmt"),
                "color_transfer": transfer, "color_primaries": primaries,
                "color_space": color_space, "warnings": warnings,
                "average_frame_rate": stream.get("avg_frame_rate"),
                "size_bytes": path.stat().st_size}
    finally:
        stop(process)


class Frames:
    def __init__(self, path, metadata, cancel=None, settings=DEFAULT):
        self.cancel = cancel
        self.settings = settings
        self.width = min(settings.width, metadata["width"])
        self.height = max(1, round(metadata["height"] * self.width / metadata["width"]))
        self.closing = threading.Event()
        self.timestamps = queue.Queue(16)
        self.images = queue.Queue(4)
        self.errors = []
        args = [tool("ffmpeg"), "-hide_banner", "-nostdin", "-v", "info",
                "-xerror", *INPUT_OPTIONS, "-noautorotate", "-threads", "2",
                "-i", str(Path(path).resolve()), "-map", "0:v:0", "-an", "-sn", "-dn",
                "-vf", f"scale={self.width}:{self.height}:flags=area,format=rgb24,showinfo",
                "-filter_threads", "1", "-fps_mode", "passthrough", "-threads", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
        self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        bufsize=0, **creation_flags())
        self.threads = [threading.Thread(target=self._stderr, daemon=True),
                        threading.Thread(target=self._stdout, daemon=True)]
        for thread in self.threads:
            thread.start()

    def _put(self, target, value):
        while not self.closing.is_set():
            try:
                target.put(value, timeout=.1)
                return
            except queue.Full:
                pass

    def _stderr(self):
        pattern = re.compile(r"\bn:\s*(\d+)\s+pts:.*?pts_time:([\d.eE+\-]+)")
        try:
            for raw in self.process.stderr:
                line = raw.decode("utf-8", errors="replace")
                match = pattern.search(line) if "showinfo" in line else None
                if match:
                    self._put(self.timestamps, (int(match[1]), float(match[2])))
                elif "error" in line.lower() or "invalid" in line.lower():
                    self.errors.append(line[-500:])
                    self.errors = self.errors[-10:]
        finally:
            self._put(self.timestamps, None)

    def _stdout(self):
        length = self.width * self.height * 3
        try:
            while not self.closing.is_set():
                buffer = bytearray()
                while len(buffer) < length:
                    chunk = self.process.stdout.read(length-len(buffer))
                    if not chunk:
                        break
                    buffer.extend(chunk)
                if not buffer:
                    break
                if len(buffer) != length:
                    self.errors.append("フレームが途中で途切れました。")
                    break
                self._put(self.images, buffer)
        finally:
            self._put(self.images, None)

    def _get(self, target):
        start = time.monotonic()
        while True:
            if self.cancel and self.cancel.is_set():
                raise Cancelled("解析を中止しました。")
            try:
                return target.get(timeout=.1)
            except queue.Empty:
                if time.monotonic() - start > self.settings.idle_timeout:
                    raise MediaError("動画の読み込みが停止しました。")

    def __iter__(self):
        index, origin, previous = 0, None, None
        try:
            while True:
                raw = self._get(self.images)
                timestamp = self._get(self.timestamps)
                if raw is None:
                    if timestamp is not None:
                        raise MediaError("フレームと時刻の数が一致しません。")
                    break
                if timestamp is None or timestamp[0] != index:
                    raise MediaError("フレームと時刻を対応付けられません。")
                pts = timestamp[1]
                if not np.isfinite(pts) or (previous is not None and pts <= previous):
                    raise Unsupported("フレーム時刻が重複または逆行しています。")
                origin = pts if origin is None else origin
                previous = pts
                yield pts-origin, np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3)
                index += 1
            self.process.wait(timeout=5)
            if self.process.returncode != 0 or self.errors:
                raise MediaError("動画を最後まで正常に読み取れませんでした。")
            if not index:
                raise MediaError("解析できるフレームがありません。")
        finally:
            self.close()

    def close(self):
        self.closing.set()
        stop(self.process)
        for thread in self.threads:
            thread.join(timeout=2)
        self.process.stdout.close()
        self.process.stderr.close()
