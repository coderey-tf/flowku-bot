# Walkthrough — WhatsApp Bot Category Alignment, Verification, Confirmation Flow & Reminder Toggle

Saya telah berhasil mengimplementasikan seluruh rencana perubahan untuk menyelaraskan kategori transaksi *bot* WhatsApp dengan aplikasi utama Flowku, mendukung kategori kustom dari Firestore, mengintegrasikan alur verifikasi nomor WhatsApp pengguna, menambahkan alur konfirmasi transaksi rancu (ambigu), serta menambahkan fitur switch/toggle untuk mengaktifkan/menonaktifkan pengingat WhatsApp.

---

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
- **Verifikasi Nomor (`verify_whatsapp`)**: Mengubah status `waVerified` menjadi `True` pada *document user* di Firestore ketika pengguna mengirim pesan verifikasi.
- **Transaksi Pending (`save_pending_transaction`)**: Menyimpan data transaksi sementara ke field `pendingTransaction` pada dokumen pengguna untuk alur konfirmasi transaksi yang rancu/kurang jelas.
- **Reminder Multi-User (`get_verified_users_for_reminder`)**: Mengambil profil semua pengguna terverifikasi yang mengaktifkan pengingat (`waReminderEnabled` bernilai `True` atau tidak diset `False`).

### 3. Bot Main & Scheduler (Handler & Alur Konfirmasi & Reminder)
Files: [main.py](file:///d:/Project%20Website/flowku/bot/main.py), [reminder.py](file:///d:/Project%20Website/flowku/bot/reminder.py)
- **Alur Konfirmasi Transaksi Rancu**:
  - Transaksi dideteksi sebagai "rancu" jika kategorinya adalah fallback (`other_expense`/`other_income`) atau jika keterangannya kosong.
  - Jika rancu, bot tidak langsung menyimpannya tetapi menyimpan data tersebut di state pending (`pendingTransaction` di Firestore) dan mengirim pertanyaan konfirmasi interaktif.
  - Jika pengguna membalas dengan kata kunci **Ya** (`ya`, `y`, `ok`, `oke`, `yes`, `simpan`), transaksi disimpan permanen ke Firestore.
  - Jika pengguna membalas dengan kata kunci **Batal** (`batal`, `b`, `tidak`, `no`, `cancel`), transaksi pending dihapus dan pencatatan dibatalkan.
  - Jika pengguna mengirim pesan/instruksi baru lainnya, transaksi pending lama dibatalkan secara otomatis dan pesan baru diproses secara normal.
- **Reminder Multi-User & Selektif**:
  - Mengubah fungsi `cek_dan_kirim_reminder` di `reminder.py` agar melakukan perulangan (*looping*) untuk semua pengguna terverifikasi di Firestore.
  - Memeriksa preferensi `waReminderEnabled` milik masing-masing pengguna. Jika diset `False` oleh pengguna lewat aplikasi, maka pengiriman pengingat harian WhatsApp akan dilewati untuk nomor tersebut.

### 4. App Frontend (Profile Page & Toggle Pengingat)
Files: [ProfilePage.jsx](file:///d:/Project%20Website/flowku/app/src/pages/ProfilePage.jsx)
- **UI Toggle Switch**: Menambahkan kontrol visual switch toggle berwarna hijau untuk **Pengingat Pencatatan** tepat di bawah input nomor WhatsApp.
- **Sync State dengan Firestore**:
  - Menggunakan Hook `useEffect` untuk menyinkronkan status switch dengan data `waReminderEnabled` dari Firestore.
  - Saat switch digeser, memicu `handleToggleReminder` yang langsung memanggil `updateDoc` ke Firestore untuk mengubah `waReminderEnabled` (disertai pembaruan `updatedAt` dan notifikasi toast sukses).
- **Verifikasi Input Nomor**: Menambahkan pembersihan format otomatis `formatPhone` saat pengguna memasukkan nomor WhatsApp agar seragam menggunakan kode negara `628xxx` dan membatasi input minimal 11 karakter.

---

## Hasil Pengujian Otomatis (Automated Testing Results)

Semua pengujian dirancang berjalan secara lokal tanpa memerlukan Firestore/WAHA asli menggunakan *mocking*. Pengujian telah sukses dijalankan dengan hasil kelulusan **100%**:

1. **Parser & Nominal Unit Test** ([local_test_nominal.py](file:///d:/Project%20Website/flowku/bot/local_test_nominal.py))
   - Menguji 22 variasi format nominal dan 12 jenis kalimat transaksi.
   - **Hasil**: 34/34 Lulus (100% OK).

2. **Integration / User Journey Test** ([local_test_behavior.py](file:///d:/Project%20Website/flowku/bot/local_test_behavior.py))
   - Menguji alur lengkap user (belum terdaftar, verifikasi via WA, pencatatan transaksi default/kustom, cek laporan/budget, dan **alur konfirmasi transaksi rancu**).
   - **Hasil**: 24/24 Skenario Lulus + 5 Skenario Konfirmasi Lulus (100% OK).

3. **FastAPI Webhook Test** ([local_test_api.py](file:///d:/Project%20Website/flowku/bot/local_test_api.py))
   - Memvalidasi endpoint `/webhook` dan payload dari WAHA (ditambahkan pengaturan UTF-8 agar console Windows tidak error).
   - **Hasil**: 5/5 API Scenario Lulus (100% OK).

4. **Edge Case Test** ([local_test_edge.py](file:///d:/Project%20Website/flowku/bot/local_test_edge.py))
   - Menguji kasus batas (deskripsi kosong, spasi saja, nominal Rp1 Miliar, simbol aneh, custom category kosong, tabrakan kata kunci jenis transaksi kustom, serta **mengirim konfirmasi 'ya' tanpa ada transaksi pending**).
   - **Hasil**: 11 parser edge cases, 3 category edge cases, dan 3 handler edge cases Lulus (100% OK).

---

## Rencana Pengujian Manual (Staging/Production)

1. **Uji Coba Pengaturan Pengingat (Reminder Toggle)**:
   - Di halaman Profil, klik switch/toggle **Pengingat Pencatatan** ke posisi OFF -> Verifikasi field `waReminderEnabled` di Firestore berubah menjadi `false`.
   - Klik toggle ke posisi ON -> Verifikasi field `waReminderEnabled` di Firestore berubah menjadi `true`.

2. **Uji Coba Verifikasi Bot**:
   - Kirim pesan `"Mulai Flowku"` ke bot -> Bot memverifikasi nomor.

3. **Uji Coba Transaksi Rancu & Konfirmasi**:
   - Kirim pesan `"50rb"` (keterangan kosong) -> Bot meminta konfirmasi. Balas `Ya` -> Verifikasi tersimpan.
   - Kirim pesan `"50.000 asdfg"` (kategori Lainnya) -> Balas `Batal` -> Verifikasi dibatalkan.
