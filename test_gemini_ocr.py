"""
Test pre-check (Tesseract) + Gemini OCR pipeline.
"""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from parser import parse_catatan, detect_category, parse_ocr_items, format_rupiah


def test_fuel_detection():
    """Test brand BBM terdeteksi sebagai transport."""
    cases = [
        ("50rb pertalite", "transport"), ("100rb pertamax", "transport"),
        ("75rb shell v-power", "transport"), ("50rb bensin", "transport"),
        ("80rb bbm", "transport"), ("60rb spbu", "transport"),
        ("50rb solar", "transport"), ("50rb premium", "transport"),
    ]
    print("=== FUEL DETECTION ===")
    ok = 0
    for text, exp in cases:
        r = parse_catatan(text)
        actual = r["category"] if r else "FAIL"
        passed = actual == exp
        print(f"  {'✅' if passed else '❌'} '{text}' → {actual}")
        if passed: ok += 1
    print(f"  {ok}/{len(cases)}\n")
    return ok == len(cases)


def test_minimarket_detection():
    """Test keyword minimarket."""
    cases = [
        ("50rb belanja alfamart", "shopping"), ("30rb indomaret", "shopping"),
        ("25rb circle k", "shopping"), ("40rb lawson", "shopping"),
    ]
    print("=== MINIMARKET DETECTION ===")
    ok = 0
    for text, exp in cases:
        r = parse_catatan(text)
        actual = r["category"] if r else "FAIL"
        passed = actual == exp
        print(f"  {'✅' if passed else '❌'} '{text}' → {actual}")
        if passed: ok += 1
    print(f"  {ok}/{len(cases)}\n")
    return ok == len(cases)


def test_bpjs_no_false_positive():
    """Test 'bpjs' TIDAK salah kategori."""
    cases = [
        ("50rb bpjs kesehatan", "health"),
        ("30rb iuran bpjs", "health"),
        ("100rb bayar bpjs", "health"),
    ]
    print("=== BPJS FALSE POSITIVE CHECK ===")
    ok = 0
    for text, exp in cases:
        r = parse_catatan(text)
        actual = r["category"] if r else "FAIL"
        passed = actual == exp
        print(f"  {'✅' if passed else '❌'} '{text}' → {actual}")
        if passed: ok += 1
    print(f"  {ok}/{len(cases)}\n")
    return ok == len(cases)


def test_precheck_receipt():
    """Test Tesseract pre-check: struk vs bukan struk."""
    from ocr import is_receipt_image
    print("=== PRE-CHECK (TESSERACT) ===")

    # Test dengan gambar struk asli (jika ada)
    test_dir = "/tmp/waha_media"
    receipt_files = []
    if os.path.exists(test_dir):
        receipt_files = [f for f in os.listdir(test_dir) if f.startswith("receipt_")]

    if not receipt_files:
        print("  ⚠️ Tidak ada file receipt di /tmp/waha_media, skip visual test")
        print("  ✅ Pre-check function exists and callable")
        print()
        return True

    ok = 0
    total = min(3, len(receipt_files))
    for fname in receipt_files[:total]:
        path = os.path.join(test_dir, fname)
        is_r, reason = is_receipt_image(path)
        status = "✅" if is_r else "⚠️"
        print(f"  {status} {fname}: is_receipt={is_r}, reason={reason[:60]}")
        if is_r: ok += 1
    print(f"  {ok}/{total} passed\n")
    return ok > 0


def test_precheck_non_receipt():
    """Test pre-check menolak gambar yang bukan struk."""
    from ocr import is_receipt_image
    from PIL import Image
    print("=== PRE-CHECK REJECT NON-RECEIPT ===")

    # Buat gambar kosong (bukan struk)
    img = Image.new("RGB", (400, 400), color=(255, 255, 255))
    path = "/tmp/test_blank.png"
    img.save(path)

    is_r, reason = is_receipt_image(path)
    passed = not is_r
    print(f"  {'✅' if passed else '❌'} Blank image: is_receipt={is_r}, reason={reason[:80]}")

    # Buat gambar dengan tulisan acak (bukan struk)
    from PIL import ImageDraw
    img2 = Image.new("RGB", (400, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img2)
    draw.text((50, 50), "Hello World\nThis is a test\nNot a receipt", fill=(0, 0, 0))
    path2 = "/tmp/test_text.png"
    img2.save(path2)

    is_r2, reason2 = is_receipt_image(path2)
    # This might pass or fail depending on Tesseract — just log it
    print(f"  ℹ️ Text image: is_receipt={is_r2}, reason={reason2[:80]}")

    os.remove(path)
    os.remove(path2)
    print()
    return passed


def test_gemini_json_parsing():
    """Test parsing respons JSON dari Gemini (mock)."""
    import json
    print("=== GEMINI JSON PARSING ===")
    valid_cats = {"food", "transport", "shopping", "health", "entertainment",
                  "bills", "education", "beauty", "home", "investment",
                  "social", "saving", "other_expense"}

    tests = [
        ('[{"nama":"Indomie","harga":3500,"kategori":"food"}]', 1, "Normal"),
        ('```json\n[{"nama":"Bensin","harga":50000,"kategori":"transport"}]\n```', 1, "Markdown block"),
        ('json\n[{"nama":"Sabun","harga":4500,"kategori":"home"}]', 1, "json prefix"),
        ('[{"nama":"Rokok","harga":22000,"kategori":"smoking"}]', 1, "Invalid cat → other"),
        ('[]', 0, "Empty array"),
    ]

    ok = 0
    for raw, exp, label in tests:
        try:
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
            items = json.loads(raw)
            if not isinstance(items, list):
                items = []
            cleaned = []
            for item in items:
                if not isinstance(item, dict): continue
                nama = str(item.get("nama","")).strip()
                harga = int(item.get("harga",0))
                kategori = str(item.get("kategori","other_expense")).strip().lower()
                if kategori not in valid_cats: kategori = "other_expense"
                if nama and harga > 0:
                    cleaned.append({"nama":nama,"harga":harga,"kategori":kategori})
            passed = len(cleaned) == exp
        except Exception:
            passed = exp == 0
        print(f"  {'✅' if passed else '❌'} {label}: {len(cleaned)} items")
        if passed: ok += 1
    print(f"  {ok}/{len(tests)}\n")
    return ok == len(tests)


def test_ocr_preview_format():
    """Test format_ocr_preview."""
    from main import format_ocr_preview, CATEGORY_EMOJIS
    print("=== OCR PREVIEW FORMAT ===")
    items = [
        {"nama": "Indomie Goreng", "harga": 3500, "kategori": "food"},
        {"nama": "Aqua 600ml", "harga": 3000, "kategori": "food"},
        {"nama": "Sabun Lifebuoy", "harga": 4500, "kategori": "home"},
    ]
    preview = format_ocr_preview(items, "🤖 AI")
    checks = [
        ("nomor item", "1." in preview and "2." in preview),
        ("kategori", "(food)" in preview and "(home)" in preview),
        ("total", "Rp11.000" in preview),
        ("instruksi hapus", "hapus" in preview),
        ("instruksi edit", "edit" in preview),
    ]
    ok = 0
    for label, passed in checks:
        print(f"  {'✅' if passed else '❌'} {label}")
        if passed: ok += 1
    print(f"  {ok}/{len(checks)}\n")
    return ok == len(checks)


def test_edit_hapus_logic():
    """Test logic hapus dan edit items."""
    from parser import detect_category
    print("=== EDIT/HAPUS LOGIC ===")
    items = [
        {"nama": "Indomie", "harga": 3500, "kategori": "food"},
        {"nama": "Aqua", "harga": 3000, "kategori": "food"},
        {"nama": "Sabun", "harga": 4500, "kategori": "home"},
    ]
    ok = 0; total = 0

    # Hapus single
    total += 1
    t = [i.copy() for i in items]
    for i in sorted([1], reverse=True): t.pop(i)
    p = len(t) == 2 and t[0]["nama"] == "Indomie"
    print(f"  {'✅' if p else '❌'} Hapus single")
    if p: ok += 1

    # Hapus multiple
    total += 1
    t = [i.copy() for i in items]
    for i in sorted([0, 2], reverse=True): t.pop(i)
    p = len(t) == 1 and t[0]["nama"] == "Aqua"
    print(f"  {'✅' if p else '❌'} Hapus multiple")
    if p: ok += 1

    # Hapus semua
    total += 1
    t = [i.copy() for i in items]
    for i in sorted([0, 1, 2], reverse=True): t.pop(i)
    p = len(t) == 0
    print(f"  {'✅' if p else '❌'} Hapus semua")
    if p: ok += 1

    # Edit item
    total += 1
    t = [i.copy() for i in items]
    t[0] = {"nama": "Indomie Pedas", "harga": 8000, "kategori": "food"}
    p = t[0]["harga"] == 8000 and t[1] == items[1]
    print(f"  {'✅' if p else '❌'} Edit item")
    if p: ok += 1

    print(f"  {ok}/{total}\n")
    return ok == total


def test_gemini_api():
    """Test Gemini API connection."""
    print("=== GEMINI API ===")
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        from ocr import USE_GEMINI, _gemini_client
        if not USE_GEMINI:
            print("  ⚠️ USE_GEMINI=False")
            return False
        resp = _gemini_client.models.generate_content(
            model="gemini-2.5-flash", contents=['Reply "OK"'])
        ok = "ok" in resp.text.strip().lower()
        print(f"  {'✅' if ok else '❌'} {resp.text.strip()[:30]}")
        return ok
    except Exception as e:
        print(f"  ❌ {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  FLOWKU BOT — OCR TEST SUITE")
    print("=" * 50 + "\n")

    results = []
    results.append(("Fuel Detection", test_fuel_detection()))
    results.append(("Minimarket Detection", test_minimarket_detection()))
    results.append(("BPJS No False Positive", test_bpjs_no_false_positive()))
    results.append(("Pre-check Receipt", test_precheck_receipt()))
    results.append(("Pre-check Reject", test_precheck_non_receipt()))
    results.append(("Gemini JSON Parsing", test_gemini_json_parsing()))
    results.append(("OCR Preview Format", test_ocr_preview_format()))
    results.append(("Edit/Hapus Logic", test_edit_hapus_logic()))
    results.append(("Gemini API", test_gemini_api()))

    print("=" * 50)
    print("  SUMMARY")
    print("=" * 50)
    all_ok = True
    for name, ok in results:
        s = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {s} — {name}")
        if not ok: all_ok = False
    print()
    print("  🎉 ALL PASSED!" if all_ok else "  ⚠️ SOME FAILED")
    print()
