#!/usr/bin/env python3
"""Live MJPEG webcam + YOLO11 cat detection + experimental cat age estimation.
Runs locally on Raspberry Pi 5; browse remotely via SSH port forwarding.
No servo, Arduino, GPIO or feeding commands are used.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pi5_ai_test import load_models, open_camera


class Shared:
    def __init__(self):
        self.condition = threading.Condition()
        self.stop = threading.Event()
        self.raw = None
        self.jpeg = None
        self.sequence = 0
        self.boxes = []
        self.age = None
        self.age_conf = None
        self.det_ms = 0.0
        self.age_ms = 0.0
        self.inferences = 0
        self.frames = 0
        self.error = None


def capture_worker(state, cap, cv2):
    last_print = time.monotonic()
    try:
        while not state.stop.is_set():
            ok, frame = cap.read()
            if not ok:
                state.error = "Webcam tidak menghasilkan frame; cek /dev/video*."
                break

            with state.condition:
                state.raw = frame.copy()
                boxes = list(state.boxes)
                age, age_conf = state.age, state.age_conf
                state.frames += 1

            for x1, y1, x2, y2, confidence in boxes:
                cv2.rectangle(frame, (x1, y1), (x2, y2), (30, 210, 40), 2)
                cv2.putText(
                    frame, "CAT %.2f" % confidence, (x1, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (30, 210, 40), 2
                )
            if age is not None:
                cv2.putText(
                    frame, "Estimasi: %s (%.2f)" % (age, age_conf),
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 225, 255), 2
                )
            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            )
            if ok:
                with state.condition:
                    state.jpeg = encoded.tobytes()
                    state.sequence += 1
                    state.condition.notify_all()
            # Prevent excessive CPU use on very fast webcams.
            time.sleep(0.025)
            if time.monotonic() - last_print >= 10:
                print("[CAMERA] frames=%d, inferensi=%d, kucing=%d" %
                      (state.frames, state.inferences, len(boxes)), flush=True)
                last_print = time.monotonic()
    except Exception as exc:
        state.error = "Capture error: %s" % exc
        print("[ERROR]", state.error, flush=True)
    finally:
        state.stop.set()
        with state.condition:
            state.condition.notify_all()
        cap.release()


def inference_worker(state, detector, classifier, args):
    while not state.stop.is_set():
        start = time.perf_counter()
        with state.condition:
            frame = None if state.raw is None else state.raw.copy()
        if frame is None:
            state.stop.wait(0.1)
            continue
        try:
            h, w = frame.shape[:2]
            result = detector.predict(
                frame, imgsz=args.imgsz, conf=args.conf,
                classes=[15], device="cpu", verbose=False
            )[0]
            det_ms = (time.perf_counter() - start) * 1000
            boxes = []
            if result.boxes is not None:
                for b in result.boxes:
                    x1, y1, x2, y2 = map(int, b.xyxy[0].tolist())
                    x1, x2 = max(0, x1), min(w - 1, x2)
                    y1, y2 = max(0, y1), min(h - 1, y2)
                    if x2 > x1 and y2 > y1:
                        boxes.append((x1, y1, x2, y2, float(b.conf[0])))

            age_label = age_conf = None
            age_ms = 0.0
            if boxes:
                biggest = max(boxes, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
                x1, y1, x2, y2, _ = biggest
                t1 = time.perf_counter()
                age_result = classifier.predict(
                    frame[y1:y2, x1:x2], imgsz=320,
                    device="cpu", verbose=False
                )[0]
                age_ms = (time.perf_counter() - t1) * 1000
                if age_result.probs is not None:
                    age_label = classifier.names[int(age_result.probs.top1)]
                    age_conf = float(age_result.probs.top1conf)

            with state.condition:
                state.boxes = boxes
                state.age = age_label
                state.age_conf = age_conf
                state.det_ms = round(det_ms, 1)
                state.age_ms = round(age_ms, 1)
                state.inferences += 1
        except Exception as exc:
            state.error = "Inference error: %s" % exc
            print("[ERROR]", state.error, flush=True)
            state.stop.set()
            with state.condition:
                state.condition.notify_all()
            break

        # Minimum delay between inference passes, not FPS.
        state.stop.wait(max(0, args.interval - (time.perf_counter() - start)))


HTML = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Cat Feeder — Live AI</title>
<style>
body{background:#101827;color:#edf2f8;font:16px system-ui,sans-serif;
  max-width:900px;margin:30px auto;padding:0 16px}
img{display:block;width:100%;max-width:800px;background:#000;border-radius:10px}
pre{white-space:pre-wrap;background:#1d293a;padding:15px;border-radius:10px}
small{color:#b5c3d6}
</style></head><body>
<h2>Smart Cat Feeder · Live Camera</h2>
<p><small>Raspberry Pi 5 · YOLO11n + YOLO11s-cls · Tidak menggerakkan servo</small></p>
<img src="/stream.mjpg" alt="Live webcam">
<h3>Status</h3><pre id="status">Menghubungkan...</pre>
<p><small>Label usia hanya perkiraan AI. Jangan gunakan untuk menentukan porsi makan.</small></p>
<script>
async function refresh(){try{
 const r=await fetch('/status',{cache:'no-store'});
 document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2);
}catch(e){document.getElementById('status').textContent='Koneksi terputus: '+e;}}
refresh();setInterval(refresh,2000);
</script></body></html>"""


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/status":
                with state.condition:
                    payload = {
                        "camera_frames": state.frames,
                        "inferences": state.inferences,
                        "detected_cats": len(state.boxes),
                        "age_estimate": state.age,
                        "age_confidence": state.age_conf,
                        "detection_ms": state.det_ms,
                        "age_ms": state.age_ms,
                        "error": state.error,
                        "servo_activated": False,
                    }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/stream.mjpg":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seen = -1
                try:
                    while not state.stop.is_set():
                        with state.condition:
                            state.condition.wait_for(
                                lambda: state.sequence != seen or state.stop.is_set(),
                                timeout=5
                            )
                            if state.stop.is_set():
                                break
                            seen, img = state.sequence, state.jpeg
                        if img is None:
                            continue
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\n"
                            + ("Content-Length: %d\r\n\r\n" % len(img)).encode()
                            + img + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
            else:
                self.send_error(404)

        def log_message(self, fmt, *args):
            # Avoid logging each request every few seconds.
            if self.path.split("?", 1)[0] not in ("/status", "/stream.mjpg"):
                super().log_message(fmt, *args)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Live webcam + YOLO via browser SSH tunnel")
    parser.add_argument("--source", default="0", help="Webcam index /dev/videoN")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--conf", type=float, default=0.40)
    parser.add_argument("--interval", type=float, default=0.4,
                        help="Minimum gap between AI passes in seconds")
    args = parser.parse_args()
    if not (1 <= args.port <= 65535 and 0 < args.conf < 1
            and args.imgsz >= 32 and args.interval >= 0):
        parser.error("Port/confidence/resolusi/interval tidak valid")

    import cv2
    state = Shared()
    det, age = load_models()
    cap = open_camera(cv2, args.source)
    print("[CAMERA OK] source=%s" % args.source, flush=True)
    capture = threading.Thread(
        target=capture_worker, args=(state, cap, cv2), daemon=True
    )
    infer = threading.Thread(
        target=inference_worker, args=(state, det, age, args), daemon=True
    )
    capture.start()
    infer.start()

    # Localhost-only: access over SSH tunnel, not exposed on network.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    server.daemon_threads = True
    print("[LIVE] http://127.0.0.1:%d" % args.port, flush=True)
    print("[INFO] Dari laptop: ssh -N -L %d:127.0.0.1:%d yolo@yolo11.local" %
          (args.port, args.port), flush=True)
    print("[INFO] Ctrl+C untuk berhenti. Servo tidak digunakan.", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\n[STOP] Live camera berhenti", flush=True)
    finally:
        state.stop.set()
        with state.condition:
            state.condition.notify_all()
        server.server_close()
        capture.join(timeout=2)


if __name__ == "__main__":
    main()
