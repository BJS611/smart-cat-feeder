#!/usr/bin/env python3
"""Manual USB serial test for Arduino Uno bench setup.
Without --feed it only sends PING and STATUS; no servo motion.
"""
import argparse
import time
from cat_servo_bridge import ArduinoBridge


def main():
    parser = argparse.ArgumentParser(description="Arduino UNO serial servo test")
    parser.add_argument("--port", default="/dev/ttyACM0")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--feed", action="store_true",
        help="EXPLICITLY actuate one servo cycle; bench only without food"
    )
    actions.add_argument(
        "--lcd-demo", action="store_true",
        help="Show Idle -> Emergency (4 s) -> Idle on LCD; does not move servo"
    )
    args = parser.parse_args()
    bridge = ArduinoBridge(args.port)
    try:
        print("[PING]", "OK" if bridge.ping() else "FAILED", flush=True)
        print("[STATUS]", bridge.status(), flush=True)
        if args.lcd_demo:
            print("[LCD] Arduino should display: Idle", flush=True)
            time.sleep(2)
            if not bridge.emergency():
                raise RuntimeError("Arduino belum mendukung EMERGENCY; upload sketch LCD terbaru")
            print("[LCD] Arduino should display: Emergency (4 seconds)", flush=True)
            time.sleep(4)
            if not bridge.reset_emergency():
                raise RuntimeError("Arduino tidak menjawab RESET")
            print("[LCD] Arduino should display: Idle", flush=True)
            print("[STATUS]", bridge.status(), flush=True)
        elif args.feed:
            print("[WARNING] Mengirim FEED: servo bisa langsung bergerak!", flush=True)
            accepted, response = bridge.feed_once()
            print("[RESULT] acknowledged=%s response=%s" % (accepted, response), flush=True)
        else:
            print("[SAFE] Tidak mengirim perintah FEED. Tambahkan --feed hanya untuk tes servo tanpa beban.")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
