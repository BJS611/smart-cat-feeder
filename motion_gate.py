import time


class MotionGate:
    def __init__(self, threshold=20, min_fraction=0.025, hold_seconds=15.0,
                 sample_seconds=0.5, warmup_seconds=3.0):
        if threshold <= 0 or not 0 < min_fraction <= 1:
            raise ValueError("Invalid motion sensitivity")
        if hold_seconds <= 0 or sample_seconds <= 0 or warmup_seconds < 0:
            raise ValueError("Invalid motion timing")
        self.threshold = threshold
        self.min_fraction = min_fraction
        self.hold_seconds = hold_seconds
        self.sample_seconds = sample_seconds
        self.warmup_seconds = warmup_seconds
        self.started_at = time.monotonic()
        self.last_sample = float("-inf")
        self.last_motion = None
        self.previous = None
        self.active = False
        self.changed_fraction = 0.0

    def observe(self, frame, cv2, now=None):
        import numpy as np

        now = time.monotonic() if now is None else now
        if now - self.last_sample < self.sample_seconds:
            return self.active
        self.last_sample = now
        small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if self.previous is not None and now - self.started_at >= self.warmup_seconds:
            previous_mean = float(np.mean(self.previous))
            current_mean = float(np.mean(gray))
            shift = current_mean - previous_mean
            adjusted = np.clip(self.previous.astype(np.float32) + shift, 0, 255)
            delta = np.abs(gray.astype(np.float32) - adjusted)
            self.changed_fraction = float(np.count_nonzero(delta > self.threshold)) / delta.size
            if self.changed_fraction >= self.min_fraction:
                self.last_motion = now
        self.previous = gray
        self.active = self.last_motion is not None and now - self.last_motion <= self.hold_seconds
        return self.active

    def snapshot(self):
        return {
            "enabled": True,
            "active": self.active,
            "changed_fraction": round(self.changed_fraction, 4),
            "hold_seconds": self.hold_seconds,
            "sample_seconds": self.sample_seconds,
        }
