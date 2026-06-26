# Ringkasan Implementasi OCR Flowku Bot
## Gemini Vision + Tesseract Pre-check Pipeline

---

## 1. ARSITEKTUR SISTEM

```
Foto masuk (WhatsApp)
    │
    ▼
┌─────────────────────────┐
│   QUICK RESPONSE        │  "📸 Sedang membaca struk..."
│   (instant, 0 detik)    │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   TESSERACT PRE-CHECK   │  Filter murah (gratis, lokal)
│   (~1-2 detik)          │  Cek: ada teks? ada sinyal struk?
└───────────┬─────────────┘
            │
     ┌──────┴──────┐
     │             │
  DITOLAK        LOLOS
     │             │
     ▼             ▼
  ❌ Pesan     ┌──────────────────────┐
  error       │  GEMINI 2.5 FLASH    │  Structured extraction
              │  (~2-3 detik)        │  Langsung parse → JSON items
              └──────────┬───────────┘
                         │
                  ┌──────┴──────┐
                  │             │
              ITEMS[]        ITEMS=[]
                  │             │
                  ▼             ▼
              ┌────────┐   ❌ Pesan "bukan struk"
              │ PREVIEW │
              │ + EDIT  │
              │ + HAPUS │
              └────┬────┘
                   │
              User: "ya"
                   │
                   ▼
              ✅ Simpan ke Firestore
```

---

## 2. KOMPONEN YANG DIIMPLEMENTASI

### 2.1 Quick Response
- **Lokasi**: `main.py` → webhook handler
- **Fungsi**: Kirim "📸 Sedang membaca struk..." sebelum proses OCR
- **Tujuan**: User tahu bot sedang kerja, tidak menunggu diam

### 2.2 Tesseract Pre-check (`is_receipt_image()`)
- **Lokasi**: `ocr.py`
- **Fungsi**: Filter cepat apakah gambar = struk atau bukan
- **Biaya**: GRATIS (Tesseract lokal)
- **Kecepatan**: ~1-2 detik
- **Logika**:
  ```
  1. OCR gambar dengan Tesseract (preprocessing ringan)
  2. Hitung "sinyal positif" (Rp, total, harga, kasir, dll)
  3. Hitung "sinyal negatif" (GPS, chat, UI, social media, dll)
  4. Keputusan:
     - signal >= 2 → lolos
     - signal >= 1 + ada pola harga → lolos
     - ada sinyal negatif → TOLAK
     - tidak ada sinyal + tidak ada harga → TOLAK
     - tidak ada sinyal + ada harga → lolos (struk thermal)
  ```
- **Sinyal positif** (30+ keyword): rp, total, subtotal, harga, bayar, cash, kasir, alfamart, indomaret, pertamina, shell, dll
- **Sinyal negatif** (40+ keyword): whatsapp, chat, instagram, tiktok, settings, login, gps, latitude, longitude, kecamatan, wib, dll
- **Limitasi**:
  - Tesseract sering salah baca struk thermal (hasil: noise/gibberish)
  - Font tertentu tidak bisa dibaca
  - Screenshot kadang lolos kalau Tesseract baca sebagai noise

### 2.3 Item Name Validation (`_is_valid_item_name()`)
- **Lokasi**: `ocr.py`
- **Fungsi**: Filter item name yang terlihat seperti OCR noise
- **Logika**:
  ```
  1. Rasio huruf < 60% → tolak (terlalu banyak simbol/angka)
  2. Ada 2+ karakter noise (| [ ] { } ~ £ : ; = + _ # @) → tolak
  3. Terlalu pendek (< 3 huruf setelah bersih) → tolak
  4. Mengandung kata non-item (whatsapp, chat, gps, dll) → tolak
  ```
- **Contoh**:
  - ❌ "~ soni wibisono [+:" → noise chars
  - ❌ "| Gi jumiah box %ekornya:" → noise chars
  - ✅ "Indomie Goreng" → valid
  - ✅ "Aqua 600ml" → valid

### 2.4 Gemini 2.5 Flash Structured OCR (`ocr_gemini_structured()`)
- **Lokasi**: `ocr.py`
- **Fungsi**: Extract items dari struk langsung jadi JSON
- **Biaya**: 1 API call per struk (20 RPD free tier)
- **Kecepatan**: ~2-3 detik
- **Input**: Gambar struk
- **Output**: `[{"nama": "Indomie", "harga": 3500, "kategori": "food"}, ...]`
- **Prompt**:
  ```
  - Validasi: apakah gambar ini benar-benar struk/nota?
  - Jika bukan (GPS, screenshot, foto biasa) → return []
  - Jika ya → extract items dengan harga dan kategori
  - Kategori: food, transport, shopping, health, bills, dll
  - Aturan khusus BBM: Pertalite → "Bensin Pertalite", kategori transport
  - Aturan khusus minimarket: kategorikan per ISI (mie→food, sabun→home)
  - DO NOT invent items from random numbers!
  ```
- **Error handling**:
  - 429 (rate limit) → log warning, fallback ke Tesseract
  - JSON parse error → return None
  - Other errors → return None

### 2.5 Gemini Text OCR (`ocr_gemini()`)
- **Fungsi**: Extract teks mentah dari gambar (fallback)
- **Sama dengan structured, tapi return teks biasa

### 2.6 Tesseract OCR (`ocr_tesseract()`)
- **Fungsi**: OCR lokal, fallback terakhir
- **Preprocessing**: grayscale → contrast → sharpness → median filter → adaptive threshold (numpy)
- **Config**: PSM 6 → PSM 4 → raw image (coba bertahap)

### 2.7 Parser Keywords (`parser.py`)
- **Fuel/BBM**: pertalite, pertamax, shell, pertamina, spbu, solar, premium, dexlite, turbo, ron, bio solar
- **Minimarket**: alfamart, indomaret, circle k, lawson, family mart, minimarket, mart
- **BPJS**: dipindah dari "bills" ke "health" (bpjs = kesehatan, bukan tagihan)
- **"bp" dihapus**: terlalu luas, bisa match "bpjs"

### 2.8 Preview + Konfirmasi (`format_ocr_preview()`)
- **Format**:
  ```
  🤖 AI Struk terbaca! 3 item ditemukan:

    1. 🍔 Indomie Goreng: Rp3.500 (food)
    2. 🍔 Aqua 600ml: Rp3.000 (food)
    3. 🏠 Sabun Lifebuoy: Rp4.500 (home)

  💸 Total: Rp11.000

  💾 Simpan semua item ke catatan?
  • Balas *Ya* / *Ok* untuk simpan
  • Balas *Batal* untuk batal
  • *hapus 1,3* — hapus item no 1 & 3
  • *edit 1 5000 makan* — ubah item no 1
  ```

### 2.9 Edit/Hapus Handler
- **Hapus**: `hapus 1,3` → hapus item no 1 & 3, tampil preview baru
- **Edit**: `edit 1 8000 indomie goreng pedas` → ubah item no 1
- **Konfirmasi**: `ya` → simpan semua, `batal` → buang semua
- **Anti-auto-cancel**: kalau user ketik salah saat OCR pending, bot minta pilih ya/batal/hapus/edit (bukan auto-cancel)

### 2.10 Foto Baru Saat Pending
- Kalau user kirim foto baru saat ada OCR pending:
  - Warning: "⚠️ Struk sebelumnya (3 item, Rp50.000) dibatalkan"
  - Proses foto baru

---

## 3. URUTAN EKSEKUSI (SAAT USER KIRIM FOTO)

```
1. User kirim foto ke WhatsApp bot
2. Bot: "📸 Sedang membaca struk..." (instant)
3. Download gambar dari WAHA
4. Tesseract pre-check (~1-2 detik)
   - Jika ditolak → return pesan error detail
   - Jika lolos → lanjut ke Gemini
5. Gemini structured OCR (~2-3 detik)
   - Jika 429 → fallback ke Tesseract
   - Jika return [] → "bukan struk"
   - Jika return items → filter dengan _is_valid_item_name()
6. Tampilkan preview dengan nomor, emoji, kategori, total
7. User bisa: ya / batal / hapus / edit
8. Simpan ke Firestore
```

---

## 4. HASIL TESTING

| Test | Hasil |
|------|-------|
| Fuel Detection (pertalite, pertamax, shell, dll) | ✅ 8/8 |
| Minimarket Detection (alfamart, indomaret, circle k) | ✅ 4/4 |
| BPJS No False Positive | ✅ 3/3 |
| Pre-check Receipt | ✅ 3/3 |
| Pre-check Blank Image | ✅ ditolak |
| Pre-check Monitor Screenshot | ✅ ditolak (GPS/timestamp) |
| Gemini JSON Parsing (normal, markdown, prefix, invalid) | ✅ 5/5 |
| OCR Preview Format | ✅ 5/5 |
| Edit/Hapus Logic | ✅ 4/4 |
| Item Name Validation | ✅ 11/11 |
| Gemini API Connection | ✅ OK |

---

## 5. LIMITASI & MASALAH

### 5.1 Tesseract Pre-check
- **Struk thermal**: Tesseract sering gagal baca (hasil noise)
- **Font non-standal**: tidak bisa dibaca
- **Screenshot WhatsApp**: kadang lolos (Tesseract baca sebagai noise, bukan teks)
- **Solusi**: pre-check hanya filter kasar, Gemini jadi hakim akhir

### 5.2 Gemini API
- **Rate limit**: 20 RPD (requests per day) di free tier
- **Biaya**: 1 API call per struk
- **Latensi**: ~2-3 detik per panggilan
- **Hallucination**: kadang "memaksa" angka jadi harga (GPS → harga, timestamp → harga)
- **Solusi**: prompt lebih ketat + filter _is_valid_item_name()

### 5.3 Akurasi Kategori
- **Minimarket**: Gemini kadang salah kategorikan (mie→shopping instead of food)
- **BBM**: cukup akurat (Bensin Pertalite → transport)
- **Lainnya**: tergantung kualitas gambar dan kejelasan struk

### 5.4 Edge Cases
- Struk dengan tulisan tangan → sulit dibaca
- Struk bahasa asing → mungkin salah parse
- Struk dengan format non-standar → item tidak terdeteksi
- Foto miring/buram → OCR gagal

---

## 6. REKOMENDASI UNTUK EFEKTIF & EFISIEN

### 6.1 Hemat API Call (20 RPD)
- Pre-check sudah agresif (tolak non-receipt sebelum Gemini)
- Pertimbangkan: cache hasil OCR untuk gambar yang sama (hash gambar)
- Pertimbangkan: batch processing (kumpulkan beberapa struk, proses sekaligus)

### 6.2 Upgrade API Tier
- **Google AI Studio**: bayar untuk lebih dari 20 RPD
- **Google Cloud Vision**: bayar per use, lebih banyak quota
- **Alternatif**: OpenAI GPT-4 Vision, Claude Vision (bandingkan harga)

### 6.3 Optimasi Pre-check
- Pakai OpenCV (cv2) untuk preprocessing lebih cepat dari numpy
- Pakai model ML ringan untuk klasifikasi receipt vs non-receipt (bukan Tesseract)
- Contoh: MobileNet/EfficientNet fine-tuned untuk receipt classification

### 6.4 Optimasi Gemini Prompt
- Prompt yang lebih spesifik → hasil lebih akurat
- Tambah few-shot examples di prompt
- Pertimbangkan: fine-tune model untuk domain struk Indonesia

### 6.5 Hybrid Approach
- **Tier 1** (gratis): Tesseract pre-check + regex parsing
- **Tier 2** (murah): Gemini Flash untuk struk yang lolos pre-check
- **Tier 3** (mahal): Gemini Pro untuk struk yang gagal di Flash
- Otomatis tier down saat limit habis

### 6.6 Monitoring & Logging
- Log setiap API call (timestamp, success/fail, items extracted)
- Monitor RPD usage (berapa sisa quota)
- Alert saat quota hampir habis

---

## 7. FILE YANG DIMODIFIKASI

| File | Perubahan |
|------|-----------|
| `ocr.py` | Gemini OCR, pre-check, item validation, fallback |
| `main.py` | Quick response, preview format, edit/hapus handler |
| `parser.py` | Fuel keywords, minimarket keywords, BPJS fix |
| `config.py` | GEMINI_API_KEY |
| `.env` | GEMINI_API_KEY value |
| `test_gemini_ocr.py` | Test suite (7 test categories) |

---

## 8. DEPENDENCIES

```
google-genai          # Gemini API client (new, not deprecated)
pytesseract           # Tesseract OCR wrapper
tesseract-ocr         # Tesseract engine
tesseract-ocr-ind     # Indonesian language pack
Pillow                # Image processing
numpy                 # Adaptive threshold (heavy preprocessing)
httpx                 # Async HTTP client
```

---

*Dokumen dibuat: 26 Juni 2026*
*Status: Production-ready dengan limitasi 20 RPD*
