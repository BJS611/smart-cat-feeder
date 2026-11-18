# Smart Cat Feeder — YOLO11 Single Model

Saat ini proyek memakai **satu model YOLO11n Object Detection** pada Raspberry Pi 5 4GB dengan webcam JETE W7. Klasifikasi umur tetap dinonaktifkan. Kontrol servo Arduino Uno **opsional** melalui USB serial untuk **bench test tanpa pakan**; saat port Arduino tidak diberikan, program hanya menampilkan live video.

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

## Arduino Uno + MG996R lewat USB serial (prototype / uji tanpa pakan)

### Skema koneksi

- **Raspberry Pi 5 USB** → **Arduino Uno USB Type-B** (kabel data).
- **Arduino D9** → **MG996R signal** (oranye/kuning).
- **Supply servo eksternal 5–6V (+)** → **MG996R merah**.
- **Supply servo eksternal GND (−)** → **MG996R cokelat/hitam**.
- **Arduino GND** → **GND supply servo** (*common ground*, wajib).
- **Jangan memberi daya servo dari pin 5V/3.3V Raspberry Pi atau 5V Arduino.** Gunakan catu daya 5–6V berarus cukup, misalnya 3A untuk **satu** MG996R, serta periksa spesifikasi unit.

**Uji pertama tanpa memasang lengan servo ke mekanisme dispenser, dan tanpa makanan.** Program ini belum memakai HX711/load cell; gerakan servo tidak menjamin gram pakan tertentu. Jangan gunakan sebagai feeder otomatis tanpa batasan mekanis, porsi dan pengujian keselamatan.

### 1) Upload sketch Arduino (C++)

Pada Arduino IDE, pilih **Arduino Uno** dan port USB Arduino. Buka file:

`arduino/smart_cat_feeder_servo/smart_cat_feeder_servo.ino`

Klik **Upload**. Sketch memakai pustaka `Servo.h` bawaan Arduino IDE. Tutup Serial Monitor setelah upload (port tidak boleh dipakai dua proses).

Konfigurasi penting di atas sketch:

- Pin servo `SERVO_PIN = 9`.
- Sudut `CLOSED_ANGLE = 20` dan `OPEN_ANGLE = 80` adalah nilai **contoh untuk uji tanpa beban**. Sesuaikan agar mekanisme tidak mentok.
- Gerakan buka `OPEN_MS = 650` milidetik, lalu kembali tutup.
- **Arduino menolak FEED kedua selama 60 detik**.
- Pesan serial: `PING` → `PONG`; `FEED` → `ACK FEED` lalu `DONE`; `STATUS` → status. Port `115200 baud`, satu perintah per baris.

#### Alternatif: upload Arduino langsung dari SSH Raspberry Pi

Jika tidak memakai Arduino IDE di laptop, instal **Arduino CLI ARM64 resmi** dan lakukan compile/upload melalui USB langsung pada Raspberry Pi:

```bash
sudo apt install -y curl
mkdir -p ~/.local/bin
curl -fL https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Linux_ARM64.tar.gz \
  -o /tmp/arduino-cli-arm64.tar.gz
tar -xzf /tmp/arduino-cli-arm64.tar.gz -C ~/.local/bin arduino-cli

~/.local/bin/arduino-cli version
~/.local/bin/arduino-cli core update-index
~/.local/bin/arduino-cli core install arduino:avr
~/.local/bin/arduino-cli lib install Servo

cd ~/smart-cat-feeder
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo
~/.local/bin/arduino-cli board list
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  -p /dev/ttyACM0 arduino/smart_cat_feeder_servo
```

Ubah `/dev/ttyACM0` jika board terdeteksi di port lain. Untuk port permission denied, tambahkan akun ke `dialout` dan login ulang sebelum upload. **Hentikan `live_cam.py` dan tutup Serial Monitor sebelum upload Arduino.**

### 2) Periksa port USB di Raspberry Pi

```bash
cd ~/smart-cat-feeder
git pull --ff-only
.venv/bin/python -m pip install pyserial
ls -l /dev/serial/by-id/ /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
.venv/bin/python -m serial.tools.list_ports
```

Arduino Uno asli biasanya `/dev/ttyACM0`; clone dengan chip USB-serial lain mungkin memakai `/dev/ttyUSB0`. Jika `Permission denied`:

```bash
sudo usermod -aG dialout yolo
```

Lalu **logout dari SSH dan login ulang** agar grup `dialout` aktif.

### 3) Tes komunikasi sebelum menggerakkan servo

```bash
.venv/bin/python serial_servo_test.py --port /dev/ttyACM0
```

Tes di atas hanya `PING` dan `STATUS` (tidak menggerakkan servo). Jika sudah ada catu daya eksternal dan servo berada di meja tanpa beban, tes gerakan **satu kali**:

```bash
.venv/bin/python serial_servo_test.py --port /dev/ttyACM0 --feed
```

Output yang diharapkan: `PONG`, `STATUS IDLE`, `ACK FEED`. Jika mengulang sebelum 60 detik, Arduino membalas `ERR COOLDOWN`.

### 4) Jalankan deteksi kucing → servo otomatis (uji tanpa pakan)

Hentikan `pi5_ai_test.py` dan pastikan **tidak ada Serial Monitor atau program lain yang membuka port Arduino**. Di Raspberry Pi:

```bash
cd ~/smart-cat-feeder
.venv/bin/python live_cam.py \
  --source 0 \
  --imgsz 320 \
  --cat-only \
  --arduino-port /dev/ttyACM0 \
  --stable-hits 3 \
  --cooldown-seconds 60 \
  --rearm-seconds 5
```

Logika pengaman:

1. Detektor YOLO11 melihat `cat` pada **3 hasil inferensi berturut-turut**, bukan hanya satu frame.
2. Raspberry Pi mengirim `FEED\n` satu kali lewat USB serial.
3. Arduino menerima `FEED`, memutar MG996R dari sudut tutup ke buka, lalu kembali menutup.
4. Arduino dan Raspberry Pi menerapkan cooldown masing-masing; Pi juga menunggu kucing **menghilang minimal 5 detik** sebelum bisa terpicu lagi.
5. **Membuka Serial Uno dapat me-reset Arduino**. Cooldown di memori Uno hilang jika Uno reset. Ini hanya aman untuk bench test tanpa makanan, bukan proteksi porsi permanen.

Tanpa `--arduino-port`, `live_cam.py` **tidak mengirim perintah servo**.

Di terminal **kedua pada laptop Parrot OS**:

```bash
ssh -N -L 8767:127.0.0.1:8767 yolo@yolo11.local
```

Buka **http://127.0.0.1:8767/** untuk melihat video dengan bounding box kucing dan status pengiriman perintah Arduino (balasan `ACK FEED` bukan bukti fisik bahwa servo benar-benar bergerak). Gunakan `Ctrl+C` pada terminal Pi untuk berhenti.

### Jika terjadi masalah

| Masalah | Pemeriksaan |
| --- | --- |
| `[ARDUINO OK]` tidak muncul | Sketch sudah di-upload? Port benar? Coba `serial_servo_test.py` dan `ls /dev/ttyACM* /dev/ttyUSB*`. |
| `Permission denied` | Tambah `yolo` ke grup `dialout` kemudian login ulang. |
| Port `busy` | Tutup Arduino IDE Serial Monitor dan hentikan program serial lain. |
| `PONG` ada tetapi servo tidak bergerak | Cek **power eksternal 5–6V, common ground, pin D9, dan kabel signal**. |
| Arduino restart saat servo bergerak | Biasanya catu daya servo tidak cukup atau wiring ground salah; jangan mengambil daya servo dari USB Uno/Pi. |
| Kucing terdeteksi tetapi servo tidak bergerak | Periksa `cat_detection_streak` dan `last_serial_response` di `/status`, serta cooldown Arduino. |

---

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

- Program live camera **hanya mengirim perintah servo** jika opsi `--arduino-port` diaktifkan secara eksplisit. Mode standar tidak menggerakkan servo. Tidak ada pengukuran pakan atau kontrol porsi, jadi hanya untuk bench test tanpa makanan.
- YOLO COCO mendeteksi objek, tetapi tidak memastikan kucing lapar atau menentukan porsi makan.
- Sebelum membuat dispenser otomatis, tambahkan kalibrasi timbangan pakan, batas porsi, jadwal, cooldown, dan keamanan aktuator.
- Perhatikan persyaratan lisensi Ultralytics untuk distribusi dan penggunaan komersial: https://www.ultralytics.com/license.

Revisi single-model sudah diunggah, namun uji live camera pada perangkat nyata tetap perlu dilakukan.
