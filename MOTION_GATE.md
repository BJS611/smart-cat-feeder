# Camera Motion Gate — Smart Cat Feeder

Mode ini memakai webcam Logitech C270 sebagai pendeteksi gerakan ringan. YOLO11 hanya menerima frame untuk inferensi ketika gerakan terdeteksi. Kamera USB dan Raspberry Pi tetap menyala; ini bukan suspend/shutdown atau pengurangan konsumsi daya total yang sudah terukur.

## Jalankan

```bash
cd ~/smart-cat-feeder
.venv/bin/python -m unittest discover -s tests -v

.venv/bin/python live_cam.py \
  --source 0 \
  --port 8767 \
  --imgsz 320 \
  --conf 0.40 \
  --camera-fourcc MJPG \
  --camera-fps 10 \
  --stream-fps 8 \
  --idle-stream-fps 1 \
  --jpeg-quality 55 \
  --interval 0.4 \
  --cat-only \
  --motion-gate \
  --motion-sample 0.5 \
  --motion-threshold 20 \
  --motion-fraction 0.025 \
  --motion-hold 15 \
  --motion-warmup 3 \
  --arduino-port /dev/ttyUSB0 \
  --stable-hits 3 \
  --cooldown-seconds 60 \
  --rearm-seconds 5
```

Hilangkan `--arduino-port /dev/ttyUSB0` untuk pengujian deteksi tanpa pengeluaran pakan. Jangan jalankan dua program yang membuka port serial Arduino yang sama secara bersamaan.

## Mekanisme

- Kamera tetap terbuka, menangkap frame pada 10 FPS yang diminta.
- Motion gate memeriksa gambar 160×120 abu-abu pada interval 0,5 detik.
- Perubahan kecerahan rata-rata dikompensasi sebelum menghitung proporsi piksel yang berubah.
- Ketika proporsi piksel berubah melebihi ambang 2,5%, YOLO diaktifkan.
- Setelah 15 detik tanpa perubahan baru, inferensi YOLO dihentikan sampai ada gerakan lagi.
- Stream JPEG turun ke 1 FPS ketika standby. Model tetap dimuat di RAM.
- Mekanisme CatGate, FEED, cooldown, LCD, HC-SR04, IR mangkuk dan servo 360° tidak diganti.

Status dapat dilihat pada `http://127.0.0.1:8767/status` melalui properti `motion_gate`, `motion_samples`, dan `performance.yolo_fps`.

## Penyesuaian

- Kamera terlalu sering terpicu: naikkan `--motion-fraction` ke `0.04` atau `--motion-threshold` ke `30`.
- Gerakan kucing terlalu kecil: turunkan `--motion-fraction` ke `0.01`.
- Kucing berhenti bergerak lalu YOLO terlalu cepat standby: naikkan `--motion-hold` ke `25`.
- Jangan letakkan webcam menghadap objek yang selalu bergerak (kipas, tirai, refleksi), karena akan membuat YOLO aktif terus.

## Verifikasi

Amati `vcgencmd measure_temp`, `vcgencmd get_throttled`, penggunaan CPU dan FPS inferensi ketika idle serta saat kucing bergerak. Temperatur dan konsumsi listrik harus diukur di hardware asli; penurunan tidak dijamin oleh kode saja.
