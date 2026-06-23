# Rencana Pengujian Lengkap (Testing Plan) — Flowku WhatsApp Bot

Dokumen ini mendefinisikan rencana pengujian menyeluruh untuk layanan WhatsApp Bot Flowku. Semua pengujian dirancang agar dapat berjalan secara lokal tanpa memerlukan koneksi Firestore atau server WhatsApp (WAHA) nyata dengan menggunakan teknik *mocking*.

---

## 1. Ruang Lingkup Pengujian

Pengujian mencakup fungsionalitas inti dari *bot* keuangan Flowku:
- **Parser (`parser.py`)**: Pengenalan nominal (berbagai format desimal & akhiran seperti `rb`, `k`, `ribu`, `jt`, `juta`), kategori bawaan & kustom, deteksi tipe transaksi (pemasukan & pengeluaran), serta parsing item OCR (foto struk).
- **Handler & Webhook (`main.py`)**: Pengenalan nomor pengguna, status verifikasi (`waVerified`), eksekusi perintah manual (`hari ini`, `bulan ini`, `anggaran`, `kategori`, `bantuan`), penanganan kesalahan, dan parsing payload webhook dari WAHA (legacy vs GOWS).
- **Edge Cases**: Penanganan input ekstrem (nominal sangat besar, deskripsi kosong, karakter khusus), limit anggaran, dan input tidak valid.

---

## 2. Level & Skenario Pengujian

### 2.1. Unit Testing — Parser (`parser.py`)
Menguji fungsi parser secara terisolasi dengan berbagai variasi input.

- **Nominal Formats (34 Test Cases)**:
  - Akhiran nominal: `50rb`, `50 rb`, `15k`, `15 k`, `25ribu`, `25 ribu`, `3jt`, `3 jt`, `2juta`, `2 juta`
  - Desimal: `1.5jt`, `2,5jt`, `1.5juta`, `0.5jt`
  - Plain angka & pemisah ribuan: `50000`, `50.000`, `1000000`, `1.000.000`
  - Awalan Rupiah: `rp50000`, `rp 50.000`, `rp50rb`, `rp3jt`
- **Kalimat Transaksi (12 Test Cases)**:
  - Format pengeluaran: `50rb makan siang`, `catat 25000 kopi`, `tagihan wifi 300rb`, `15k parkir motor`
  - Format pemasukan: `3jt gaji bulanan`, `masuk 500rb bonus`, `1jt freelance desain logo`
- **Deteksi Kategori**:
  - Kategori bawaan: makanan (`food`), transportasi (`transport`), belanja (`shopping`), dll.
  - Kategori pemasukan: gaji (`salary`), sampingan (`freelance`), dll.
  - Kategori kustom: mengambil label kategori kustom dari database profil pengguna (misalnya: `Nasi Padang` -> `custom_nasi_padang`).

### 2.2. Webhook Testing — Webhook Endpoint (`main.py` -> `/webhook`)
Menguji API endpoint `/webhook` menggunakan `FastAPI.testclient.TestClient` tanpa WAHA atau Firestore asli.

- **Payload Parsing (Legacy & GOWS)**:
  - Format legacy chatId (`6281234567890@c.us`)
  - Format GOWS (dengan payload `_data` -> `Info` -> `SenderAlt` atau `Chat`)
  - Filter `fromMe = True` (harus diabaikan bot agar tidak *looping*)
  - Filter `session` bukan `"default"` (harus diabaikan)
- **Status Respons HTTP**: Memastikan webhook selalu mengembalikan status HTTP 200 OK dengan format respons JSON yang sesuai.

### 2.3. Integration / Behavioral Testing — User Journey (`main.py` & `firestore_db.py`)
Menguji alur interaksi pengguna secara kronologis untuk mensimulasikan penggunaan nyata di lapangan.

- **Skenario 1: Pengguna Baru (Belum Terdaftar)**
  - Pengguna mengirim pesan -> Bot menolak akses karena nomor tidak terdaftar.
- **Skenario 2: Terdaftar tapi Belum Verifikasi**
  - Pengguna terdaftar mengirim pesan transaksi -> Bot menolak dan meminta verifikasi WhatsApp terlebih dahulu.
- **Skenario 3: Verifikasi Nomor ("Mulai Flowku")**
  - Pengguna mengirim pesan `"Mulai Flowku"` -> Status `waVerified` di Firestore menjadi `True` dan bot aktif.
- **Skenario 4: Pencatatan Transaksi Bawaan & Kustom**
  - Pengguna mengirim format pengeluaran & pemasukan -> Transaksi tersimpan ke Firestore dengan kategori dan jenis yang sesuai.
  - Pengguna mencatat kategori kustom yang diatur di Firestore.
- **Skenario 5: Laporan & Navigasi**
  - Pengguna meminta laporan (`hari ini`, `bulan ini`, `anggaran`, `kategori`, `bantuan`).
- **Skenario 6: Input Tidak Dikenali**
  - Pengguna mengirim pesan random -> Bot merespons dengan instruksi ramah menggunakan petunjuk *bantuan*.

### 2.4. Edge Case Testing (New Script)
Menguji kasus-kasus ekstrem atau tidak biasa untuk menghindari kegagalan sistem (*crash*).

- **Input kosong / spasi saja**
- **Nominal super besar** (contoh: 1 Miliar, 10 Miliar) untuk melihat perilaku limit numerik.
- **Pesan tanpa deskripsi** (contoh: hanya mengirim pesan `"50rb"` atau `"catat 25000"`) -> Harusnya sukses mencatat dengan deskripsi kosong dan kategori fallback.
- **Teks tanpa angka** (contoh: `"catat makan siang"`) -> Gagal parse karena tidak ada nominal.
- **Dua nominal dalam satu baris** (contoh: `"catat 50rb makan siang dan 20rb minum"`) -> Mengambil nominal pertama secara aman.
- **Karakter spesial dalam deskripsi** (contoh: `"50rb makan + es teh manis (level 3) & kerupuk!!!"`).
- **User dengan customCategories kosong** (`customCategories: []` atau `None`).

---

## 3. Cara Menjalankan Pengujian

Pengujian dilakukan menggunakan *virtual environment* Python lokal. Buka PowerShell/Terminal di direktori `bot` lalu jalankan perintah berikut:

### A. Persiapan Environment
Pastikan *virtual environment* sudah terpasang dependensinya:
```powershell
.venv\Scripts\pip install -r requirements.txt
```

### B. Menjalankan Unit & Nominal Test (Parser)
Menguji keakuratan parser nominal dan kalimat:
```powershell
.venv\Scripts\python local_test_nominal.py
```

### C. Menjalankan Integration / Behavioral Test
Menguji alur journey user dari belum terdaftar, verifikasi, hingga transaksi:
```powershell
.venv\Scripts\python local_test_behavior.py
```

### D. Menjalankan Webhook API Test
Menguji endpoint FastAPI dan parsing payload:
```powershell
.venv\Scripts\python local_test_api.py
```

### E. Menjalankan Edge Case Test (Akan Ditambahkan)
Menguji input ekstrem dan batasan bot:
```powershell
.venv\Scripts\python local_test_edge.py
```

---

## 4. Status & Kriteria Kelulusan

Untuk menyatakan bahwa bot Flowku siap di-deploy ke *production*, seluruh pengujian harus mencapai status kelulusan 100%.

| Level Pengujian | File Pengujian | Status Saat Ini | Kriteria Lulus |
| :--- | :--- | :--- | :--- |
| **Unit Test Parser** | `local_test_nominal.py` | 34/34 Nominal Lulus<br>12/12 Kalimat Lulus | Semua kasus parse bernilai benar sesuai ekspektasi. |
| **Integration/Behavior** | `local_test_behavior.py` | 24/24 Skenario Lulus | Seluruh alur WhatsApp user journey lancar dari awal hingga akhir. |
| **Webhook/API** | `local_test_api.py` | 5/5 Skenario API Lulus | FastAPI TestClient merespons 200 OK dengan format JSON valid. |
| **Edge Cases** | `local_test_edge.py` | *Belum Dibuat* | Program tidak *crash* dan menangani input ekstrem secara elegan. |

---

## 5. Rencana Manual E2E (Setelah Deploy)

Berikut adalah checklist pengujian manual setelah kode di-deploy ke server staging/production:

1. [ ] **User Signup**: Registrasi di aplikasi Flowku menggunakan nomor HP baru.
2. [ ] **Verifikasi WhatsApp**: Masuk ke profil -> isi nomor WA -> Klik tombol verifikasi -> Kirim `"Mulai Flowku"` dari WhatsApp Anda ke bot.
3. [ ] **Uji Chat Bot**:
   - Kirim `50rb makan siang` -> Terima balasan konfirmasi dari bot.
   - Periksa apakah data transaksi langsung muncul di aplikasi utama Flowku (Sinkronisasi Firestore).
4. [ ] **Uji Laporan**: Kirim `hari ini` -> Periksa keakuratan ringkasan transaksi.
5. [ ] **Uji Struk/OCR**: Kirim foto struk belanja -> Periksa apakah bot berhasil mengurai item-item belanja dan menyimpannya.
