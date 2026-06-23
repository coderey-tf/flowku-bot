"""
Flowku Bot — Behavioral User Journey Test
==========================================
Import langsung handle_text_message dari main, mock semua dependensi
eksternal (Firestore, WAHA, OCR, Reminder) via sys.modules SEBELUM import.
Tidak butuh server, tidak butuh Firestore, tidak butuh internet.
"""
import os
os.environ["TESTING"] = "true"
import asyncio
import sys
import io
import unittest.mock as mock

# Force UTF-8 output agar emoji di respons bot tidak error di Windows CP1252
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────────────────────────
# 1. PATCH: Semua modul yang butuh kredensial/koneksi eksternal
# ─────────────────────────────────────────────────────────────────
# Buat mock modul firestore_db lengkap dengan fungsi yang dipakai main.py
mock_firestore_db = mock.MagicMock()
sys.modules["firestore_db"] = mock_firestore_db

# Mock waha (send_text) agar tidak kirim pesan asli
mock_waha = mock.MagicMock()
sys.modules["waha"] = mock_waha

# Mock OCR
mock_ocr = mock.MagicMock()
sys.modules["ocr"] = mock_ocr

# Mock Reminder
mock_reminder = mock.MagicMock()
sys.modules["reminder"] = mock_reminder

# Mock APScheduler agar tidak error saat import main
mock_apscheduler = mock.MagicMock()
sys.modules["apscheduler"] = mock_apscheduler
sys.modules["apscheduler.schedulers"] = mock_apscheduler
sys.modules["apscheduler.schedulers.asyncio"] = mock_apscheduler

# ─────────────────────────────────────────────────────────────────
# 2. IMPORT main SETELAH semua mock terpasang
# ─────────────────────────────────────────────────────────────────
import main

# ─────────────────────────────────────────────────────────────────
# 3. DATA USER MOCK
# ─────────────────────────────────────────────────────────────────
USER_NOT_FOUND   = None

USER_UNVERIFIED  = {
    "uid": "uid_sari",
    "waPhone": "6281111111111",
    "waVerified": False,
    "customCategories": [],
}

USER_VERIFIED    = {
    "uid": "uid_sari",
    "waPhone": "6281111111111",
    "waVerified": True,
    "customCategories": [
        {"id": "custom_nasi_padang", "label": "Nasi Padang", "type": "expense"},
    ],
}

USER_PREMIUM     = {
    "uid": "uid_budi",
    "waPhone": "6282222222222",
    "waVerified": True,
    "isPremium": True,
    "customCategories": [
        {"id": "custom_desain", "label": "Desain Grafis", "type": "income"},
    ],
}

# ─────────────────────────────────────────────────────────────────
# 4. HELPER PRINT BERWARNA
# ─────────────────────────────────────────────────────────────────
def section(title):
    print(f"\n" + "="*62)
    print(f"  {title}")
    print("="*62)

def chat(phone, text):
    print(f"\nUser [{phone[-4:]}]:  \"{text}\"")

def bot_reply(text):
    lines = text.strip().split("\n")
    print("Bot:")
    for line in lines:
        print(f"        {line}")

# ─────────────────────────────────────────────────────────────────
# 5. RUNNER UTAMA
# ─────────────────────────────────────────────────────────────────
async def send(phone, text, user_mock, catat_result=None, verify_ok=True):
    """Simulasikan satu pesan masuk dan tampilkan respons handler."""
    chat(phone, text)

    # Pasang mock Firestore functions langsung ke namespace main
    main.get_user_by_phone   = mock.MagicMock(return_value=user_mock)
    main.verify_whatsapp     = mock.MagicMock(return_value=verify_ok)
    main.catat_transaksi     = mock.MagicMock(return_value=catat_result)
    main.save_pending_transaction = mock.MagicMock(return_value=True)
    main.save_ocr_result     = mock.MagicMock()
    main.hitung_total_hari_ini = mock.MagicMock(return_value={
        "pengeluaran": 75000, "pemasukan": 0, "catatan": [{}]
    })
    main.hitung_total_bulan_ini = mock.MagicMock(return_value={
        "pengeluaran": 1_200_000, "pemasukan": 2_500_000, "catatan": [{}] * 18
    })
    main.get_budget_status   = mock.MagicMock(return_value={
        "food": {"limit": 500_000, "spent": 430_000, "remaining": 70_000, "percentage": 86},
    })

    reply = await main.handle_text_message(phone, text)
    bot_reply(reply)

# ─────────────────────────────────────────────────────────────────
# 6. SKENARIO USER JOURNEY
# ─────────────────────────────────────────────────────────────────
async def run_all():
    print("\n" + "="*62)
    print(f"  FLOWKU BOT - BEHAVIORAL USER JOURNEY TEST")
    print("="*62)

    # ── Skenario 1: User Tak Dikenal ────────────────────────────
    section("SKENARIO 1 — Nomor belum terdaftar di Flowku")
    await send("6280000000000", "catat 50rb makan",    USER_NOT_FOUND)
    await send("6280000000000", "bantuan",              USER_NOT_FOUND)

    # ── Skenario 2: User Ada, WA Belum Diverifikasi ──────────────
    section("SKENARIO 2 — Terdaftar tapi belum verifikasi WhatsApp")
    await send("6281111111111", "hari ini",             USER_UNVERIFIED)
    await send("6281111111111", "catat 80rb belanja",   USER_UNVERIFIED)
    await send("6281111111111", "kategori",             USER_UNVERIFIED)

    # ── Skenario 3: Proses Verifikasi ───────────────────────────
    section("SKENARIO 3 — Mengirim pesan 'Mulai Flowku'")
    await send("6281111111111", "Mulai Flowku",         USER_UNVERIFIED, verify_ok=True)

    # ── Skenario 4: Pencatatan Pengeluaran (Berbagai Format) ──────
    section("SKENARIO 4 — Pengeluaran dengan berbagai format & kategori")
    cases = [
        ("catat 25000 makan siang",          "expense", 25_000,   "food"),
        ("50rb kopi starbucks",              "expense", 50_000,   "food"),
        ("catat 15k parkir motor",           "expense", 15_000,   "transport"),
        ("80rb skincare vitamin c",          "expense", 80_000,   "beauty"),
        ("200rb investasi saham",            "expense", 200_000,  "investment"),
        ("tagihan wifi 300rb",               "expense", 300_000,  "bills"),
        ("35rb obat apotek",                 "expense", 35_000,   "health"),
        ("catat 50.000 asdfg",               "expense", 50_000,   "other_expense"),
        ("catat 50rb asdfg",                 "expense", 50_000,   "other_expense"),
        ("catat rp25000 makan",              "expense", 25_000,   "food"),
    ]
    for text, tipe, amount, kategori in cases:
        await send("6281111111111", text, USER_VERIFIED, catat_result={
            "txId": "tx_abc", "uid": "uid_sari", "coupleId": "solo_uid_sari",
            "type": tipe, "amount": amount, "category": kategori
        })

    # ── Skenario 5: Pencatatan Pemasukan ─────────────────────────
    section("SKENARIO 5 — Pencatatan pemasukan berbagai tipe")
    incomes = [
        ("pemasukan 3jt gaji bulanan",       "income", 3_000_000, "salary"),
        ("masuk 500rb bonus",                "income", 500_000,   "bonus"),
        ("1jt freelance desain logo",        "income", 1_000_000, "freelance"),
        ("transfer masuk 200rb dari mama",   "income", 200_000,   "transfer"),
    ]
    for text, tipe, amount, kategori in incomes:
        await send("6281111111111", text, USER_VERIFIED, catat_result={
            "txId": "tx_def", "uid": "uid_sari", "coupleId": "solo_uid_sari",
            "type": tipe, "amount": amount, "category": kategori
        })

    # ── Skenario 6: Kategori Kustom ──────────────────────────────
    section("SKENARIO 6 — Menggunakan kategori kustom (Nasi Padang)")
    await send("6281111111111", "35rb Nasi Padang siang", USER_VERIFIED, catat_result={
        "txId": "tx_ghi", "uid": "uid_sari", "coupleId": "solo_uid_sari",
        "type": "expense", "amount": 35_000, "category": "custom_nasi_padang"
    })

    # ── Skenario 7: Perintah Laporan & Navigasi ──────────────────
    section("SKENARIO 7 — Perintah laporan & navigasi")
    cmds = ["hari ini", "bulan ini", "anggaran", "kategori", "bantuan"]
    for cmd in cmds:
        await send("6281111111111", cmd, USER_VERIFIED)

    # ── Skenario 8: Input Tidak Dikenali ─────────────────────────
    section("SKENARIO 8 — Pesan tidak dikenali")
    unknowns = ["halo bot", "tolong catat semuanya", "apa itu flowku?"]
    for msg in unknowns:
        await send("6281111111111", msg, USER_VERIFIED)

    # ── Skenario 9: Alur Konfirmasi Transaksi Rancu ────────────────
    section("SKENARIO 9 — Konfirmasi Transaksi Rancu (Ambigu)")
    
    # 9a. Transaksi rancu (kategori other_expense)
    print("\n[9a. Kirim transaksi rancu - kategori 'other_expense']")
    await send("6281111111111", "catat 50rb asdfg", USER_VERIFIED)

    # 9b. Konfirmasi YA
    print("\n[9b. Kirim konfirmasi 'Ya']")
    USER_WITH_PENDING_EXPENSE = {
        **USER_VERIFIED,
        "pendingTransaction": {
            "type": "expense",
            "amount": 50000,
            "category": "other_expense",
            "description": "Asdfg"
        }
    }
    await send("6281111111111", "ya", USER_WITH_PENDING_EXPENSE, catat_result={
        "txId": "tx_abc", "uid": "uid_sari", "coupleId": "solo_uid_sari",
        "type": "expense", "amount": 50000, "category": "other_expense"
    })

    # 9c. Transaksi rancu (deskripsi kosong)
    print("\n[9c. Kirim transaksi rancu - keterangan kosong]")
    await send("6281111111111", "50rb", USER_VERIFIED)

    # 9d. Konfirmasi BATAL
    print("\n[9d. Kirim konfirmasi 'Batal']")
    USER_WITH_PENDING_PLAIN = {
        **USER_VERIFIED,
        "pendingTransaction": {
            "type": "expense",
            "amount": 50000,
            "category": "other_expense",
            "description": ""
        }
    }
    await send("6281111111111", "batal", USER_WITH_PENDING_PLAIN)

    # 9e. Batal otomatis jika ada transaksi pending tapi mengirim pesan baru
    print("\n[9e. Batal otomatis saat menerima instruksi baru]")
    await send("6281111111111", "hari ini", USER_WITH_PENDING_PLAIN)

    print("\n" + "="*62)
    print("  [OK] Semua skenario berhasil diuji!")
    print("="*62 + "\n")

if __name__ == "__main__":
    asyncio.run(run_all())
