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
        # USB serial often auto-resets the Arduino Uno, which needs boot time.
        time.sleep(2.5)
        self.serial.reset_input_buffer()
        self._write("PING\n")
        reply = self._wait_for(("PONG",), timeout=3.0)
        if reply != "PONG":
            self.close()
            raise RuntimeError(
                "Arduino tidak menjawab PING di %s. Pastikan sketch telah di-upload. Balasan: %r"
                % (port, reply)
            )
        print("[ARDUINO OK] %s pada %d baud; PONG diterima" % (port, baudrate), flush=True)

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
            ("STATUS IDLE", "STATUS OPENING", "STATUS CLOSING"),
            timeout=2.0,
        )
        return reply

    def feed_once(self):
        """Return True only if the Arduino acknowledged the command.
        Does not independently verify that the motor physically moved.
        """
        self._write("FEED\n")
        reply = self._wait_for(
            ("ACK FEED", "ERR BUSY", "ERR COOLDOWN", "ERR UNKNOWN_COMMAND"),
            timeout=2.0,
        )
        return reply == "ACK FEED", reply

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
            # Disarm before contacting the Arduino so failures cannot cause a burst.
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
