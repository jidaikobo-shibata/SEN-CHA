import base64
from dataclasses import replace
from datetime import datetime, timezone
import io
import math
from pathlib import Path
import time

from PIL import Image

from . import __version__
from .detection import Detector
from .media import Cancelled, Frames, MediaError, inspect_video
from .settings import DEFAULT, DEFAULT_SENSITIVITY, LIMITATIONS, REGION_GRIDS
from .timeline import Timeline


def thumbnail(frame):
    buffer = io.BytesIO()
    Image.fromarray(frame).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def analyze(path, sensitivity=DEFAULT_SENSITIVITY, progress=None, cancel=None, settings=DEFAULT,
            region_mode=None):
    if region_mode is not None:
        if not isinstance(region_mode, str) or region_mode not in REGION_GRIDS:
            raise ValueError("検出領域の設定が不正です。")
        columns, rows = REGION_GRIDS[region_mode]
        settings = replace(settings, columns=columns, rows=rows)
    else:
        region_mode = next((name for name, grid in REGION_GRIDS.items()
                            if grid == (settings.columns, settings.rows)), "custom")
    started = time.monotonic()
    metadata = inspect_video(path, cancel, settings)
    detector = Detector(sensitivity, settings)
    candidates = []
    timeline = Timeline(metadata["duration"])
    detail_timeline = Timeline(metadata["duration"], bins=min(60000, max(1, math.ceil(metadata["duration"] / .05))))
    frames = 0
    last_progress = -1.0
    for timestamp, frame in Frames(path, metadata, cancel, settings):
        if cancel and cancel.is_set():
            raise Cancelled("解析を中止しました。")
        if timestamp > settings.max_duration:
            raise MediaError("実際の動画時間が上限を超えました。")
        hits = detector.step(frame, timestamp)
        timeline.add(timestamp, *detector.last_change)
        detail_timeline.add(timestamp, *detector.last_change)
        frames += 1
        if hits:
            start = min(h["start"] for h in hits)
            if not candidates or start > candidates[-1]["end"] + settings.merge_gap:
                if len(candidates) >= settings.max_candidates:
                    raise MediaError("候補数が上限1000件を超えました。動画を分割して確認してください。")
                candidates.append({"start": start, "end": timestamp, "evidence": {},
                                   "thumbnail": thumbnail(frame), "thumbnail_time": timestamp})
            candidate = candidates[-1]
            candidate["end"] = timestamp
            for hit in hits:
                key = f'{hit["region"]}:{hit["kind"]}:{hit["profile"]}'
                old = candidate["evidence"].get(key)
                if old is None or hit["count"] > old["count"] or hit["change"] > old["change"]:
                    candidate["evidence"][key] = hit
        if progress and timestamp - last_progress >= .25:
            progress({"frames": frames, "video_time": timestamp,
                      "duration": metadata["duration"],
                      "percent": min(99, 100*timestamp/metadata["duration"]),
                      "elapsed": time.monotonic()-started})
            last_progress = timestamp
    for candidate in candidates:
        candidate["evidence"] = list(candidate["evidence"].values())
    return {"schema_version": 1, "app_version": __version__, "status": "completed",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "filename": Path(path).name, "metadata": metadata,
            "settings": {**settings.export(), "sensitivity": sensitivity,
                         "region_mode": region_mode},
            "frames": frames, "elapsed": time.monotonic()-started,
            "candidates": candidates, "timeline": timeline.export(),
            "detail_timeline": detail_timeline.export(),
            "limitations": LIMITATIONS}
