"""
Flowku Bot — Suspicious Transaction Test
=========================================
Menguji deteksi transaksi mencurigakan / typo sebelum disimpan.
Fokus pada kasus seperti di screenshot: "10 m makan" → Rp10 (typo Rp10.000)
"""
import os
os.environ["TESTING"] = "true"
import sys
import io
import asyncio
import unittest.mock as mock

# Force UTF-8 output agar emoji tidak error di Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Mock dependencies
mock_firestore_db = mock.MagicMock()
sys.modules["firestore_db"] = mock_firestore_db
sys.modules["waha"] = mock.MagicMock()
sys.modules["ocr"] = mock.MagicMock()
sys.modules["reminder"] = mock.MagicMock()
sys.modules["apscheduler"] = mock.MagicMock()
sys.modules["apscheduler.schedulers"] = mock.MagicMock()
sys.modules["apscheduler.schedulers.asyncio"] = mock.MagicMock()

from parser import parse_catatan, format_rupiah
import main
from main import is_suspicious_transaction


# ─────────────────────────────────────────────
# PART 1: Unit test is_suspicious_transaction()
# ─────────────────────────────────────────────

SUSPICIOUS_CASES = [
    # (label, raw_text, catatan_dict, expect_suspicious)
    # --- Kasus SUSPICIOUS (harus kena konfirmasi) ---
    (
        "Typo: '10 m makan' → Rp10 (suffix 'm' tidak valid)",
        "10 m makan",
        {"type": "expense", "amount": 10, "category": "food", "description": "Makan"},
        True,
    ),
    (
        "Typo: '5 ml kopi' → Rp5 (suffix 'ml' tidak valid)",
        "5 ml kopi",
        {"type": "expense", "amount": 5, "category": "food", "description": "Kopi"},
        True,
    ),
    (
        "Nominal sangat kecil: Rp100 (kemungkinan typo)",
        "100 makan",
        {"type": "expense", "amount": 100, "category": "food", "description": "Makan"},
        True,
    ),
    (
        "Nominal sangat kecil: Rp1 (jelas typo)",
        "1 transport",
        {"type": "expense", "amount": 1, "category": "transport", "description": "Transport"},
        True,
    ),
    (
        "Nominal terlalu besar: Rp500jt",
        "500jt makan",
        {"type": "expense", "amount": 500_000_000, "category": "food", "description": "Makan"},
        True,
    ),
    (
        "Typo suffix 'rb' tapi nempel jadi 'makan rb' (harusnya aman, ini edge)",
        "10rb makan rb",
        {"type": "expense", "amount": 10_000, "category": "food", "description": "Makan rb"},
        False,  # 'rb' valid suffix, tapi ini di deskripsi — expected NOT suspicious karena 'rb' ada di valid set
    ),
    # --- Kasus NORMAL (tidak boleh kena konfirmasi) ---
    (
        "Normal: '50rb makan siang'",
        "50rb makan siang",
        {"type": "expense", "amount": 50_000, "category": "food", "description": "Makan siang"},
        False,
    ),
    (
        "Normal: '25000 transport grab'",
        "25000 transport grab",
        {"type": "expense", "amount": 25_000, "category": "transport", "description": "Transport grab"},
        False,
    ),
    (
        "Normal: '3jt gaji bulanan'",
        "3jt gaji bulanan",
        {"type": "income", "amount": 3_000_000, "category": "salary", "description": "Gaji bulanan"},
        False,
    ),
    (
        "Normal: '10k kopi' (suffix 'k' valid)",
        "10k kopi",
        {"type": "expense", "amount": 10_000, "category": "food", "description": "Kopi"},
        False,
    ),
    (
        "Normal: '15rb parkir' (angka >= 500)",
        "15rb parkir",
        {"type": "expense", "amount": 15_000, "category": "transport", "description": "Parkir"},
        False,
    ),
    (
        "Normal: 'catat 80rb skincare' (angka normal, suffix valid)",
        "catat 80rb skincare",
        {"type": "expense", "amount": 80_000, "category": "beauty", "description": "Skincare"},
        False,
    ),
    (
        "Normal: '1jt freelance desain logo'",
        "1jt freelance desain logo",
        {"type": "income", "amount": 1_000_000, "category": "freelance", "description": "Freelance desain logo"},
        False,
    ),
    (
        "Batas bawah normal: Rp500 (tepat di batas, tidak suspicious)",
        "500 parkir",
        {"type": "expense", "amount": 500, "category": "transport", "description": "Parkir"},
        False,
    ),
    (
        "Batas atas normal: Rp100jt (tepat di batas, tidak suspicious)",
        "100jt deposito",
        {"type": "expense", "amount": 100_000_000, "category": "investment", "description": "Deposito"},
        False,
    ),
]


def run_unit_tests():
    print("=" * 65)
    print("  [PART 1] Unit Test: is_suspicious_transaction()")
    print("=" * 65)

    passed = 0
    failed = 0

    for label, raw_text, catatan, expect_suspicious in SUSPICIOUS_CASES:
        suspicious, reason = is_suspicious_transaction(raw_text, catatan)
        ok = suspicious == expect_suspicious
        status = "✅ LULUS" if ok else "❌ GAGAL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} [{label}]")
        print(f"  Input   : '{raw_text}' → amount={format_rupiah(catatan['amount'])}")
        print(f"  Expect  : suspicious={expect_suspicious}")
        print(f"  Got     : suspicious={suspicious}", end="")
        if reason:
            print(f", reason='{reason}'", end="")
        print()

    print(f"\n{'─'*65}")
    print(f"  Hasil: {passed} lulus, {failed} gagal dari {len(SUSPICIOUS_CASES)} test case")
    print(f"{'─'*65}")
    return failed == 0


# ─────────────────────────────────────────────
# PART 2: Integration test via handle_text_message
# ─────────────────────────────────────────────

INTEGRATION_CASES = [
    # (label, pesan_user, expect_contains, expect_NOT_contains)
    (
        "Typo '10 m makan' → harus minta konfirmasi ⚠️",
        "10 m makan",
        ["Konfirmasi Transaksi", "Rp10", "Apakah ini benar"],
        ["Pengeluaran tercatat"],
    ),
    (
        "Normal '50rb makan siang' → langsung tercatat",
        "50rb makan siang",
        ["Pengeluaran tercatat", "Rp50.000"],
        ["Konfirmasi Transaksi"],
    ),
    (
        "Normal '10rb makan' → langsung tercatat (Rp10.000 bukan Rp10)",
        "10rb makan",
        ["Pengeluaran tercatat", "Rp10.000"],
        ["Konfirmasi Transaksi"],
    ),
    (
        "Sangat kecil '5 makan' → minta konfirmasi (Rp5)",
        "5 makan",
        ["Konfirmasi Transaksi", "Rp5", "Apakah ini benar"],
        ["Pengeluaran tercatat"],
    ),
]


async def run_integration_tests():
    print("\n" + "=" * 65)
    print("  [PART 2] Integration Test: handle_text_message()")
    print("=" * 65)

    user_verified = {
        "uid": "uid_test",
        "waPhone": "6289999999999",
        "waVerified": True,
        "customCategories": [],
        "pendingTransaction": None,
    }

    main.get_user_by_phone = mock.MagicMock(return_value=user_verified)
    main.catat_transaksi = mock.MagicMock(return_value={"txId": "tx_test"})
    main.save_pending_transaction = mock.MagicMock(return_value=True)
    main.get_budget_status = mock.MagicMock(return_value={})
    main.hitung_total_hari_ini = mock.MagicMock(return_value={
        "pengeluaran": 75_000, "pemasukan": 0, "catatan": [{}]
    })

    passed = 0
    failed = 0

    for label, pesan, expect_contains, expect_not_contains in INTEGRATION_CASES:
        reply = await main.handle_text_message("6289999999999", pesan)
        ok = True

        missing = [s for s in expect_contains if s not in reply]
        found_bad = [s for s in expect_not_contains if s in reply]

        if missing or found_bad:
            ok = False

        status = "✅ LULUS" if ok else "❌ GAGAL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} [{label}]")
        print(f"  Input  : '{pesan}'")
        print(f"  Reply  :")
        for line in reply.splitlines():
            print(f"    {line}")
        if missing:
            print(f"  ⚠ Kurang : {missing}")
        if found_bad:
            print(f"  ⚠ Ada yg seharusnya tidak ada: {found_bad}")

    print(f"\n{'─'*65}")
    print(f"  Hasil: {passed} lulus, {failed} gagal dari {len(INTEGRATION_CASES)} test case")
    print(f"{'─'*65}")
    return failed == 0


if __name__ == "__main__":
    all_passed = True

    all_passed &= run_unit_tests()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    all_passed &= loop.run_until_complete(run_integration_tests())
    loop.close()

    print("\n" + "=" * 65)
    if all_passed:
        print("  🎉 SEMUA TEST LULUS!")
    else:
        print("  💥 ADA TEST YANG GAGAL — cek output di atas")
    print("=" * 65)
    sys.exit(0 if all_passed else 1)
