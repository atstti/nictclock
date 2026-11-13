import time
from datetime import datetime
from zoneinfo import ZoneInfo


class TimeService:
    def __init__(self, wall=time.time, mono=time.monotonic_ns):
        self.mono = mono
        self.anchor_utc = wall()
        self.anchor_mono = mono()
        self.sample = None

    def now(self):
        return self.anchor_utc + (self.mono() - self.anchor_mono) / 1e9

    def synchronize(self, sample):
        self.anchor_utc, self.anchor_mono = sample.utc, sample.monotonic_ns
        self.sample = sample

    def age(self):
        return (
            None
            if self.sample is None
            else max(0, (self.mono() - self.sample.monotonic_ns) / 1e9)
        )

    def local(self, zone="Asia/Tokyo"):
        return datetime.fromtimestamp(self.now(), ZoneInfo(zone))


def hand_angles(hour, minute, second, microsecond=0, sweep=True):
    seconds = second + microsecond / 1e6
    return (
        (hour % 12 + minute / 60 + seconds / 3600) * 30,
        (minute + seconds / 60) * 6,
        (seconds if sweep else int(seconds)) * 6,
    )
