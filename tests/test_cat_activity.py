import unittest

from cat_activity import CatActivity


class CatActivityTests(unittest.TestCase):
    def test_no_motion_stays_standby(self):
        state = CatActivity()
        self.assertFalse(state.should_infer(False, now=100))
        self.assertEqual(state.snapshot(now=100)["mode"], "standby")

    def test_motion_only_probes_slowly(self):
        state = CatActivity(probe_seconds=3)
        self.assertTrue(state.should_infer(True, now=100))
        self.assertEqual(state.interval(0.4, now=100), 3)
        state.observe(False, now=100)
        self.assertEqual(state.snapshot(now=100)["mode"], "cat_probe")

    def test_cat_detection_enters_fast_mode(self):
        state = CatActivity(probe_seconds=3, active_hold=8)
        state.observe(True, now=100)
        self.assertTrue(state.should_infer(False, now=101))
        self.assertEqual(state.interval(0.4, now=101), 0.4)
        self.assertTrue(state.should_infer(False, now=108))
        self.assertFalse(state.should_infer(False, now=109))
        self.assertEqual(state.snapshot(now=109)["mode"], "standby")

    def test_invalid_values(self):
        with self.assertRaises(ValueError):
            CatActivity(probe_seconds=0)
        with self.assertRaises(ValueError):
            CatActivity(active_hold=0)


if __name__ == "__main__":
    unittest.main()
