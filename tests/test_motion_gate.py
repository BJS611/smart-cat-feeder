import unittest

import cv2
import numpy as np

from motion_gate import MotionGate


class MotionGateTests(unittest.TestCase):
    def test_steady_frames_do_not_activate(self):
        gate = MotionGate(sample_seconds=0.1, warmup_seconds=0)
        base = np.zeros((120, 160, 3), dtype=np.uint8)
        self.assertFalse(gate.observe(base, cv2, now=100))
        self.assertFalse(gate.observe(base.copy(), cv2, now=101))
        self.assertFalse(gate.active)

    def test_object_motion_activates_and_expires(self):
        gate = MotionGate(sample_seconds=0.1, hold_seconds=3, warmup_seconds=0)
        base = np.zeros((120, 160, 3), dtype=np.uint8)
        moved = base.copy()
        moved[20:80, 40:110] = 220
        self.assertFalse(gate.observe(base, cv2, now=100))
        self.assertTrue(gate.observe(moved, cv2, now=101))
        self.assertTrue(gate.observe(moved, cv2, now=102))
        self.assertFalse(gate.observe(moved, cv2, now=105))

    def test_uniform_brightness_change_is_compensated(self):
        gate = MotionGate(sample_seconds=0.1, warmup_seconds=0)
        baseline = np.full((120, 160, 3), 80, dtype=np.uint8)
        brighter = np.full((120, 160, 3), 115, dtype=np.uint8)
        gate.observe(baseline, cv2, now=100)
        self.assertFalse(gate.observe(brighter, cv2, now=101))

    def test_invalid_config_rejected(self):
        with self.assertRaises(ValueError):
            MotionGate(min_fraction=0)
        with self.assertRaises(ValueError):
            MotionGate(sample_seconds=0)


if __name__ == "__main__":
    unittest.main()
