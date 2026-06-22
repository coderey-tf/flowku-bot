# Walkthrough — WhatsApp Bot Category Alignment & Verification Flow

Saya telah berhasil mengimplementasikan perubahan yang direncanakan untuk menyelaraskan kategori transaksi *bot* WhatsApp dengan aplikasi utama Flowku, mendukung kategori kustom dari Firestore, dan menambahkan alur verifikasi nomor WhatsApp pengguna.

## Perubahan yang Dilakukan

### 1. Bot Parser
File: [parser.py](file:///d:/Project%20Website/flowku/bot/parser.py)
- **Default Category Keywords**: Menambahkan kategori baru (`beauty`, `home`, `investment`, `social`, `saving`, `other_expense`) beserta kata kunci pencocokannya.
- **Income Category Keywords**: Menambahkan pemetaan kategori khusus pemasukan (`salary`, `freelance`, `business`, `investment_in`, `bonus`, `transfer`, `other_income`).
- **Logika `detect_category`**:
  - Mengecek kecocokan kategori kustom terlebih dahulu berdasarkan label kategori yang dimiliki user di Firestore.
  - Memisahkan kata kunci berdasarkan jenis transaksi (`expense` vs `income`).
  - Mengembalikan *fallback* default `other_expense` (untuk pengeluaran) dan `other_income` (untuk pemasukan) alih-alih `"other"`.
- **Fungsi Parser (`parse_catatan` & `parse_ocr_items`)**: Menerima parameter `custom_categories` dan meneruskannya ke fungsi deteksi kategori.

### 2. Firestore Database Helper
File: [firestore_db.py](file:///d:/Project%20Website/flowku/bot/firestore_db.py)
- Menambahkan fungsi `verify_whatsapp(phone)` untuk mengubah status `waVerified` menjadi `True` pada *document user* di Firestore ketika pengguna mengirim pesan verifikasi.

### 3. Bot Main (Handler & Verifikasi)
File: [main.py](file:///d:/Project%20Website/flowku/bot/main.py)
- **Fitur Verifikasi Otomatis**:
  - Cek keberadaan user berdasar nomor WA. Jika belum terdaftar, bot menolak akses.
  - Jika pesan yang masuk adalah `"mulai flowku"`, status `waVerified` di Firestore diubah menjadi `True`, lalu dikirim pesan konfirmasi selamat datang.
  - Jika belum terverifikasi (`waVerified = False`), bot menolak perintah pencatatan/laporan dan menginstruksikan pengguna untuk melakukan verifikasi terlebih dahulu.
- **Penanganan Kategori Kustom**: Meneruskan array `customCategories` milik user dari Firestore ke parser.
- **Privasi Pengguna**: Memperbaiki rujukan `OWNER_PHONE` menjadi `phone` (nomor pengirim pesan) pada perintah laporan (`cmd_hari_ini`, `cmd_bulan_ini`, `cmd_anggaran`, `format_catatan_msg`) sehingga data keuangan tidak bocor antar pengguna.
- **Perbaikan Fallback Kategori**: Mengubah default fallback kategori dari `"other"` menjadi `"other_expense"` dalam pembentukan ringkasan laporan.

### 4. App Frontend
Files: [ProfilePage.jsx](file:///d:/Project%20Website/flowku/app/src/pages/ProfilePage.jsx), [.env.local](file:///d:/Project%20Website/flowku/app/.env.local), [.env.example](file:///d:/Project%20Website/flowku/app/.env.example)
- Mengubah badge WhatsApp Bot dari `SEGERA HADIR` menjadi status aktif dinamis (`AKTIF` / `BELUM AKTIF`).
- Menambahkan tombol **Verifikasi WhatsApp** (berwarna hijau khas WhatsApp `#25D166`) yang mengarahkan ke link `wa.me/<nomor-bot>?text=Mulai+Flowku` apabila nomor WA telah disimpan di profil namun belum diverifikasi.
- Menambahkan konfigurasi `VITE_WA_BOT_NUMBER` di file environment agar nomor bot mudah dikonfigurasi.

---

## Rencana Pengujian Manual

1. **Uji Coba Pengguna Baru / Belum Terdaftar**:
   - Kirim pesan apa saja dari nomor WhatsApp baru ke bot.
   - **Hasil Yang Diharapkan**: Bot merespons bahwa nomor belum terdaftar dan instruksi pendaftaran di aplikasi.

2. **Uji Coba Verifikasi Bot**:
   - Masuk ke aplikasi utama Flowku -> Masuk ke Halaman Profil -> Masukkan Nomor WA -> Simpan.
   - Klik tombol **Verifikasi WhatsApp** yang muncul.
   - Kirim pesan `"Mulai Flowku"` ke bot.
   - **Hasil Yang Diharapkan**: Bot memverifikasi nomor, status di aplikasi berubah menjadi `AKTIF`/`Terverifikasi`, dan bot siap digunakan.

3. **Uji Coba Pencatatan Transaksi**:
   - Kirim pesan `"catat 50rb makan siang"` -> Masuk ke kategori `food` (Makan & Minum).
   - Kirim pesan `"pemasukan 500rb gaji"` -> Masuk ke tipe pemasukan kategori `salary` (Gaji).
   - Kirim pesan `"catat 50rb asdfg"` -> Masuk ke kategori fallback `other_expense`.
   - Kirim pesan `"catat 100rb beli skincare"` -> Masuk ke kategori baru `beauty` (Kecantikan).
   - Kirim pesan `"hari ini"` -> Laporan terformat rapi sesuai kategori dengan emoji yang sesuai.
