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

### Sensor infrared digital (D6) dan LED merah peringatan pakan habis (D7)

**Asumsi modul:** sensor IR proximity/obstacle detection 3-pin atau 4-pin (seperti FC-51/LM393) dengan keluaran **digital OUT/DO**. Jenis IR break-beam atau modul analog murni memerlukan penyesuaian; jangan menebak pin. Modul reflektif mendeteksi objek pada satu titik, **tidak mengukur berat, volume, atau total pakan**. Sensor harus diuji terhadap warna, tekstur, jarak, sudut, cahaya, dan material dinding hopper sebelum digunakan.

**Koneksi (matikan daya sebelum memindahkan kabel):**

| Perangkat | Pin Arduino Uno |
| --- | --- |
| Sensor IR VCC | 5V |
| Sensor IR GND | GND |
| Sensor IR DO / OUT (digital) | D6 |
| LED merah anoda (+) | D7 **lewat resistor seri 220–330 Ω** |
| LED merah katoda (-) | GND |

Pin lainnya tetap: tombol manual D2-GND, LED hijau D4, LED kuning D5, sinyal servo D9, LCD I2C SDA=A4 SCL=A5. Daya MG996R **eksternal 5–6V**, ground disatukan dengan Arduino. Jika menggunakan lampu indikator bertegangan 12/24V atau LED berarus tinggi, wajib driver yang sesuai; jangan langsung ke pin digital Arduino.

**Logika indikator baru:**

| Kondisi | Hijau D4 | Kuning D5 | Merah D7 |
| --- | --- | --- | --- |
| Pakan terdeteksi dan servo Idle | ON | OFF | OFF |
| Servo bergerak lewat YOLO11 / tombol manual; pakan tersedia | OFF | ON | OFF |
| Objek/pakan tidak terdeteksi stabil selama 3 detik | OFF saat Idle | Sesuai servo/emergency | ON |
| Status sensor belum terverifikasi sesaat setelah boot | OFF | Sesuai servo/emergency | ON (peringatan) |
| Pakan kembali terdeteksi stabil 0,8 detik | ON jika Idle | Sesuai servo/emergency | OFF |

Peringatan merah **tidak memblokir** FEED otomatis atau tombol manual saat ini; sensor hanya monitoring/indikator agar perilaku servo existing tidak diam-diam berubah. Untuk feeding nyata, pertimbangkan safety interlock berbasis sensor level yang tervalidasi serta timbangan/pembatas porsi.

Pada kebanyakan sensor reflektif digital **LOW = objek terdeteksi** dan **HIGH = tak ada objek**. Jika modul kamu terbalik, ubah `IR_FOOD_PRESENT_LEVEL` dari `LOW` menjadi `HIGH` di sketch sebelum compile. Sensor dipasang pada titik **minimum level pakan**, dengan pemancar/penerima IR menghadap langsung ke permukaan pellet, bukan dinding kosong atau cahaya kuat. Kalibrasikan potensiometer di modul sambil mengamati hasil serial.

**Meng-upload firmware bench terbaru:**

```bash
cd ~/smart-cat-feeder
git pull --ff-only

# Hentikan live_cam.py dan serial monitor lain sebelum meng-upload.
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo_bench_5s
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  --port /dev/ttyUSB0 arduino/smart_cat_feeder_servo_bench_5s
```

**Uji sensor tanpa menggerakkan servo** (membuka satu sesi serial dan memantau terus-menerus):

```bash
.venv/bin/python serial_servo_test.py --port /dev/ttyUSB0 --food-monitor
```

Contoh hasil:

```text
[IR] FOOD_STATUS RAW=LOW STATE=PRESENT
[IR] FOOD_STATUS RAW=HIGH STATE=CHECKING
[IR] FOOD_STATUS RAW=HIGH STATE=EMPTY
```

Saat startup, `STATE=CHECKING` selama proses validasi pembacaan. Setelah 3 detik tanpa objek, `STATE=EMPTY` dan LED merah ON. Setelah pakan berada di depan sensor stabil 0,8 detik, `STATE=PRESENT` dan LED merah OFF (LED hijau kembali menyala jika tidak sedang Feeding).

**Catatan:** pada modul tanpa sensor tersambung, input D6 memakai `INPUT_PULLUP` dan cenderung terbaca HIGH, sehingga LED merah juga akan menyala setelah start. Kondisi ini **tidak** membedakan hopper kosong dengan sensor yang hilang atau kabel putus. Periksa kabel dan sensor secara terpisah; jangan mengandalkan satu sensor reflektif sebagai proteksi keselamatan atau pengukuran porsi yang presisi.

### Dua LED indikator Arduino Uno (hijau / kuning)

Firmware terbaru pada **kedua** sketch (normal 60 s dan bench 5 s) menyediakan LED indikator:

| Keadaan | Hijau (D4) | Kuning (D5) |
| --- | --- | --- |
| Arduino siap / Idle | ON | OFF |
| YOLO11 mendeteksi kucing dan Arduino sedang menjalankan FEED | OFF | ON |
| Pushbutton manual D2 men-trigger servo ("Emergency feed") | OFF | ON |
| Perintah serial `EMERGENCY` (software lock, tidak menggerakkan servo) | OFF | ON hingga `RESET` |
| Servo selesai dan status kembali Idle | ON | OFF |

**Sambungan LED standar 3–5 mm** (masing-masing wajib resistor seri 220–330 Ω):

- `Arduino D4 -> resistor 220–330 Ω -> anoda (+, kaki panjang) LED hijau; katoda (-, kaki pendek) -> GND Arduino`.
- `Arduino D5 -> resistor 220–330 Ω -> anoda (+, kaki panjang) LED kuning; katoda (-, kaki pendek) -> GND Arduino`.

Gunakan dua resistor terpisah, satu untuk setiap LED. LED ini dikontrol langsung oleh Arduino, jadi tetap merespons tombol D2 tanpa Raspberry Pi terhubung. **Jika indikator yang digunakan adalah lampu industri 12/24V atau modul LED berarus tinggi, jangan hubungkan langsung ke pin Arduino**: gunakan driver transistor/MOSFET/relay yang sesuai tegangan dan arus.

LCD I2C tetap opsional dan tidak menghalangi LED ketika dilepas. LED kuning merepresentasikan status *Feeding* / *Emergency* yang berbagi satu indikator, bukan bukti servo benar-benar bergerak.

Setelah `git pull --ff-only`, **compile dan upload firmware Arduino lagi sekali** agar dua pin LED aktif:

```bash
cd ~/smart-cat-feeder
git pull --ff-only

# Untuk uji bench tanpa makanan, sesuai firmware 5 detik:
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo_bench_5s
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  --port /dev/ttyUSB0 arduino/smart_cat_feeder_servo_bench_5s
```

Setelah upload, **hijau harus menyala**. Menekan tombol D2 atau memicu FEED lewat YOLO11 menyalakan **kuning hanya selama servo bekerja**; setelah siklus selesai, hijau menyala lagi. Mode software lock `EMERGENCY` menahan kuning sampai `RESET`.

### Tombol pemberian pakan manual darurat (Arduino D2)

**Istilah penting:** tombol ini adalah **MANUAL FEED OVERRIDE**, yang menggerakkan servo saat ditekan. **Bukan emergency stop**, bukan pemutus daya, dan bukan mekanisme pengaman keselamatan mesin.

**Koneksi pushbutton momentary NO** (normally open):
- Salah satu kontak → **D2 Arduino Uno**.
- Kontak lainnya → **GND Arduino Uno**.
- Firmware memakai `pinMode(2, INPUT_PULLUP)`; tidak perlu resistor tambahan.
- Jika tombol empat kaki, gunakan dua pin yang akan **tersambung hanya ketika tombol ditekan** (periksa dengan multimeter).
- MG996R: sinyal D9, **daya servo eksternal 5–6V**, GND servo disambungkan dengan GND Arduino. **Jangan** ambil daya motor servo dari pin 5V Arduino/Pi.

**Perilaku:**
1. Tombol tertekan stabil selama 35 ms → satu siklus servo buka lalu tutup, dengan log serial `EVENT MANUAL_FEED`.
2. Menahan tombol tidak memicu siklus berikutnya; harus lepas dan tekan ulang.
3. Tombol manual **tidak memerlukan YOLO11, koneksi serial Pi, atau cooldown otomatis**. Ada jarak minimum anti-repeat tombol 2 detik, dan tidak dapat memulai siklus baru saat servo sedang bekerja.
4. Siklus tombol manual juga memulai cooldown perintah FEED otomatis (5 detik pada sketch bench atau 60 detik pada sketch normal).
5. Perintah serial `EMERGENCY` yang sudah ada adalah **software lock/stop**: bila aktif, baik FEED otomatis maupun tombol manual akan diblokir sampai perintah `RESET`. Ini berbeda dari tombol fisik manual.
6. Saat LCD nanti tersedia, tombol manual menunjukkan status `Emergency` selama gerakan; status otomatis menunjukkan `Feeding`. Keduanya kembali ke `Idle` setelah servo selesai.

**LCD tetap disimpan di firmware, tetapi sekarang opsional.** Pada boot, Arduino memeriksa alamat I2C `0x27` dan `0x3F`. Jika LCD tidak terpasang, board mencetak `LCD NOT CONNECTED - continue without LCD` dan fungsi servo/button tetap jalan. LCD rusak harus **dilepas secara fisik** dari kabel. Ketika LCD baru datang, sambungkan LCD (VCC=5V, GND=GND, SDA=A4, SCL=A5) **saat daya mati**, kemudian hidupkan ulang Arduino. Jika alamatnya 0x27 atau 0x3F, firmware akan menggunakannya secara otomatis, **tanpa flash ulang**.

**Update dan upload** (gunakan sketch bench 5 detik yang terakhir digunakan):

```bash
cd ~/smart-cat-feeder
git pull --ff-only

# Tutup live_cam.py dan serial monitor sebelum upload
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo_bench_5s
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  --port /dev/ttyUSB0 arduino/smart_cat_feeder_servo_bench_5s
```

**Tes tombol langsung dari Arduino:** biarkan Arduino mendapat daya melalui USB (Pi bisa menjalankan atau tidak menjalankan YOLO) dan servo mendapat daya eksternal. Tekan tombol D2 sekali untuk satu siklus. **Jangan hubungkan hopper atau pakan saat tes.**

**Opsional: pantau log tombol dari Pi** tanpa mengirim perintah gerakan:

```bash
.venv/bin/python serial_servo_test.py --port /dev/ttyUSB0 --button-monitor
```

Saat ditekan, output normal berisi `EVENT MANUAL_FEED`, `STATE CLOSING` dan `DONE`. Hentikan dengan Ctrl+C. Program Python monitor membuka port Uno sendiri; jangan jalankan bersama `live_cam.py` atau Serial Monitor lain.

**Mode YOLO11 otomatis masih berfungsi** dengan skrip dan parameter sebelumnya. Sketsa regular `arduino/smart_cat_feeder_servo` tetap memiliki cooldown otomatis 60 detik; keduanya memiliki tombol D2 yang sama. Kode LCD tetap dipertahankan pada kedua sketch.

**Keamanan:** Ini **bench test tanpa pakan**. Tombol manual dapat mengabaikan jadwal dan pembatasan otomatis; jangan menggunakannya untuk memberi makan nyata tanpa mekanisme penakar, pembatasan porsi, dan uji fail-safe.

---

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

### Uji cooldown 5 detik (khusus servo tanpa hopper/makanan)

**Perbedaan istilah:** `--rearm-seconds 5` berarti kucing harus **tidak terlihat selama 5 detik** sebelum sistem siap kembali. Itu bukan cooldown. Cooldown default sebelumnya `60 detik` diberlakukan di **Raspberry Pi dan Arduino**, sehingga hanya mengubah argumen Python menjadi `5` tidak akan bekerja dengan sketch normal.

Untuk **menguji gerakan mekanik tanpa pakan** dengan cooldown 5 detik, gunakan sketch terpisah `arduino/smart_cat_feeder_servo_bench_5s/smart_cat_feeder_servo_bench_5s.ino`. **Jangan gunakan sketch ini saat hopper berisi pakan.** Sudut servo, durasi buka, dan protokol serial tetap sama; cooldown Arduino berubah menjadi 5000ms.

**Upload ke Arduino dari Raspberry Pi** (pastikan mode live dan Serial Monitor sudah ditutup):

```bash
cd ~/smart-cat-feeder
git pull --ff-only
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo_bench_5s
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  --port /dev/ttyUSB0 arduino/smart_cat_feeder_servo_bench_5s
```

Jalankan YOLO11 + USB serial dengan mode uji 5 detik:

```bash
.venv/bin/python live_cam.py \
  --source 0 --port 8767 --imgsz 320 --conf 0.40 \
  --cat-only --arduino-port /dev/ttyUSB0 \
  --stable-hits 3 --rearm-seconds 5 \
  --cooldown-seconds 5 --bench-test
```

Prosesnya adalah **3 hasil inferensi kucing berturut-turut** → satu gerakan servo → tidak ada deteksi kucing selama **5 detik** agar sistem siap lagi → minimal **5 detik** sejak trigger sebelumnya. Jika kucing tetap di depan kamera, servo tidak bergerak lagi meskipun 5 detik sudah lewat.

Untuk kembali ke default yang lebih aman, upload ulang sketch normal dari folder `arduino/smart_cat_feeder_servo` dan **hilangkan** `--bench-test`, gunakan `--cooldown-seconds 60`. Tanpa HX711, kontrol porsi, dan mekanisme pengunci, jangan gunakan deteksi otomatis sebagai pengumpan makanan tanpa pengawasan.

### LCD 16x2 I2C pada Arduino Uno: Idle, Feeding, Emergency

**Perangkat:** LCD 1602 harus memakai I2C backpack dengan pin `GND VCC SDA SCL`. Jika modul LCD hanya mempunyai 16 pin paralel dan tidak ada backpack, rangkaian berikut belum dapat dipakai.

**Wiring (Arduino Uno R3):**

| LCD I2C | Arduino Uno |
| --- | --- |
| GND | GND |
| VCC | 5V |
| SDA | A4 (SDA) |
| SCL | A5 (SCL) |

Servo tetap di D9 dengan **power eksternal** 5–6V dan common ground, sedangkan Arduino tetap menggunakan USB serial `/dev/ttyUSB0` ke Raspberry Pi.

**Tampilan LCD dua baris (16 kolom):**

- Baris 1 selalu `SMART CAT FEEDER` (16 karakter).
- Baris 2 adalah `Idle` saat board siap, `Feeding` selama servo menjalankan siklus buka-tutup (perintah serial `FEED`), atau `Emergency` bila perintah serial `EMERGENCY` diterima.
- `EMERGENCY` saat ini **simulasi status lewat serial**, bukan tombol fisik atau sistem emergency-stop bersertifikasi. Perintah itu langsung meminta servo kembali ke posisi tutup dan menolak `FEED` berikutnya sampai `RESET`. Tombol manual untuk mode emergency akan ditambahkan pada tahap berikutnya.
- LCD hanya di-refresh **ketika status berganti**, supaya tidak berkedip.

**Alamat I2C awal** diset ke `0x27`. Jika backlight menyala tetapi tulisan tidak muncul, periksa potensiometer kontras pada backpack, SDA/SCL, alamat alternatif `0x3F`, dan library LCD yang terpasang. Ganti `0x27` pada sketch bila alamat modul berbeda.

**Wajib upload firmware Arduino yang mendukung I2C sekali.** Script Python sendiri tidak dapat mengendalikan LCD yang terhubung ke pin Arduino bila firmware Arduino sebelumnya belum mempunyai kode LCD. Setelah upload sekali, penggantian status `Idle` ↔ `Feeding` berlangsung otomatis dari serial Python sebelumnya tanpa flash ulang.

Di **SSH Raspberry Pi**, hentikan `live_cam.py` dan tutup Serial Monitor, kemudian:

```bash
cd ~/smart-cat-feeder
git pull --ff-only
~/.local/bin/arduino-cli lib install "LiquidCrystal I2C"

# Untuk firmware bench test cooldown 5 detik yang sedang digunakan:
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo_bench_5s
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  --port /dev/ttyUSB0 arduino/smart_cat_feeder_servo_bench_5s
```

Jika kamu tidak memakai firmware bench 5 detik, compile/upload folder `arduino/smart_cat_feeder_servo` (cooldown 60 detik) sebagai gantinya.

**Jika koneksi serial menunjukkan startup Arduino tetapi gagal pada `PING`:** model Uno dengan CH340 bisa reset otomatis ketika port serial dibuka, dan LCD I2C dapat menambah durasi startup. `cat_servo_bridge.py` terbaru mencoba ulang `PING` selama sekitar 12 detik sebelum menyatakan gagal. Jalankan `git pull --ff-only` lalu ulangi `serial_servo_test.py`. Jika `PING` berhasil tetapi `EMERGENCY` tidak dikenali, kemungkinan Arduino masih menjalankan sketch lama; upload firmware LCD terbaru.

**Jika LCD menunjukkan kotak-kotak hitam padahal Arduino sudah membalas `ACK EMERGENCY`/`ACK RESET`:**

1. Matikan daya sebelum memindahkan kabel. Periksa LCD `GND -> GND`, `VCC -> 5V`, `SDA -> A4`, `SCL -> A5` pada **Arduino Uno**, bukan pada Pi.
2. Putar perlahan potensiometer kontras kecil pada backpack LCD. Kotak hitam sering terjadi saat kontras terlalu tinggi atau LCD belum terinisialisasi.
3. Periksa alamat I2C lewat perintah serial baru. Ini memerlukan upload firmware Arduino terbaru **sekali** (bukan flash Raspberry Pi).

```bash
cd ~/smart-cat-feeder
git pull --ff-only

# Tutup live_cam.py dan semua aplikasi yang memakai port /dev/ttyUSB0 terlebih dahulu.
~/.local/bin/arduino-cli compile --fqbn arduino:avr:uno \
  arduino/smart_cat_feeder_servo_bench_5s
~/.local/bin/arduino-cli upload --fqbn arduino:avr:uno \
  --port /dev/ttyUSB0 arduino/smart_cat_feeder_servo_bench_5s

.venv/bin/python serial_servo_test.py --port /dev/ttyUSB0 --i2c-scan
```

Contoh hasil: `I2C_FOUND 0x27` atau `I2C_FOUND 0x3F`. Bila `0x27` ditemukan, kode awal LCD sudah benar dan fokus berikutnya adalah kontras/kabel/susunan pin backpack/library. Bila `0x3F` ditemukan, ubah alamat di sketch dari `0x27` ke `0x3F`, compile, lalu upload kembali. Jika `I2C_SCAN_DONE 0`, Arduino tidak memperoleh respons dari modul apa pun: fokus pada SDA/SCL, VCC/GND, sambungan/solder backpack, atau modul I2C rusak.

**Jangan** jalankan `i2cdetect` pada Raspberry Pi untuk perangkat ini: LCD tersambung ke bus I2C **Arduino**, bukan Pi.

**Tes LCD tanpa menggerakkan servo:**

```bash
.venv/bin/python serial_servo_test.py \
  --port /dev/ttyUSB0 --lcd-demo
```

Tes tersebut menampilkan `Idle` sebentar, mengirim perintah `EMERGENCY` sehingga LCD menunjukkan `Emergency` sekitar 4 detik, kemudian `RESET` kembali ke `Idle`. Script memakai **satu koneksi serial** sehingga reset otomatis Uno saat port dibuka tidak mengganggu demonstrasi.

**Tes status Feeding dengan servo tanpa makanan dan mekanisme:**

```bash
.venv/bin/python serial_servo_test.py \
  --port /dev/ttyUSB0 --feed
```

LCD akan menampilkan `Feeding` sewaktu servo bergerak, kemudian `Idle` ketika siklus selesai. Gerakan servo hanya untuk pengujian tanpa pakan.

**Mode kamera YOLO11 + LCD + servo tetap sama:**

```bash
.venv/bin/python live_cam.py --source 0 --port 8767 --imgsz 320 \
  --cat-only --arduino-port /dev/ttyUSB0 \
  --stable-hits 3 --cooldown-seconds 5 \
  --rearm-seconds 5 --bench-test
```

Program di Raspberry Pi tetap memuat **satu model `models/yolo11.pt`**, tanpa usia. Perintah `FEED` yang dikirim Pi akan mengubah LCD secara otomatis. Jangan gunakan cooldown 5 detik dengan pakan asli; untuk uji feeder terpasang harus ada pengukuran porsi dan pengamanan hardware/software tambahan.

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
