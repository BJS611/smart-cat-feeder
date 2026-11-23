# Cat-activated YOLO with Logitech C270

Mode opt-in, tanpa sensor PIR tambahan.

1. Webcam tetap hidup dan pendeteksi gerakan ringan tetap aktif.
2. Saat tidak ada gerakan dan belum ada kucing baru-baru ini, inferensi YOLO dilewati.
3. Saat ada gerakan, YOLO mengecek gambar tiap 2 detik (`cat_probe`).
4. Begitu YOLO menemukan kelas COCO `cat` (15), model memproses lebih sering (interval 0,4 detik) agar CatGate bisa mengumpulkan 3 deteksi berturut-turut.
5. Setelah sekitar 10 detik tidak ada deteksi kucing, frekuensi inferensi turun lagi. Jika gerakan juga telah berhenti, status beralih ke `standby`.
6. Servo, HC-SR04, IR, LCD, cooldown, dan protokol serial tetap mengikuti firmware Arduino sebelumnya.

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
  --cat-activated-yolo \
  --cat-probe-seconds 2 \
  --cat-active-hold 10 \
  --motion-sample 0.5 \
  --motion-threshold 20 \
  --motion-fraction 0.025 \
  --motion-hold 15 \
  --arduino-port /dev/ttyUSB0 \
  --stable-hits 3 \
  --cooldown-seconds 60 \
  --rearm-seconds 5
```

Hapus `--arduino-port` untuk pengujian tanpa servo. Data status tersedia melalui `/status` bagian `cat_activity` (`standby`, `cat_probe`, `cat_active`). Perlu diperhatikan bahwa sistem tidak dapat mengetahui ada kucing tanpa menguji frame setidaknya sekali; mode ini menggunakan pemeriksaan berkala setelah gerakan, bukan detektor kucing pasif. Webcam dan Raspberry Pi tetap menyala. Kucing yang masuk sangat perlahan atau diam tanpa menyebabkan perubahan gambar mungkin tidak memicu pemeriksaan. Verifikasi pada hardware sebelum dipakai sebagai feeder tanpa pengawasan.
