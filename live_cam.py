#!/usr/bin/env python3
"""Browser live camera: ONE YOLO11 object detector only.
No age model. Optional USB serial Arduino Uno servo bench test.
Access localhost:8767 via SSH tunnel from your laptop.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from yolo11_runtime import draw_boxes, load_detector, open_camera, predict_boxes
from cat_servo_bridge import ArduinoBridge, CatGate


class State:
    def __init__(self):
        self.lock = threading.Condition()
        self.stop = threading.Event()
        self.raw = None
        self.jpeg = None
        self.seq = 0
        self.boxes = []
        self.frame_count = 0
        self.inferences = 0
        self.det_ms = None
        self.error = None
        self.serial_info = {"enabled": False, "reason": "Arduino belum diaktifkan"}


def camera_worker(state, cap, cv2):
    try:
        last_report = time.monotonic()
        while not state.stop.is_set():
            ok, frame = cap.read()
            if not ok:
                state.error = "Webcam tidak mengirim frame."
                break
            with state.lock:
                state.raw = frame.copy()
                boxes = list(state.boxes)
                state.frame_count += 1
            draw_boxes(cv2, frame, boxes)
            encoded_ok, encoded = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            if encoded_ok:
                with state.lock:
                    state.jpeg = encoded.tobytes()
                    state.seq += 1
                    state.lock.notify_all()
            if time.monotonic() - last_report > 10:
                print("[CAMERA] frames=%d, inferensi=%d, objek=%d" %
                      (state.frame_count, state.inferences, len(boxes)), flush=True)
                last_report = time.monotonic()
            time.sleep(0.03)
    except Exception as exc:
        state.error = "Camera error: %s" % exc
        print("[ERROR]", state.error, flush=True)
    finally:
        state.stop.set()
        with state.lock:
            state.lock.notify_all()
        cap.release()


def inference_worker(state, model, args, cat_gate=None):
    while not state.stop.is_set():
        with state.lock:
            frame = None if state.raw is None else state.raw.copy()
        if frame is None:
            state.stop.wait(0.1)
            continue
        begin = time.perf_counter()
        try:
            boxes = predict_boxes(
                model, frame, imgsz=args.imgsz,
                conf=args.conf, cat_only=args.cat_only
            )
            dt_ms = (time.perf_counter() - begin) * 1000.0
            if cat_gate is not None:
                cat_gate.observe(any(b[4] == 15 for b in boxes))
            with state.lock:
                state.boxes = boxes
                state.inferences += 1
                state.det_ms = round(dt_ms, 1)
                if cat_gate is not None:
                    state.serial_info = cat_gate.snapshot()
        except Exception as exc:
            state.error = "Inference error: %s" % exc
            print("[ERROR]", state.error, flush=True)
            state.stop.set()
            with state.lock:
                state.lock.notify_all()
            return
        state.stop.wait(max(0, args.interval - (time.perf_counter() - begin)))


PAGE = """<!doctype html><html lang="id"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Cat Feeder — YOLO11 Live</title><style>
body{background:#111827;color:#eef2ff;font:16px system-ui,sans-serif;
max-width:940px;margin:24px auto;padding:0 14px}
img{display:block;width:100%;max-width:900px;border-radius:10px;background:#000}
pre{white-space:pre-wrap;background:#1e293b;border-radius:10px;padding:12px}
small{color:#cbd5e1}
</style></head><body>
<h2>YOLO11 · Live Object Detection</h2>
<p><small>Satu model YOLO11. Arduino/servo hanya aktif bila argumen --arduino-port diberikan. Belum memakai timbangan pakan.</small></p>
<img src="/stream.mjpg" alt="Webcam live YOLO11">
<h3>Status</h3><pre id="status">Menghubungkan...</pre>
<script>
async function update(){try{
let r=await fetch('/status',{cache:'no-store'});
document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2);
}catch(e){document.getElementById('status').textContent='Disconnected: '+e;}}
update();setInterval(update,2000);
</script></body></html>"""


def make_handler(state, cat_only):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                data = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif path == "/status":
                with state.lock:
                    detections = [
                        {"class": b[5], "confidence": round(b[6], 3)}
                        for b in state.boxes
                    ]
                    data = {
                        "model": "models/yolo11.pt",
                        "mode": "cat-only" if cat_only else "all-classes",
                        "camera_frames": state.frame_count,
                        "inferences": state.inferences,
                        "detection_ms": state.det_ms,
                        "detections": detections,
                        "error": state.error,
                        "age_classifier_loaded": False,
                        "arduino_serial": dict(state.serial_info),
                        "physical_servo_motion_verified": False,
                    }
                payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            elif path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seen = -1
                try:
                    while not state.stop.is_set():
                        with state.lock:
                            state.lock.wait_for(
                                lambda: state.seq != seen or state.stop.is_set(),
                                timeout=5
                            )
                            if state.stop.is_set():
                                break
                            seen = state.seq
                            frame = state.jpeg
                        if frame is None:
                            continue
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n" +
                            ("Content-Length: %d\r\n\r\n" % len(frame)).encode() +
                            frame + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            else:
                self.send_error(404)

        def log_message(self, fmt, *values):
            if self.path.split("?", 1)[0] not in ("/status", "/stream.mjpg"):
                super().log_message(fmt, *values)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="YOLO11 live stream, single detection model")
    parser.add_argument("--source", default="0", help="Camera index, /dev/videoN, or stream URL")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--arduino-port", default=None,
                        help="Aktifkan pengiriman FEED ke Arduino Uno melalui USB serial, contoh /dev/ttyACM0")
    parser.add_argument("--stable-hits", type=int, default=3,
                        help="Deteksi cat berturut-turut sebelum FEED (default 3)")
    parser.add_argument("--rearm-seconds", type=float, default=5.0,
                        help="Wajib tidak ada cat selama N detik sebelum bisa trigger lagi")
    parser.add_argument("--cooldown-seconds", type=float, default=60.0,
                        help="Minimum detik antar perintah (Arduino juga punya cooldown sendiri)")
    parser.add_argument("--cat-only", action="store_true",
                        help="Only show COCO class 'cat' (15); default all 80 classes")
    args = parser.parse_args()
    if not (1 <= args.port <= 65535 and 0 < args.conf < 1
            and args.imgsz >= 32 and args.interval >= 0
            and args.stable_hits >= 2 and args.rearm_seconds >= 1
            and args.cooldown_seconds >= 30):
        parser.error("Port, confidence, resolusi, atau interval tidak valid")

    import cv2
    model = load_detector()
    cap = open_camera(cv2, args.source)
    print("[CAMERA OK] %s" % args.source, flush=True)
    state = State()
    bridge = None
    gate = None
    if args.arduino_port:
        print("[SAFETY] MODE SERVO BENCH TEST: jangan pasang hopper atau makanan sebelum ada timbangan.", flush=True)
        bridge = ArduinoBridge(args.arduino_port)
        gate = CatGate(bridge, stable_hits=args.stable_hits,
                       absence_seconds=args.rearm_seconds,
                       cooldown_seconds=args.cooldown_seconds)
        state.serial_info = gate.snapshot()
    else:
        print("[SAFE] Arduino tidak aktif. Untuk mengirim FEED, tentukan --arduino-port.", flush=True)
    capture = threading.Thread(
        target=camera_worker, args=(state, cap, cv2), daemon=True
    )
    infer = threading.Thread(
        target=inference_worker, args=(state, model, args, gate), daemon=True
    )
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port), make_handler(state, args.cat_only)
    )
    server.daemon_threads = True
    capture.start()
    infer.start()
    print("[LIVE] http://127.0.0.1:%d/" % args.port, flush=True)
    print("[INFO] SSH tunnel dari laptop: ssh -N -L %d:127.0.0.1:%d yolo@yolo11.local" %
          (args.port, args.port), flush=True)
    print("[MODEL] YOLO11 detect saja; Arduino %s. Stop dengan Ctrl+C." %
          ("AKTIF" if bridge else "OFF"), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\n[STOP] Live YOLO11 dimatikan", flush=True)
    finally:
        state.stop.set()
        with state.lock:
            state.lock.notify_all()
        server.server_close()
        capture.join(timeout=2)
        if bridge is not None:
            bridge.close()


if __name__ == "__main__":
    main()
