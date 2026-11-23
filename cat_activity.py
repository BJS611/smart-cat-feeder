import time


class CatActivity:
    def __init__(self, probe_seconds=2.0, active_hold=10.0):
        if probe_seconds < 0.2 or active_hold < 1:
            raise ValueError("Invalid cat activity timing")
        self.probe_seconds = probe_seconds
        self.active_hold = active_hold
        self.last_cat = None
        self.mode = "standby"

    def is_recent(self, now=None):
        now = time.monotonic() if now is None else now
        return self.last_cat is not None and now - self.last_cat <= self.active_hold

    def should_infer(self, motion_active, now=None):
        recent = self.is_recent(now)
        self.mode = "cat_active" if recent else "cat_probe" if motion_active else "standby"
        return recent or motion_active

    def observe(self, cat_detected, now=None):
        now = time.monotonic() if now is None else now
        if cat_detected:
            self.last_cat = now
        self.mode = "cat_active" if self.is_recent(now) else "cat_probe"

    def interval(self, active_interval, now=None):
        return active_interval if self.is_recent(now) else self.probe_seconds

    def snapshot(self, now=None):
        return {
            "enabled": True,
            "mode": self.mode,
            "cat_recent": self.is_recent(now),
            "probe_seconds": self.probe_seconds,
            "active_hold": self.active_hold,
        }
