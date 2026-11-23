"""USB serial bridge: Raspberry Pi YOLO11 cat detections -> Arduino Uno Servo.
Communication is disabled unless --arduino-port is supplied to live_cam.py.
No cat-age model is used. Commands are bounded, rate-limited, and acknowledged.
"""
import time


class ArduinoBridge:
    def __init__(self, port, baudrate=115200):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError(
                "pyserial belum terpasang. Jalankan .venv/bin/python -m pip install pyserial"
            ) from exc

        self.port = port
        self.serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.15,
            write_timeout=1.0,
        )


        time.sleep(1.0)
        last_reply = None
        handshake_deadline = time.monotonic() + 12.0
        attempt = 0
        try:
            while time.monotonic() < handshake_deadline:
                attempt += 1
                print("[SERIAL] PING percobaan %d..." % attempt, flush=True)
                self._write("PING\n")
                reply = self._wait_for(("PONG",), timeout=1.25)
                if reply == "PONG":
                    print("[ARDUINO OK] %s pada %d baud; PONG diterima" %
                          (port, baudrate), flush=True)
                    break
                if reply:
                    last_reply = reply
            else:
                raise RuntimeError(
                    "Arduino tidak menjawab PING setelah beberapa percobaan di %s. "
                    "Pastikan sketch terbaru, baudrate 115200, port benar, "
                    "dan Arduino tidak terus-menerus restart. Balasan terakhir: %r"
                    % (port, last_reply)
                )
        except Exception:
            self.close()
            raise

    def _write(self, message):
        self.serial.write(message.encode("ascii"))
        self.serial.flush()

    def _wait_for(self, expected, timeout):
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            line = self.serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            last = line
            print("[ARDUINO]", line, flush=True)
            if line in expected:
                return line
        return last

    def ping(self):
        self._write("PING\n")
        return self._wait_for(("PONG",), timeout=2.0) == "PONG"

    def status(self):
        self._write("STATUS\n")
        reply = self._wait_for(
            ("STATUS IDLE", "STATUS OPENING", "STATUS CLOSING", "STATUS EMERGENCY"),
            timeout=2.0,
        )
        return reply

    def emergency(self):
        """Display Emergency on LCD and inhibit automatic FEED until RESET.
        This is a software-only demo, NOT a physical emergency stop.
        """
        self._write("EMERGENCY\n")
        return self._wait_for(("ACK EMERGENCY",), timeout=2.0) == "ACK EMERGENCY"

    def reset_emergency(self):
        self._write("RESET\n")
        return self._wait_for(("ACK RESET",), timeout=2.0) == "ACK RESET"

    def feed_once(self):
        """Return True only if the Arduino acknowledged the command.
        Does not independently verify that the motor physically moved.
        """
        self._write("FEED\n")
        reply = self._wait_for(
            ("ACK FEED", "ERR BUSY", "ERR COOLDOWN", "ERR EMERGENCY",
             "ERR HOPPER_LOW", "ERR BOWL_FULL", "ERR BOWL_UNKNOWN", "ERR UNKNOWN_COMMAND"),
            timeout=2.0,
        )
        return reply == "ACK FEED", reply

    def cooldown_status(self, timeout=2.0):
        """Read remaining automatic cooldown seconds from Arduino, no servo motion."""
        self._write("COOLDOWN_STATUS\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            if line.startswith("COOLDOWN "):
                try:
                    return int(line.split()[1])
                except (ValueError, IndexError):
                    raise RuntimeError("Balasan COOLDOWN tidak valid: %r" % line)
            print("[ARDUINO]", line, flush=True)
            if line == "ERR UNKNOWN_COMMAND":
                raise RuntimeError(
                    "Firmware belum mendukung COOLDOWN_STATUS. Upload sketch Arduino terbaru."
                )
        raise RuntimeError("Arduino tidak membalas COOLDOWN_STATUS; cek firmware/port.")

    def food_status(self, timeout=2.0):
        """Read IR sensor and confirmed food state; never commands servo movement."""
        self._write("FOOD_STATUS\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            if line.startswith("FOOD_STATUS "):
                return line
            print("[ARDUINO]", line, flush=True)
            if line == "ERR UNKNOWN_COMMAND":
                raise RuntimeError(
                    "Firmware Arduino lama belum mendukung FOOD_STATUS. Upload sketch terbaru."
                )
        raise RuntimeError("Arduino tidak membalas FOOD_STATUS; cek firmware/port.")

    def hopper_status(self, timeout=2.0):
        self._write("HOPPER_STATUS\n")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", errors="replace").strip()
            if line.startswith("HOPPER_STATUS "):
                return line
            if line:
                print("[ARDUINO]", line, flush=True)
        raise RuntimeError("Arduino tidak membalas HOPPER_STATUS.")

    def scan_i2c(self, timeout=8.0):
        """Scan Arduino Uno I2C bus (A4/A5). Does not actuate the servo."""
        self.serial.reset_input_buffer()
        self._write("I2C_SCAN\n")
        found = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.serial.readline().decode("ascii", errors="replace").strip()
            if not line:
                continue
            print("[ARDUINO]", line, flush=True)
            if line.startswith("I2C_FOUND 0x"):
                found.append(line.split()[-1])
            elif line.startswith("I2C_SCAN_DONE "):
                return found
            elif line == "ERR UNKNOWN_COMMAND":
                raise RuntimeError(
                    "Sketch Arduino belum memiliki perintah I2C_SCAN. Upload firmware terbaru."
                )
        raise RuntimeError("I2C scan tidak selesai; cek kabel SDA/SCL dan suplai LCD.")

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()


class CatGate:
    """Only issue FEED after consecutive cat detections.
    Requires cat absence before re-arming and enforces host-side cooldown.
    Arduino separately enforces its own cooldown.
    """

    def __init__(self, bridge, stable_hits=3, absence_seconds=5.0,
                 cooldown_seconds=60.0, bench_test=False):
        if stable_hits < 2 or absence_seconds < 1:
            raise ValueError("Minimum safety limits: hits>=2 and absence>=1s")
        if cooldown_seconds < 5:
            raise ValueError("Cooldown minimum 5 seconds in bench test")
        if cooldown_seconds < 30 and not bench_test:
            raise ValueError("Cooldown <30 s hanya untuk mode --bench-test tanpa makanan")
        self.bridge = bridge
        self.bench_test = bench_test
        self.stable_hits = stable_hits
        self.absence_seconds = absence_seconds
        self.cooldown_seconds = cooldown_seconds
        self.hit_streak = 0
        self.absent_since = None
        self.armed = True
        self.last_attempt = float("-inf")
        self.commands_accepted = 0
        self.last_response = "NONE"

    def observe(self, cat_detected, now=None):
        now = time.monotonic() if now is None else now

        if not cat_detected:
            self.hit_streak = 0
            if self.absent_since is None:
                self.absent_since = now
            if not self.armed and now - self.absent_since >= self.absence_seconds:
                self.armed = True
                self.last_response = "REARMED"
            return

        self.absent_since = None
        self.hit_streak += 1

        if (
            self.armed
            and self.hit_streak >= self.stable_hits
            and now - self.last_attempt >= self.cooldown_seconds
        ):

            self.armed = False
            self.last_attempt = now
            accepted, response = self.bridge.feed_once()
            self.last_response = response or "NO_RESPONSE"
            if accepted:
                self.commands_accepted += 1
                print("[TRIGGER] Kucing terdeteksi stabil -> Arduino ACK FEED", flush=True)
            else:
                print("[TRIGGER] Arduino menolak/tidak menjawab: %s" % self.last_response, flush=True)

    def snapshot(self):
        return {
            "enabled": True,
            "bench_test": self.bench_test,
            "armed": self.armed,
            "cat_detection_streak": self.hit_streak,
            "commands_accepted": self.commands_accepted,
            "last_serial_response": self.last_response,
            "physical_servo_motion_verified": False,
            "cooldown_seconds": self.cooldown_seconds,
        }
