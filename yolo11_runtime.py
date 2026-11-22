#!/usr/bin/env python3
"""Shared YOLO11n detection-only runtime for Raspberry Pi 5.
No age classifier, servo, Arduino or GPIO access.
"""
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent
MODEL_PATH = BASE / "models" / "yolo11.pt"
OFFICIAL_WEIGHT = "yolo11n.pt"


def load_detector():
    from ultralytics import YOLO
    import torch
    torch.set_num_threads(2)

    if not MODEL_PATH.is_file():
        print("[MODEL] models/yolo11.pt belum ada; mengunduh YOLO11n resmi...", flush=True)
        pretrained = YOLO(OFFICIAL_WEIGHT)
        source = Path(pretrained.ckpt_path).resolve()
        if not source.is_file():
            raise FileNotFoundError("Checkpoint YOLO11n hasil unduhan tidak ditemukan: %s" % source)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = MODEL_PATH.with_suffix(".pt.part")
        shutil.copyfile(source, temp)
        temp.replace(MODEL_PATH)
        print("[MODEL] Disimpan: %s" % MODEL_PATH, flush=True)

    model = YOLO(str(MODEL_PATH))
    if model.task != "detect":
        raise RuntimeError("models/yolo11.pt bukan checkpoint deteksi: task=%r" % model.task)
    print("[MODEL OK] %s | task=detect | %d kelas" %
          (MODEL_PATH, len(model.names)), flush=True)
    return model


def open_camera(cv2, source, width=640, height=480, fps=None, fourcc=None):
    """Open the camera with optional low-bandwidth webcam format settings.

    Caller can request MJPG for a USB webcam, but actual negotiated format is
    reported separately (some V4L2 devices silently ignore unsupported modes).
    The defaults preserve pi5_ai_test.py's existing camera behavior.
    """
    source = int(source) if str(source).isdecimal() else source
    if isinstance(source, int):
        cap = cv2.VideoCapture(source, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(source)
    else:
        cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError("Webcam gagal dibuka: %s. Cek v4l2-ctl --list-devices" % source)
    if fourcc and fourcc.upper() not in ("AUTO", "NONE"):
        if len(fourcc) != 4:
            cap.release()
            raise ValueError("Camera FOURCC must be 4 letters, e.g. MJPG")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc.upper()))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if fps is not None:
        cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def predict_boxes(model, frame, imgsz=320, conf=0.4, cat_only=False):
    result = model.predict(
        frame, device="cpu", imgsz=imgsz, conf=conf, verbose=False,
        classes=[15] if cat_only else None
    )[0]
    h, w = frame.shape[:2]
    boxes = []
    if result.boxes is not None:
        for box in result.boxes:
            x1, y1, x2, y2 = (int(x) for x in box.xyxy[0].tolist())
            x1, x2 = max(0, x1), min(w - 1, x2)
            y1, y2 = max(0, y1), min(h - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            cls = int(box.cls[0])
            name = model.names.get(cls, str(cls))
            boxes.append((x1, y1, x2, y2, cls, name, float(box.conf[0])))
    return boxes


def draw_boxes(cv2, frame, boxes):
    for x1, y1, x2, y2, cls, name, confidence in boxes:
        color = (45, 220, 45) if cls == 15 else (0, 210, 255)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, "%s %.2f" % (name, confidence),
                    (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 2)
    return frame
