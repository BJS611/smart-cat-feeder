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
    actions.add_argument(
        "--i2c-scan", action="store_true",
        help="Scan Arduino Uno A4/A5 for connected I2C devices; no servo movement"
    )
    actions.add_argument(
        "--button-monitor", action="store_true",
        help="Monitor Arduino serial events while pressing the physical D2 button"
    )
    actions.add_argument(
        "--food-monitor", action="store_true",
        help="Monitor raw infrared sensor and confirmed food state (no servo movement)"
    )
    args = parser.parse_args()
    bridge = ArduinoBridge(args.port)
    try:
        print("[PING]", "OK" if bridge.ping() else "FAILED", flush=True)
        print("[STATUS]", bridge.status(), flush=True)
        if args.food_monitor:
            print("[IR] Pantau sensor D6. Tutupi/hilangkan pakan di depan sensor.", flush=True)
            print("[IR] Ctrl+C untuk berhenti. Tidak ada perintah FEED.", flush=True)
            try:
                while True:
                    print("[IR]", bridge.food_status(), flush=True)
                    time.sleep(0.7)
            except KeyboardInterrupt:
                print("\n[IR] Monitor selesai.", flush=True)
        elif args.button_monitor:
            print("[BUTTON] Tekan tombol D2 ke GND. Servo bergerak dari tombol, bukan Python.", flush=True)
            print("[BUTTON] Ctrl+C untuk berhenti.", flush=True)
            try:
                while True:
                    message = bridge.serial.readline().decode("ascii", errors="replace").strip()
                    if message:
                        print("[ARDUINO]", message, flush=True)
            except KeyboardInterrupt:
                print("\n[BUTTON] Monitor selesai.", flush=True)
        elif args.i2c_scan:
            print("[I2C] Memindai bus A4(SDA) / A5(SCL)...", flush=True)
            devices = bridge.scan_i2c()
            if devices:
                print("[I2C OK] Alamat ditemukan: %s" % ", ".join(devices), flush=True)
                print("[I2C] Firmware LCD saat ini memakai 0x27.", flush=True)
            else:
                print("[I2C] TIDAK ADA alamat ditemukan. Cek VCC, GND, SDA=A4, SCL=A5 dan backpack LCD.", flush=True)
        elif args.lcd_demo:
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
