# Smart Cat Feeder — YOLO11 Single Model

Saat ini proyek hanya memakai **satu model YOLO11n Object Detection** pada Raspberry Pi 5 4GB dengan webcam JETE W7. Tidak ada klasifikasi umur, pengukuran berat, maupun kontrol servo pada pengujian ini.

## Model aktif

Seluruh kode runtime baru hanya membaca **`models/yolo11.pt`**.

Nama resmi checkpoint YOLO11n dari Ultralytics adalah **`yolo11n.pt`**, bukan `yolo11.pt`. Jika `models/yolo11.pt` belum ada, script otomatis mengunduh `yolo11n.pt` resmi dan menyimpan salinannya dengan nama `models/yolo11.pt`. Bila kamu sudah punya checkpoint YOLO11 detect sendiri, simpan sebagai `models/yolo11.pt` sebelum menjalankan program. Unduhan ini hanya terjadi ketika file belum ada.

Checkpoint lama `models/detector_coco80.pt` dan `models/cat_age_v4_hybrid_best.pt` tidak dipakai oleh `live_cam.py` maupun `pi5_ai_test.py`. File lama mungkin masih ada sebagai arsip di GitHub, tetapi tidak pernah dimuat.

Default: deteksi semua kelas COCO. Tambahkan `--cat-only` untuk hanya mendeteksi kucing.

## Instalasi Raspberry Pi OS 64-bit

Persiapkan Raspberry Pi 5, SD card 32GB, webcam USB dan SSH. Gunakan catu daya stabil dan pendinginan. Di Raspberry Pi:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/BJS611/smart-cat-feeder.git
cd smart-cat-feeder
bash install_pi.sh
```

Jika repo sudah ada dan instalasi dependency telah berhasil:

```bash
cd ~/smart-cat-feeder
git pull --ff-only
```

Installer memasang PyTorch **CPU-only untuk ARM64**. Jangan menggunakan kembali installer lama yang mengunduh paket CUDA NVIDIA seperti `nvidia_cublas`. Jika microSD penuh akibat cache instalasi lama:

```bash
rm -rf ~/.cache/pip
sudo apt clean
df -h /
git pull --ff-only
bash install_pi.sh
```

Menjalankan ulang installer akan membuat ulang `.venv`; model di folder `models/` tidak dihapus.

## Pengujian satu model

Untuk memastikan model dapat dijalankan:

```bash
cd ~/smart-cat-feeder
.venv/bin/python pi5_ai_test.py --selftest
```

Output sukses memuat `models/yolo11.pt` dengan task `detect` dan `[SELFTEST OK]`. Gambar sintetis tidak menguji akurasi.

Periksa webcam:

```bash
v4l2-ctl --list-devices
ls -l /dev/video*
.venv/bin/python pi5_ai_test.py --camera-only --source 0 --seconds 10
```

Tes deteksi lewat webcam:

```bash
.venv/bin/python pi5_ai_test.py --source 0 --seconds 60 --imgsz 320
```

Hanya kucing:

```bash
.venv/bin/python pi5_ai_test.py --source 0 --seconds 60 --cat-only
```

Laporan tersedia di `results/summary.json` dan `results/last_frame.jpg`. Pada desktop Raspberry Pi, gunakan `--display` untuk jendela OpenCV.

## Live video di browser Parrot OS

Di terminal SSH **Raspberry Pi**:

```bash
cd ~/smart-cat-feeder
git pull --ff-only
.venv/bin/python live_cam.py --source 0 --port 8767 --imgsz 320
```

Mode ini menampilkan **semua kelas** yang terdeteksi YOLO11. Jika ingin khusus kucing, ganti menjadi:

```bash
.venv/bin/python live_cam.py --source 0 --port 8767 --imgsz 320 --cat-only
```

Jalankan perintah di terminal **kedua pada laptop Parrot OS**:

```bash
ssh -N -L 8767:127.0.0.1:8767 yolo@yolo11.local
```

Buka browser laptop ke **http://127.0.0.1:8767/**.

Jika `yolo11.local` gagal terdeteksi, ganti dengan IP Raspberry Pi. Jangan buka `http://IP_PI:8767`; server secara sengaja hanya mendengarkan localhost agar tidak terekspos ke jaringan. Hentikan streaming dengan Ctrl+C.

## Troubleshooting

| Gejala | Penyelesaian |
| --- | --- |
| Video tidak tampil / connection refused | Periksa proses `live_cam.py` serta SSH tunnel masih aktif dan browser membuka `127.0.0.1:8767`. |
| Kamera gagal dibaca | Jalankan `v4l2-ctl --list-devices`, sesuaikan `--source 0` ke nomor kamera yang sebenarnya, contohnya `--source 2`. |
| Performa CPU lambat | Gunakan `--imgsz 320`, kurangi beban proses lain, periksa pendinginan Pi 5. |
| Download model gagal | Periksa internet Pi atau salin checkpoint YOLO11 detection yang ada ke `models/yolo11.pt`. |
| File lama masih ada | Tidak masalah: runtime tidak menggunakan `detector_coco80.pt` maupun `cat_age_v4_hybrid_best.pt`. |
| Nama/usia tidak muncul | Ini disengaja: hanya deteksi objek, tidak menjalankan klasifikasi umur. |

## Catatan proyek

- Program **tidak** mengontrol Arduino/GPIO/servo dan **tidak** memberi makan kucing.
- YOLO COCO mendeteksi objek, tetapi tidak memastikan kucing lapar atau menentukan porsi makan.
- Sebelum membuat dispenser otomatis, tambahkan kalibrasi timbangan pakan, batas porsi, jadwal, cooldown, dan keamanan aktuator.
- Perhatikan persyaratan lisensi Ultralytics untuk distribusi dan penggunaan komersial: https://www.ultralytics.com/license.

Revisi single-model sudah diunggah, namun uji live camera pada perangkat nyata tetap perlu dilakukan.
