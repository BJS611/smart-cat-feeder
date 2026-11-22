#!/usr/bin/env bash
set -euo pipefail

if [ "$(uname -m)" != "aarch64" ]; then
  echo "ERROR: Installer ini untuk Raspberry Pi OS 64-bit (aarch64)." >&2
  exit 1
fi

sudo apt update
sudo apt install -y python3-venv python3-pip v4l-utils usbutils unzip libgl1 libglib2.0-0

python3 -m venv --clear .venv
.venv/bin/python -m pip install --upgrade pip

echo "[1/3] Memasang PyTorch + TorchVision CPU-only untuk Linux ARM64..."
.venv/bin/python -m pip install --no-cache-dir \
  --index-url https://download.pytorch.org/whl/cpu \
  'torch==2.11.0+cpu' 'torchvision==0.26.0+cpu'

echo "[2/3] Memasang Ultralytics dan OpenCV..."
.venv/bin/python -m pip install --no-cache-dir ultralytics pyserial

echo "[3/3] Memverifikasi dependensi..."
.venv/bin/python - <<'PY'
import cv2, torch, torchvision, ultralytics
print("OpenCV:", cv2.__version__)
print("PyTorch:", torch.__version__)
print("TorchVision:", torchvision.__version__)
print("Ultralytics:", ultralytics.__version__)
print("PyTorch CUDA build:", torch.version.cuda)
if torch.version.cuda is not None:
    raise RuntimeError("Build PyTorch memuat CUDA; instalasi CPU-only gagal.")
print("[INSTALL OK] Runtime CPU siap untuk Raspberry Pi 5.")
PY
