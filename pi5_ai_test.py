#!/usr/bin/env python3
"""Single-model YOLO11 detection test for Raspberry Pi 5.
No age classifier, no old detector checkpoint, no GPIO or servo.
"""
import argparse
import json
import statistics
import time
from pathlib import Path

from yolo11_runtime import draw_boxes, load_detector, open_camera, predict_boxes

BASE = Path(__file__).resolve().parent


def parser_args():
    parser = argparse.ArgumentParser(description="YOLO11-only webcam tester")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--selftest", action="store_true")
    group.add_argument("--image", type=Path)
    group.add_argument("--camera-only", action="store_true")
    parser.add_argument("--source", default="0")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--conf", type=float, default=0.4)
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--every", type=int, default=3)
    parser.add_argument("--cat-only", action="store_true", help="Filter only COCO cat (15)")
    parser.add_argument("--display", action="store_true", help="OpenCV window requires local desktop")
    parser.add_argument("--output", type=Path, default=BASE / "results")
    args = parser.parse_args()
    if args.every < 1 or args.seconds < 1 or not (0 < args.conf < 1):
        parser.error("--every / --seconds must be positive; 0 < --conf < 1")
    return args


def run_inference(model, frame, args, cv2):
    t0 = time.perf_counter()
    boxes = predict_boxes(
        model, frame, imgsz=args.imgsz, conf=args.conf,
        cat_only=args.cat_only
    )
    elapsed = round((time.perf_counter() - t0) * 1000, 1)
    output = draw_boxes(cv2, frame.copy(), boxes)
    return output, boxes, elapsed


def main():
    args = parser_args()
    import cv2
    import numpy as np

    args.output.mkdir(parents=True, exist_ok=True)
    print("[INFO] YOLO11-only CPU test. Tidak memakai model usia, servo, atau Arduino.", flush=True)
    model = None if args.camera_only else load_detector()

    if args.selftest:
        synthetic = np.full((480, 640, 3), 127, dtype=np.uint8)
        _, boxes, dt = run_inference(model, synthetic, args, cv2)
        print("[SELFTEST OK] YOLO11 detection inference berhasil, %.1fms. Hasil sintetis tidak mewakili akurasi." % dt, flush=True)
        return

    if args.image:
        frame = cv2.imread(str(args.image))
        if frame is None:
            raise RuntimeError("Tidak bisa membaca gambar: %s" % args.image)
        annotated, boxes, dt = run_inference(model, frame, args, cv2)
        filename = args.output / "hasil_foto.jpg"
        if not cv2.imwrite(str(filename), annotated):
            raise RuntimeError("Gagal menyimpan gambar %s" % filename)
        print("[PHOTO] %s" % json.dumps({
            "detections": [{"class": b[5], "confidence": round(b[6], 3)} for b in boxes],
            "inference_ms": dt
        }, ensure_ascii=False), flush=True)
        print("[SAVED]", filename, flush=True)
        return

    cap = open_camera(cv2, args.source)
    print("[CAMERA OK] source=%s resolution=%.0fx%.0f" % (
        args.source, cap.get(cv2.CAP_PROP_FRAME_WIDTH),
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    ), flush=True)

    started = time.monotonic()
    report_at = started + 5
    frames = inferences = cat_positive = read_errors = 0
    timings = []
    last_frame = None
    labels = {}

    try:
        while time.monotonic() - started < args.seconds:
            ok, frame = cap.read()
            if not ok:
                read_errors += 1
                if read_errors >= 10:
                    raise RuntimeError("Kamera gagal membaca 10 frame berturut-turut")
                continue

            read_errors = 0
            frames += 1
            last_frame = frame
            if model is not None and frames % args.every == 0:
                last_frame, boxes, dt = run_inference(model, frame, args, cv2)
                inferences += 1
                timings.append(dt)
                if any(b[4] == 15 for b in boxes):
                    cat_positive += 1
                for b in boxes:
                    labels[b[5]] = labels.get(b[5], 0) + 1
                if boxes:
                    print("[DETECT] " +
                          ", ".join("%s:%.2f" % (b[5], b[6]) for b in boxes) +
                          " | %.1fms" % dt, flush=True)

            if args.display:
                cv2.imshow("YOLO11 Single Model (NO SERVO)", last_frame)
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
            now = time.monotonic()
            if now >= report_at:
                print("[STATUS] frames=%d inferensi=%d frames_dengan_kucing=%d" %
                      (frames, inferences, cat_positive), flush=True)
                report_at = now + 5

    except KeyboardInterrupt:
        print("[STOP] Ctrl+C", flush=True)
    finally:
        cap.release()
        if args.display:
            cv2.destroyAllWindows()

    elapsed = max(time.monotonic() - started, 0.001)
    if last_frame is not None:
        cv2.imwrite(str(args.output / "last_frame.jpg"), last_frame)

    summary = {
        "model": "models/yolo11.pt",
        "mode": "camera-only" if args.camera_only else ("cat-only" if args.cat_only else "all-classes"),
        "camera_source": args.source,
        "frames_read": frames,
        "frames_with_inference": inferences,
        "frames_cat_detected": cat_positive,
        "class_detection_counts": labels,
        "duration_sec": round(elapsed, 2),
        "capture_fps": round(frames / elapsed, 2),
        "avg_inference_ms": round(statistics.mean(timings), 1) if timings else None,
        "age_model_loaded": False,
        "servo_activated": False,
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print("[SELESAI] " + json.dumps(summary, ensure_ascii=False), flush=True)
    print("[HASIL] " + str(args.output / "summary.json"), flush=True)
    if frames == 0:
        raise RuntimeError("Webcam tidak menghasilkan frame")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import sys
        print("[ERROR] %s: %s" % (type(exc).__name__, exc), file=sys.stderr, flush=True)
        sys.exit(1)
