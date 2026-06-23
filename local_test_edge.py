"""
Flowku Bot — Edge Case Test
===========================
Menguji parser dan main handler terhadap input ekstrem atau tidak biasa
untuk memastikan tidak terjadi error/crash pada aplikasi.
"""
import sys
import io
import unittest.mock as mock

# Force UTF-8 output agar emoji di respons bot tidak error di Windows CP1252
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

# Import parser dan main
from parser import parse_catatan, parse_amount, detect_category
import main

def run_edge_cases():
    print("=" * 62)
    print("  RUNNING FLOWKU BOT EDGE CASE TESTS")
    print("=" * 62)
    
    # ─── PART 1: parser.py Edge Cases ─────────────────────────────
    print("\n--- [PART 1] Testing parser.py Edge Cases ---")
    
    parser_cases = [
        # (label, input, expected_amount, expected_desc, expected_category)
        ("Input kosong", "", None, "", ""),
        ("Hanya spasi", "    ", None, "", ""),
        ("Nominal sangat besar (1 Miliar)", "catat 1000000000 gaji bulanan", 1_000_000_000, "Gaji bulanan", "salary"),
        ("Nominal sangat besar desimal (1.5jt juta - wait, 1.5jt saja)", "catat 1.5jt bonus", 1_500_000, "Bonus", "bonus"),
        ("Hanya angka (tanpa deskripsi)", "50rb", 50_000, "", "other_expense"),
        ("Hanya nominal saja dengan RP", "rp25000", 25_000, "", "other_expense"),
        ("Pesan tanpa angka", "catat makan siang", None, "", ""),
        ("Pesan acak tanpa angka", "halo apa kabar", None, "", ""),
        ("Dua nominal dalam satu baris", "catat 50rb makan siang dan 20rb minum", 50_000, "Makan siang dan 20rb minum", "food"),
        ("Karakter spesial dalam deskripsi", "50rb makan + es teh manis (level 3) & kerupuk!!!", 50_000, "Makan + es teh manis (level 3) & kerupuk!!!", "food"),
        ("Nominal dengan pemisah titik berantakan", "catat 5.0.0.0.0 makan", 50_000, "Makan", "food"),
    ]
    
    parser_pass = 0
    for label, text, exp_amount, exp_desc, exp_cat in parser_cases:
        res = parse_catatan(text)
        print(f"[{label}]")
        print(f"  Input: '{text}'")
        if res is None:
            if exp_amount is None:
                print("  Result: None (Lulus — Sesuai ekspektasi)")
                parser_pass += 1
            else:
                print(f"  Result: None (Gagal — Ekspektasi amount {exp_amount})")
        else:
            amount_ok = res["amount"] == exp_amount
            desc_ok = res["description"] == exp_desc
            cat_ok = res["category"] == exp_cat
            
            if amount_ok and desc_ok and cat_ok:
                print(f"  Result: Lulus -> Type: {res['type']}, Amount: {res['amount']}, Category: {res['category']}, Desc: '{res['description']}'")
                parser_pass += 1
            else:
                print(f"  Result: GAGAL!")
                print(f"    Got  -> Amount: {res['amount']}, Category: {res['category']}, Desc: '{res['description']}'")
                print(f"    Exp  -> Amount: {exp_amount}, Category: {exp_cat}, Desc: '{exp_desc}'")
        print("-" * 50)
        
    print(f"\nParser Edge Cases: {parser_pass}/{len(parser_cases)} Lulus")
    
    # ─── PART 2: customCategories Edge Cases ──────────────────────
    print("\n--- [PART 2] Testing customCategories Edge Cases ---")
    
    # Case A: customCategories bernilai None atau kosong
    print("[Case A: customCategories is None]")
    res_none = parse_catatan("50rb makan siang", custom_categories=None)
    if res_none and res_none["category"] == "food":
        print("  Result: Lulus (Kembali ke kategori default 'food')")
    else:
        print(f"  Result: Gagal (Got: {res_none})")
        
    # Case B: customCategories kosong []
    print("[Case B: customCategories is empty list]")
    res_empty = parse_catatan("50rb makan siang", custom_categories=[])
    if res_empty and res_empty["category"] == "food":
        print("  Result: Lulus (Kembali ke kategori default 'food')")
    else:
        print(f"  Result: Gagal (Got: {res_empty})")
        
    # Case C: Cocok dengan custom category tapi tipe transaksi beda
    print("[Case C: Match custom category label but transaction type is different]")
    # User punya kategori kustom "Nasi Padang" dengan type "income", tetapi dia mengetik "50rb Nasi Padang" (dianggap expense)
    # Seharusnya masuk ke default category "food" karena kata kunci "Nasi" terdeteksi, bukan "custom_nasi_padang" (karena beda type).
    custom_cats = [{"id": "custom_nasi_padang_income", "label": "Nasi Padang", "type": "income"}]
    res_diff_type = parse_catatan("50rb Nasi Padang", custom_categories=custom_cats)
    if res_diff_type and res_diff_type["category"] == "food":
        print("  Result: Lulus (Aman, mengabaikan custom category income saat transaksi expense)")
    else:
        print(f"  Result: Gagal (Got: {res_diff_type})")
        
    print("-" * 50)

    # ─── PART 3: main.py Message Handler Edge Cases ───────────────
    print("\n--- [PART 3] Testing main.py Message Handler Edge Cases ---")
    
    # Mock user verified, tetapi budget status mengembalikan None atau kosong
    user_verified = {
        "uid": "uid_test",
        "waPhone": "6289999999999",
        "waVerified": True,
        "customCategories": []
    }
    
    async def test_main_handler():
        main.get_user_by_phone = mock.MagicMock(return_value=user_verified)
        main.catat_transaksi = mock.MagicMock(return_value={"txId": "tx_test"})
        main.save_pending_transaction = mock.MagicMock(return_value=True)
        main.hitung_total_hari_ini = mock.MagicMock(return_value={
            "pengeluaran": 75000, "pemasukan": 0, "catatan": [{}]
        })
        main.hitung_total_bulan_ini = mock.MagicMock(return_value={
            "pengeluaran": 1_200_000, "pemasukan": 2_500_000, "catatan": [{}] * 18
        })
        
        # Test Case 1: Laporan anggaran saat budget kosong
        print("[Budget Empty Command]")
        main.get_budget_status = mock.MagicMock(return_value={})
        reply = await main.handle_text_message("6289999999999", "anggaran")
        print(f"  Bot Reply:\n{reply}")
        if "Belum ada anggaran yang diset" in reply:
            print("  Result: Lulus")
        else:
            print("  Result: Gagal")
        print("-" * 50)
        
        # Test Case 2: Catat transaksi saat budget kosong (tidak boleh print warning budget)
        print("[Transaction recording with empty budget]")
        reply_tx = await main.handle_text_message("6289999999999", "catat 50rb makan siang")
        print(f"  Bot Reply:\n{reply_tx}")
        if "⚠️ Anggaran" not in reply_tx:
            print("  Result: Lulus (Tidak ada warning anggaran kosong)")
        else:
            print("  Result: Gagal")
        print("-" * 50)

        # Test Case 3: Mengirim "ya" tanpa ada transaksi pending
        print("[Send 'ya' without pending transaction]")
        reply_ya_none = await main.handle_text_message("6289999999999", "ya")
        print(f"  Bot Reply:\n{reply_ya_none}")
        if "gue ga ngerti pesannya" in reply_ya_none:
            print("  Result: Lulus (Aman, diabaikan karena tidak ada transaksi pending)")
        else:
            print("  Result: Gagal")
        print("-" * 50)

    import asyncio
    asyncio.run(test_main_handler())
    print("=" * 62)

if __name__ == "__main__":
    run_edge_cases()
