"""Unit tests for detection gate (does not need Arduino or model weights)."""
import unittest

from cat_servo_bridge import CatGate


class FakeBridge:
    def __init__(self, accepted=True):
        self.calls = 0
        self.accepted = accepted

    def feed_once(self):
        self.calls += 1
        return self.accepted, "ACK FEED" if self.accepted else "ERR COOLDOWN"


class GateTests(unittest.TestCase):
    def test_requires_consecutive_positive_detections(self):
        bridge = FakeBridge()
        gate = CatGate(bridge, stable_hits=3)
        gate.observe(True, now=0)
        gate.observe(True, now=1)
        self.assertEqual(bridge.calls, 0)
        gate.observe(False, now=2)
        gate.observe(True, now=3)
        gate.observe(True, now=4)
        self.assertEqual(bridge.calls, 0)
        gate.observe(True, now=5)
        self.assertEqual(bridge.calls, 1)
        self.assertEqual(gate.commands_accepted, 1)

    def test_no_repeat_during_continuous_cat_presence(self):
        bridge = FakeBridge()
        gate = CatGate(bridge, stable_hits=3)
        for i in range(100):
            gate.observe(True, now=i)
        self.assertEqual(bridge.calls, 1)

    def test_absence_and_cooldown_required_for_retrigger(self):
        bridge = FakeBridge()
        gate = CatGate(bridge, stable_hits=3, absence_seconds=5, cooldown_seconds=60)
        for now in [1, 2, 3]:
            gate.observe(True, now=now)
        self.assertEqual(bridge.calls, 1)
        gate.observe(False, now=20)
        gate.observe(False, now=25)
        for now in [26, 27, 28]:
            gate.observe(True, now=now)
        self.assertEqual(bridge.calls, 1)  # cooldown
        gate.observe(False, now=61)
        gate.observe(False, now=66)
        for now in [67, 68, 69]:
            gate.observe(True, now=now)
        self.assertEqual(bridge.calls, 2)

    def test_short_cooldown_requires_explicit_bench_mode(self):
        bridge = FakeBridge()
        with self.assertRaises(ValueError):
            CatGate(bridge, stable_hits=3, cooldown_seconds=5)
        gate = CatGate(bridge, stable_hits=3, absence_seconds=5,
                       cooldown_seconds=5, bench_test=True)
        for now in [0, 1, 2]:
            gate.observe(True, now=now)
        self.assertEqual(bridge.calls, 1)
        gate.observe(False, now=3)
        gate.observe(False, now=8)
        for now in [9, 10, 11]:
            gate.observe(True, now=now)
        self.assertEqual(bridge.calls, 2)

    def test_rejected_command_is_not_repeated_without_absence(self):
        bridge = FakeBridge(accepted=False)
        gate = CatGate(bridge, stable_hits=3)
        for now in range(75):
            gate.observe(True, now=now)
        self.assertEqual(bridge.calls, 1)
        self.assertEqual(gate.commands_accepted, 0)


if __name__ == "__main__":
    unittest.main()
