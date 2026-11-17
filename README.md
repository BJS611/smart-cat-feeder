# Smart Cat Feeder — Raspberry Pi 5 AI Controller

Prototipe pengujian **deteksi kucing + estimasi kelompok umur** pada **Raspberry Pi 5 4GB** memakai webcam USB **JETE W7**. Dua checkpoint YOLO ada di repository, sehingga tidak perlu mengunduh ulang dari Google Colab atau server iot-lab.

> **Status: AI smoke test, bukan dispenser otomatis.** Program ini **tidak** mengakses GPIO, Arduino, servo, atau dispenser, serta **tidak** mengeluarkan pakan. Estimasi usia visual belum cukup akurat untuk menentukan porsi makanan.

## 1. Susunan perangkat yang digunakan

| Perangkat | Fungsi saat ini |
| --- | --- |
| Raspberry Pi 5 4GB + microSD | Menjalankan kedua model di CPU |
| Webcam JETE W7 USB | Mengambil gambar/video kucing |
| Laptop (Parrot OS) | Akses SSH, inspeksi laporan |
| Arduino Uno R3 | Belum dipakai; tahap selanjutnya sebagai kontrol servo/display |
| 2x Tower Pro MG996R | Belum dipasang; memerlukan catu daya servo terpisah |
| TM1637 dan LCD 16x2 | Belum dipakai pada pengujian AI |

**Belum ada HX711/load cell pada daftar komponen.** Karena itu alat belum dapat mengukur gram pakan. Jangan mengaktifkan servo untuk feeding otomatis tanpa mekanisme keamanan dan pengukuran porsi.

## 2. Model yang digunakan

| Lokasi | Arsitektur | Fungsi |
| --- | --- | --- |
| `models/detector_coco80.pt` | YOLO11n detect, 80 kelas COCO | Deteksi `cat` (ID 15), bounding box, confidence |
| `models/cat_age_v4_hybrid_best.pt` | YOLO11s-cls, 3 kelas | Perkiraan `kitten_1_3`, `kitten_4_6`, `kitten_7_12` |

Evaluasi model usia v4 pada **415 gambar test PetFinder**: accuracy **63,86%**, balanced accuracy **55,78%**, macro-F1 **56,47%**. Hasil ini bukan akurasi detektor dan bukan pengukuran pada webcam JETE W7. Khusus kucing dewasa di atas 12 bulan, kelas model umur tidak mencakup usianya.

## 3. Persiapan Raspberry Pi OS

1. Gunakan **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Pilih **Raspberry Pi OS (64-bit)**, bukan image 32-bit; flash ke microSD.
3. Di pengaturan Imager, tentukan username/password, koneksi Wi-Fi atau Ethernet, dan **Enable SSH** jika ingin headless.
4. Boot Raspberry Pi dengan catu daya resmi/kompatibel (untuk Pi 5 direkomendasikan 5,1V 5A), pendinginan dan webcam USB yang terpasang.
5. Dari laptop, cari IP Raspberry Pi atau coba hostname `.local` bila mDNS tersedia.

Masuk lewat SSH dari laptop:

```bash
ssh <user_pi>@<ip_pi>
```

Jalankan pengecekan di Pi:

```bash
uname -m                  # seharusnya: aarch64
cat /etc/os-release       # Raspberry Pi OS / Debian 64-bit
python3 --version
free -h
df -h /
lsusb
```

## 4. Clone repository dan instal dependencies

Di Raspberry Pi:

```bash
sudo apt update
sudo apt install -y git
# Ganti URL kalau repo disimpan di owner/nama yang berbeda
git clone https://github.com/BJS611/smart-cat-feeder.git
cd smart-cat-feeder
bash install_pi.sh
```

Untuk **repository private**, gunakan GitHub CLI, SSH key, atau credential GitHub dengan izin membaca repository; jangan menaruh personal access token di skrip/README. Alternatif transfer lewat laptop memakai `scp -r` setelah repository diunduh di laptop.

Instalasi `install_pi.sh` membuat `.venv` terisolasi dan memasang `ultralytics` (beserta PyTorch/OpenCV). Dependency dan wheel ARM64 membutuhkan koneksi internet serta ruang disk beberapa GB. **Jangan** menggunakan `sudo pip` atau `--break-system-packages`. Proses instalasi pertama dapat berat pada microSD.

Verifikasi bobot model:

```bash
sha256sum -c SHA256SUMS
```

## 5. Test tanpa webcam (wajib pertama kali)

```bash
.venv/bin/python pi5_ai_test.py --selftest
```

Keberhasilan ditandai `[MODEL OK]` untuk kedua model dan `[SELFTEST OK]`. Pengujian gambar sintetis ini **hanya membuktikan model dapat memuat dan inferensi di CPU**; bukan pengujian akurasi kucing.

## 6. Test webcam JETE W7

Identifikasi kamera:

```bash
lsusb
v4l2-ctl --list-devices
ls -l /dev/video*
```

Cek pengambilan frame tanpa model:

```bash
.venv/bin/python pi5_ai_test.py --camera-only --source 0 --seconds 10
```

Jika kamera berada di `/dev/video2`, ganti `--source 0` menjadi `--source 2` (atau `--source /dev/video2`). Hindari memilih node metadata kamera yang bukan perangkat video capture.

## 7. Jalankan dua model sekaligus

Headless melalui SSH (tidak perlu desktop):

```bash
.venv/bin/python pi5_ai_test.py --source 0 --seconds 60
```

Opsional mempercepat inferensi CPU dan menyesuaikan confidence:

```bash
.venv/bin/python pi5_ai_test.py --source 0 --seconds 60 --imgsz 320 --every 4 --conf 0.40
```

Dengan desktop Raspberry Pi, tambahkan `--display`. Jangan gunakan `--display` lewat SSH tanpa X/Wayland forwarding.

Tes foto nyata tanpa webcam:

```bash
.venv/bin/python pi5_ai_test.py --image /home/<user_pi>/foto-kucing.jpg
```

Hasil tersimpan di:

- `results/summary.json`: frame, jumlah inferensi, frame dengan kucing, estimasi usia, FPS kamera, dan rata-rata waktu inferensi.
- `results/last_frame.jpg`: frame terakhir (jika webcam digunakan).
- `results/hasil_foto.jpg`: foto hasil `--image`.

Cek laporan:

```bash
cat results/summary.json
```

**Kriteria lulus:** kedua model dapat dimuat, kamera dapat menangkap frame, hasil inferensi tercatat, dan saat ada kucing nyata akan muncul `[CAT]`. Nilai FPS diambil dari Raspberry Pi yang sebenarnya; jangan berasumsi memiliki FPS tertentu sebelum diukur.

## 8. Troubleshooting cepat

| Gejala | Tindakan |
| --- | --- |
| `python3 -m venv` gagal | `sudo apt install python3-venv` lalu ulangi `bash install_pi.sh` |
| `torch`/`ultralytics` gagal diinstal | Pastikan `uname -m` = `aarch64`, OS 64-bit, cukup ruang; simpan log lengkap `pip` |
| Kamera gagal dibuka | `lsusb`, `v4l2-ctl --list-devices`; ganti `--source`; pastikan tidak digunakan aplikasi lain |
| Izin `/dev/video*` ditolak | `groups`, `ls -l /dev/video0`; pertimbangkan menambahkan akun ke grup `video` lalu login ulang |
| Raspberry Pi lambat | Kurangi `--imgsz` ke 320, naikkan `--every`, sediakan pendinginan; evaluasi export NCNN nantinya |
| Detektor tidak menemukan kucing | Uji foto kucing nyata dengan `--image`, periksa cahaya, posisi, dan nilai `--conf` |
| Age classifier salah menebak | Normal mengingat balanced accuracy 55,78%; jangan pakai untuk menentukan porsi |
| `-bash: .venv/bin/...` tidak ada | Jalankan `bash install_pi.sh` dari root repository, lalu cek `ls -la .venv/bin/` |

Log instalasi apabila terjadi error:

```bash
bash install_pi.sh 2>&1 | tee install.log
```

## 9. Arsitektur tahap selanjutnya

```text
Webcam JETE W7 --USB--> Raspberry Pi 5 (YOLO11n + YOLO11s-cls)
                                |
                   USB serial ke Arduino Uno (belum dibuat)
                                |
                    +-----------+----------+
                    |           |          |
                MG996R x2    TM1637    LCD 16x2
```

Servo MG996R **wajib** memakai catu daya terpisah 5–6V dengan arus cukup dan **common ground** dengan kontroler. Jangan mengambil arus servo dari GPIO Raspberry Pi, pin 5V Raspberry Pi, atau USB Arduino. Tambahkan HX711/load cell untuk gram pakan, limit porsi, timeout, cooldown, dan mode fail-safe sebelum feeding otomatis.

## 10. Status dan lisensi model

- Proyek ini adalah prototipe penelitian/pembelajaran, **bukan alat pemberi makan otomatis yang tervalidasi**.
- Checkpoint berasal dari model Ultralytics; sebelum distribusi atau penggunaan komersial, periksa persyaratan lisensi Ultralytics (AGPL-3.0 atau Enterprise sesuai kasus) di https://www.ultralytics.com/license.
- Foto/dataset PetFinder/Wikimedia tidak disertakan. Periksa lisensi sumber jika kelak membagikan dataset.
- Untuk menjaga histori model, checkpoint v2/v3/v5 tetap tersimpan di backup terpisah; repository ini hanya memuat dua model terpilih untuk runtime.
