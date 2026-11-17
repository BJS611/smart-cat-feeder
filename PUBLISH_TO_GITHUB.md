# Upload repository ke GitHub

GitHub project yang direkomendasikan: `BJS611/smart-cat-feeder` (private terlebih dahulu).

## Opsi A — GitHub CLI dari laptop Parrot OS

Instal GitHub CLI, login, lalu masuk ke folder ini (yang berisi README.md dan models/):

```bash
sudo apt update && sudo apt install -y git gh
# Jalankan jika belum login
gh auth login
cd /path/ke/smart-cat-feeder

git init -b main
git add .
git commit -m "feat: add Raspberry Pi 5 AI smoke test and setup guide"
gh repo create BJS611/smart-cat-feeder --private --source=. --remote=origin --push
```

Jika `git commit` meminta identitas, atur `git config --global user.name` dan `git config --global user.email` memakai identitas GitHub kamu (jangan masukkan token).

Jika repository **sudah dibuat** di GitHub, ganti perintah terakhir dengan:

```bash
git remote add origin https://github.com/BJS611/smart-cat-feeder.git
git push -u origin main
```

Jangan menjalankan `git init` bila folder ini sudah berupa repository Git. Jika remote `origin` sudah ada, gunakan `git remote -v` untuk memeriksa sebelum menambah.

## Opsi B — Buat repository lewat GitHub web

Buka https://github.com/new, pilih nama `smart-cat-feeder`, buat private repository kosong (jangan otomatis membuat README). Kemudian gunakan perintah `git remote add origin ...` dan `git push ...` seperti di atas.

Setelah push, jalankan perintah `git clone` dan `bash install_pi.sh` di Raspberry Pi seperti dalam README utama.

Model biner total sekitar 16.6 MB (masing-masing <100 MB), sehingga masih dapat dimasukkan dalam Git repository standar. Repo bersifat private adalah default aman, namun berkas `.pt` ini tidak mengandung token API. Jangan commit dataset berlisensi tidak jelas atau kredensial.
