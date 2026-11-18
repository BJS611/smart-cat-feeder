#!/usr/bin/env python3
"""Manual USB serial test for Arduino Uno bench setup.
Without --feed it only sends PING and STATUS; no servo motion.
"""
import argparse
from cat_servo_bridge import ArduinoBridge


def main():
    parser = argparse.ArgumentParser(description="Arduino UNO serial servo test")
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument(
        "--feed", action="store_true",
        help="EXPLICITLY actuate a single servo cycle (bench test only, no food)"
    )
    args = parser.parse_args()
    bridge = ArduinoBridge(args.port)
    try:
        print("[PING]", "OK" if bridge.ping() else "FAILED", flush=True)
        print("[STATUS]", bridge.status(), flush=True)
        if args.feed:
            print("[WARNING] Mengirim FEED: servo bisa langsung bergerak!", flush=True)
            accepted, response = bridge.feed_once()
            print("[RESULT] acknowledged=%s response=%s" % (accepted, response), flush=True)
        else:
            print("[SAFE] Tidak mengirim perintah FEED. Tambahkan --feed hanya untuk tes servo tanpa beban.")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
