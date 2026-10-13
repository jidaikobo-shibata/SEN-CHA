"""Bounded overview of frame-to-frame changes; not a hazard score."""


class Timeline:
    def __init__(self, duration, bins=1200):
        self.duration = duration
        self.bins = bins
        self.values = {}

    def add(self, timestamp, luminance, red):
        index = min(self.bins - 1, max(0, int(timestamp / self.duration * self.bins)))
        old = self.values.get(index, (0.0, 0.0))
        self.values[index] = (max(old[0], luminance), max(old[1], red))

    def export(self):
        return [{"time": round((index + .5) * self.duration / self.bins, 6),
                 "luminance": round(values[0], 4), "red": round(values[1], 4)}
                for index, values in sorted(self.values.items())]
