#!/usr/bin/env bash
set -euo pipefail
if [ "$(uname -m)" != "aarch64" ]; then
    echo 'PERINGATAN: Jalankan ini pada Raspberry Pi OS 64-bit (aarch64).'
fi
sudo apt update
sudo apt install -y python3-venv python3-pip v4l-utils usbutils unzip libgl1 libglib2.0-0
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --no-cache-dir ultralytics
.venv/bin/python - <<'PY'
import cv2, torch, ultralytics
print('OpenCV:', cv2.__version__)
print('PyTorch:', torch.__version__)
print('Ultralytics:', ultralytics.__version__)
PY
