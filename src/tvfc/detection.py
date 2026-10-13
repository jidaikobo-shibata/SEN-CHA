"""Deterministic tile-based heuristic. Time is always in seconds, not frame counts."""
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .settings import DEFAULT, DEFAULT_SENSITIVITY


@dataclass
class Track:
    anchor: float | None = None
    direction: int = 0
    first_transition: float | None = None
    first_delta: float = 0.0
    flashes: deque = field(default_factory=deque)

    def step(self, value, time, delta, count, window):
        if self.anchor is None:
            self.anchor = value
            return None
        difference = value - self.anchor
        direction = 1 if difference >= delta else -1 if difference <= -delta else 0
        # Follow extrema while moving in the existing direction.
        if self.direction and (value - self.anchor) * self.direction > 0:
            self.anchor = value
        elif direction and direction != self.direction:
            magnitude = abs(difference)
            if self.first_transition is None:
                self.first_transition = time
                self.first_delta = magnitude
            else:
                self.flashes.append((self.first_transition, time,
                                     min(self.first_delta, magnitude)))
                self.first_transition = None
            self.direction = direction
            self.anchor = value
        while self.flashes and self.flashes[0][0] < time - window - 1e-7:
            self.flashes.popleft()
        if len(self.flashes) >= count:
            return {"start": self.flashes[0][0], "end": time,
                    "count": len(self.flashes),
                    "change": max(f[2] for f in self.flashes)}
        return None


class Detector:
    def __init__(self, sensitivity=DEFAULT_SENSITIVITY, settings=DEFAULT):
        if sensitivity not in ("standard", "high"):
            raise ValueError("感度が不正です")
        self.settings = settings
        self.profiles = [("standard", settings.standard_delta, settings.standard_count)]
        # Running standard independently guarantees that high includes its evidence.
        if sensitivity == "high":
            self.profiles.append(("high", settings.high_delta, settings.high_count))
        self.tracks = {}
        self.regions = []
        self.previous_values = None
        self.last_change = (0.0, 0.0)
        self.lut = np.where(np.arange(256) / 255 <= .04045,
                            np.arange(256) / 255 / 12.92,
                            ((np.arange(256) / 255 + .055) / 1.055)**2.4)

    def features(self, frame):
        height, width, _ = frame.shape
        rgb = self.lut[frame]
        luminance = rgb @ np.array([.2126, .7152, .0722])
        # Saturated-red intensity: intentionally a heuristic, not WCAG red threshold.
        total = rgb.sum(axis=2)
        fraction = np.divide(rgb[:, :, 0], total, out=np.zeros_like(total), where=total > 0)
        red = rgb[:, :, 0] * np.clip((fraction - .6) / .4, 0, 1)
        regions = [(0, 0, width, height, "画面全体")]
        for row in range(self.settings.rows):
            for col in range(self.settings.columns):
                x0, x1 = col * width // self.settings.columns, (col + 1) * width // self.settings.columns
                y0, y1 = row * height // self.settings.rows, (row + 1) * height // self.settings.rows
                if x1 > x0 and y1 > y0:
                    regions.append((x0, y0, x1, y1, f"上から{row+1}行目・左から{col+1}列目"))
        self.regions = regions
        values = []
        for x0, y0, x1, y1, _ in regions:
            values.append((float(luminance[y0:y1, x0:x1].mean()),
                           float(red[y0:y1, x0:x1].mean())))
        return values

    def step(self, frame, time):
        hits = []
        features = self.features(frame)
        if self.previous_values is not None:
            self.last_change = tuple(max(abs(current[channel] - previous[channel])
                                         for current, previous in zip(features, self.previous_values))
                                     for channel in (0, 1))
        self.previous_values = features
        for region, values in enumerate(features):
            for channel, value in enumerate(values):
                for profile, delta, count in self.profiles:
                    track = self.tracks.setdefault((region, channel, profile), Track())
                    hit = track.step(value, time, delta, count, self.settings.window_seconds)
                    if hit:
                        x0, y0, x1, y1, label = self.regions[region]
                        height, width = frame.shape[:2]
                        hit.update(region=region, label=label, profile=profile,
                                   kind="luminance" if channel == 0 else "red",
                                   box=[x0/width, y0/height, x1/width, y1/height],
                                   area_fraction=(x1-x0)*(y1-y0)/(width*height))
                        hits.append(hit)
        return hits
