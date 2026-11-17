#!/usr/bin/env python3
"""Smart Cat Feeder: test YOLO detector + age classifier on Raspberry Pi (CPU only).
No GPIO, serial, or servo control. See README.md.
"""
import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
DET = BASE / 'models' / 'detector_coco80.pt'
AGE = BASE / 'models' / 'cat_age_v4_hybrid_best.pt'


def build_parser():
    p = argparse.ArgumentParser(description='Uji model dan webcam Raspberry Pi 5; tidak mengaktifkan servo')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--selftest', action='store_true', help='Tes inferensi kedua model dengan gambar sintetis; bukan tes akurasi')
    group.add_argument('--image', type=Path, help='Uji dua model pada file foto asli')
    group.add_argument('--camera-only', action='store_true', help='Tes webcam tanpa memuat model AI')
    p.add_argument('--source', default='0', help='Indeks webcam (0/1/2) atau path /dev/video0')
    p.add_argument('--seconds', type=int, default=60, help='Durasi pengujian kamera dalam detik')
    p.add_argument('--conf', type=float, default=0.35, help='Ambang confidence deteksi kucing')
    p.add_argument('--imgsz', type=int, default=416, help='Resolusi input detektor')
    p.add_argument('--every', type=int, default=3, help='Inferensi setiap N frame webcam')
    p.add_argument('--display', action='store_true', help='Tampilkan jendela OpenCV bila desktop tersedia')
    p.add_argument('--output', type=Path, default=BASE / 'results', help='Direktori foto dan laporan hasil')
    return p


def open_camera(cv2, source):
    source = int(source) if source.isdecimal() else source
    if isinstance(source, int) and sys.platform.startswith('linux'):
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(source)
    else:
        cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f'Webcam tidak terbuka: {source}. Periksa ls /dev/video* dan v4l2-ctl --list-devices.')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


def load_models():
    from ultralytics import YOLO
    import torch
    torch.set_num_threads(2)
    for filename in (DET, AGE):
        if not filename.is_file():
            raise FileNotFoundError(f'Model tidak ditemukan: {filename}')
    t0 = time.perf_counter()
    det = YOLO(str(DET))
    age = YOLO(str(AGE))
    if det.task != 'detect' or age.task != 'classify':
        raise RuntimeError(f'Task model salah: det={det.task}, age={age.task}')
    if det.names.get(15) != 'cat':
        raise RuntimeError(f'Kelas COCO cat (15) tidak ditemukan: {det.names.get(15)}')
    expected = {'kitten_1_3', 'kitten_4_6', 'kitten_7_12'}
    if set(age.names.values()) != expected:
        raise RuntimeError(f'Kelas umur tidak sesuai: {age.names}')
    print(f'[MODEL OK] Detektor: {DET.name} (cat=15)', flush=True)
    print(f'[MODEL OK] Umur: {AGE.name} {age.names}', flush=True)
    print(f'[INFO] Memuat model: {time.perf_counter()-t0:.1f}s | mode CPU', flush=True)
    return det, age


def infer(det, age, frame, cv2, args):
    t0 = time.perf_counter()
    out = det.predict(frame, imgsz=args.imgsz, conf=args.conf,
                      classes=[15], device='cpu', verbose=False)[0]
    det_ms = 1000 * (time.perf_counter() - t0)
    image = frame.copy()
    found = []
    h, w = frame.shape[:2]
    if out.boxes is not None:
        for box in out.boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            x1, x2 = max(0, x1), min(w, x2)
            y1, y2 = max(0, y1), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            conf = float(box.conf[0])
            found.append((x1, y1, x2, y2, conf))
    age_label = None
    age_conf = None
    age_ms = 0.0
    # classify only the largest cat crop to limit Pi 5 CPU load
    if found and age is not None:
        biggest = max(found, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
        x1, y1, x2, y2, _ = biggest
        crop = frame[y1:y2, x1:x2]
        if crop.size:
            t1 = time.perf_counter()
            pred = age.predict(crop, imgsz=320, device='cpu', verbose=False)[0]
            age_ms = 1000 * (time.perf_counter() - t1)
            if pred.probs is not None:
                index = int(pred.probs.top1)
                age_label = age.names[index]
                age_conf = float(pred.probs.top1conf)
    for (x1, y1, x2, y2, c) in found:
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.putText(image, f'CAT {c:.2f}', (x1, max(18, y1-8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 0), 2)
    if age_label is not None:
        cv2.putText(image, f'Age estimate: {age_label} ({age_conf:.2f})',
                    (12, min(h-15, 30)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 220, 20), 2)
    return image, {
        'cat_count': len(found), 'age_estimate': age_label,
        'age_confidence': age_conf,
        'detection_ms': round(det_ms, 2), 'age_ms': round(age_ms, 2),
    }


def main():
    args = build_parser().parse_args()
    if args.every < 1 or args.seconds < 1 or not (0 < args.conf < 1):
        raise SystemExit('--every dan --seconds harus >=1; --conf antara 0 dan 1')
    import cv2
    import numpy as np
    args.output.mkdir(parents=True, exist_ok=True)
    print('[INFO] Raspberry Pi CPU test; servo dan Arduino tidak diakses.', flush=True)
    det = age = None
    if not args.camera_only:
        det, age = load_models()
    if args.selftest:
        synthetic = np.full((480, 640, 3), 127, dtype=np.uint8)
        annotated, result = infer(det, age, synthetic, cv2, args)
        # test classification explicitly, even if synthetic image has no cat
        t0 = time.perf_counter()
        prediction = age.predict(synthetic, imgsz=320, device='cpu', verbose=False)[0]
        if prediction.probs is None:
            raise RuntimeError('Classifier gagal menghasilkan probabilities')
        print(f'[SELFTEST OK] Detector + classifier inference berhasil. ' 
              f'Detector={result["detection_ms"]:.1f}ms, classifier={1000*(time.perf_counter()-t0):.1f}ms.', flush=True)
        print('[CATATAN] Gambar sintetis bukan kucing: label prediksi tidak bermakna.', flush=True)
        return
    if args.image is not None:
        frame = cv2.imread(str(args.image))
        if frame is None:
            raise RuntimeError(f'Gambar tidak dapat dibaca: {args.image}')
        annotated, result = infer(det, age, frame, cv2, args)
        output = args.output / 'hasil_foto.jpg'
        if not cv2.imwrite(str(output), annotated):
            raise RuntimeError('Gagal menyimpan foto output')
        print('[PHOTO RESULT]', json.dumps(result, ensure_ascii=False), flush=True)
        print(f'[SAVED] {output}', flush=True)
        return
    cap = open_camera(cv2, args.source)
    print(f'[CAMERA OK] source={args.source}, resolution=' 
          f'{cap.get(cv2.CAP_PROP_FRAME_WIDTH):.0f}x{cap.get(cv2.CAP_PROP_FRAME_HEIGHT):.0f}', flush=True)
    started = time.monotonic()
    next_report = started + 5
    total_frames = inferences = cat_positive = errors = 0
    timings = []
    estimates = Counter()
    last_frame = None
    try:
        while time.monotonic() - started < args.seconds:
            ok, frame = cap.read()
            if not ok:
                errors += 1
                if errors >= 10:
                    raise RuntimeError('10 frame berturut-turut gagal dibaca dari webcam')
                continue
            errors = 0
            total_frames += 1
            last_frame = frame
            if not args.camera_only and total_frames % args.every == 0:
                annotated, outcome = infer(det, age, frame, cv2, args)
                last_frame = annotated
                inferences += 1
                timings.append(outcome['detection_ms'] + outcome['age_ms'])
                if outcome['cat_count']:
                    cat_positive += 1
                    if outcome['age_estimate'] is not None:
                        estimates[outcome['age_estimate']] += 1
                    print(f'[CAT] n={outcome["cat_count"]}, ' 
                          f'est_age={outcome["age_estimate"]}, conf={outcome["age_confidence"]}, '
                          f'det={outcome["detection_ms"]:.0f}ms, age={outcome["age_ms"]:.0f}ms', flush=True)
            if args.display:
                cv2.imshow('Smart Cat Feeder (NO SERVO)', last_frame)
                if cv2.waitKey(1) & 0xff in (27, ord('q')):
                    break
            now = time.monotonic()
            if now >= next_report:
                print(f'[STATUS] frames={total_frames} inferensi={inferences} '
                      f'frames_dengan_kucing={cat_positive} '
                      f'elapsed={now-started:.0f}s', flush=True)
                next_report = now + 5
    except KeyboardInterrupt:
        print('[STOP] KeyboardInterrupt', flush=True)
    finally:
        cap.release()
        if args.display:
            cv2.destroyAllWindows()
    elapsed = max(time.monotonic()-started, 0.001)
    report = {
        'camera_source': args.source, 'frames_read': total_frames,
        'frames_with_inference': inferences, 'frames_cat_detected': cat_positive,
        'age_estimates': dict(estimates), 'duration_sec': round(elapsed, 2),
        'capture_fps': round(total_frames/elapsed, 2),
        'avg_total_inference_ms': round(statistics.mean(timings), 2) if timings else None,
        'servo_activated': False,
    }
    if last_frame is not None:
        cv2.imwrite(str(args.output / 'last_frame.jpg'), last_frame)
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('[SELESAI]', json.dumps(report, ensure_ascii=False), flush=True)
    print(f'[HASIL] {args.output / "summary.json"} dan last_frame.jpg', flush=True)
    if total_frames == 0:
        raise SystemExit('Pengujian gagal: webcam tidak menghasilkan frame')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'[ERROR] {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        raise SystemExit(1)
