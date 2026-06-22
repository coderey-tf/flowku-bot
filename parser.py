"""
Text Parser — Parse pesan WhatsApp jadi transaksi Flowku
Kategori sesuai schema Firestore: food, transport, shopping, entertainment,
bills, health, education, other

Format yang didukung:
  - "catat 50000 makan" / "catat 50rb makan"
  - "pengeluaran 50000 makan siang"
  - "pemasukan 500000 gaji"
  - "50rb makan" / "50000 transport grab"
"""
import re

# Mapping kata kunci ke kategori pengeluaran (sesuai schema Flowku)
CATEGORY_KEYWORDS = {
    "food": ["makan", "minum", "kopi", "teh", "jus", "nasi", "ayam", "mie", "sate", "bakso",
             "snack", "cemilan", "sarapan", "makan siang", "makan malam", "gofood", "grabfood",
             "resto", "kafe", "warung", "food", "drink", "coffee"],
    "transport": ["transport", "grab", "gojek", "ojek", "bensin", "parkir", "tol", "bus",
                  "kereta", "mrt", "taksi", "bbm", "motor", "mobil", "angkot", "transjakarta"],
    "shopping": ["belanja", "shopping", "supermarket", "indomaret", "alfamart", "toko",
                 "market", "shopee", "tokopedia", "lazada", "bukalapak", "mall"],
    "health": ["kesehatan", "obat", "dokter", "rumah sakit", "apotek", "vitamin",
               "klinik", "medical", "checkup", "sakit", "therapi", "rawat"],
    "entertainment": ["hiburan", "nonton", "film", "game", "musik", "spotify", "netflix",
                      "youtube", "karaoke", "bioskop", "liburan", "jalan-jalan", "wisata", "rekreasi"],
    "bills": ["tagihan", "listrik", "air", "internet", "wifi", "pulsa", "bpjs", "cicilan",
              "sewa", "kos", "kontrakan", "pdam", "telepon", "asuransi", "token", "paket data"],
    "education": ["pendidikan", "buku", "kursus", "sekolah", "kuliah", "training",
                  "seminar", "workshop", "spp", "les", "akademik"],
    "beauty": ["kecantikan", "salon", "skincare", "kosmetik", "makeup", "facial", "creambath",
               "potong rambut", "pangkas", "beauty", "spa"],
    "home": ["rumah tangga", "dapur", "kasur", "lemari", "meja", "kursi", "alat dapur", "sabun",
             "shampoo", "detergen", "sapu", "pel", "renovasi"],
    "investment": ["investasi", "saham", "reksadana", "crypto", "kripto", "obligasi", "emas",
                   "reksa dana", "bibit", "bareksa", "invest"],
    "social": ["sosial", "hadiah", "kado", "donasi", "sedekah", "zakat", "kondangan", "sumbangan",
               "tumpengan", "gift", "donation"],
    "saving": ["tabungan", "saving", "celengan", "simpanan", "tabung", "goal"],
    "other_expense": ["lainnya", "other", "misc", "lain-lain"],
}

# Mapping kata kunci ke kategori pemasukan (sesuai schema Flowku)
INCOME_CATEGORY_KEYWORDS = {
    "salary": ["gaji", "salary", "gajian", "payroll", "upah"],
    "freelance": ["freelance", "proyek", "project", "sambilan", "desain", "coding", "nulis", "side hustle"],
    "business": ["bisnis", "usaha", "jualan", "dagang", "toko", "omset", "omzet", "warung", "untung", "profit", "sales", "penjualan"],
    "investment_in": ["dividen", "bunga", "kupon", "profit investasi", "capital gain", "hasil saham", "imbal hasil"],
    "bonus": ["bonus", "thr", "insentif", "hadiah", "giveaway", "tips", "reward"],
    "transfer": ["transfer masuk", "kiriman", "ditransfer", "dikirimi", "uang masuk", "transfer"],
    "other_income": ["lainnya", "other", "misc", "lain-lain", "pemasukan", "masuk", "income", "pendapatan"],
}

INCOME_KEYWORDS = ["gaji", "pemasukan", "masuk", "income", "hadiah", "transfer masuk",
                   "cair", "untung", "bonus", "gajian", "pendapatan", "jualan", "profit"]


def parse_amount(text: str) -> int:
    """Parse jumlah uang dari text. Mendukung: 50000, 50rb, 50k, 50.000, rp50000, rp 50.000."""
    text = text.lower().strip()
    text = re.sub(r"rp\.?\s*", "", text)

    # Handle "rb" / "k" suffix
    match = re.match(r"([\d.,]+)\s*(rb|k|ribu)(?:\s|$)", text)
    if match:
        num = match.group(1).replace(",", "").replace(".", "")
        return int(num) * 1000

    # Handle "jt" / "juta" suffix
    match = re.match(r"([\d.,]+)\s*(jt|juta)(?:\s|$)", text)
    if match:
        num = match.group(1).replace(",", "").replace(".", "")
        return int(num) * 1000000

    # Plain number (with dots/commas as thousand separators)
    cleaned = text.replace(".", "").replace(",", "")
    match = re.match(r"(\d+)", cleaned)
    if match:
        return int(match.group(1))

    return 0


def detect_category(text: str, tx_type: str = "expense", custom_categories: list = None) -> str:
    """Deteksi kategori dari text dengan prioritas kategori kustom lalu default."""
    text_lower = text.lower()

    # 1. Cek custom categories dari Firestore
    if custom_categories:
        for c in custom_categories:
            if c.get("type") == tx_type:
                label = c.get("label", "")
                if label and label.lower() in text_lower:
                    return c.get("id")

    # 2. Cek kategori statis bawaan
    if tx_type == "income":
        for category, keywords in INCOME_CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return category
        return "other_income"
    else:
        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return category
        return "other_expense"


def parse_catatan(message: str, custom_categories: list = None) -> dict | None:
    """
    Parse pesan jadi dict transaksi.
    Returns: {type, amount, category, description} atau None kalau gagal.
    type: "expense" atau "income"
    """
    msg = message.strip().lower()

    # Detect type
    tx_type = "expense"
    if any(w in msg for w in INCOME_KEYWORDS):
        tx_type = "income"

    # Remove command keywords
    msg_clean = msg
    for word in ["catat", "catatan", "pengeluaran", "pemasukan", "masuk", "keluar",
                 "income", "expense", "uang"]:
        msg_clean = msg_clean.replace(word, "")
    msg_clean = msg_clean.strip()

    # Extract amount
    amount = 0
    description = ""

    patterns = [
        r"(rp\.?\s*[\d.,]+\s*(?:rb|k|ribu|jt|juta|m)?)\s*(.*)",
        r"([\d.,]+\s*(?:rb|k|ribu|jt|juta|m))\s*(.*)",
        r"([\d.,]+)\s*(.*)",
    ]

    for pattern in patterns:
        match = re.match(pattern, msg_clean, re.IGNORECASE)
        if match:
            amount_str = match.group(1).strip()
            amount = parse_amount(amount_str)
            description = match.group(2).strip() if match.group(2) else ""
            break

    if amount <= 0:
        return None

    # Detect category
    category = detect_category(description if description else msg, tx_type=tx_type, custom_categories=custom_categories)

    return {
        "type": tx_type,
        "amount": amount,
        "category": category,
        "description": description.capitalize() if description else "",
    }


def parse_ocr_items(text: str, custom_categories: list = None) -> list:
    """
    Parse teks OCR struk jadi list item pengeluaran.
    """
    items = []
    lines = text.strip().split("\n")

    skip_words = ["total", "subtotal", "pajak", "tax", "cash", "kembali",
                  "change", "kartu", "debit", "qris", "bayar", "payment"]

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if any(w in line.lower() for w in skip_words):
            continue

        numbers = re.findall(r"[\d.,]+", line)
        if numbers:
            price_str = numbers[-1].replace(".", "").replace(",", "")
            try:
                price = int(price_str)
                if 0 < price < 100000000:
                    name_part = line
                    for num in numbers:
                        name_part = name_part.replace(num, "")
                    name_part = name_part.strip(" -·*")
                    if name_part:
                        items.append({
                            "nama": name_part,
                            "harga": price,
                            "kategori": detect_category(name_part, tx_type="expense", custom_categories=custom_categories),
                        })
            except ValueError:
                continue

    return items


def format_rupiah(amount: int) -> str:
    """Format angka jadi Rupiah."""
    if amount >= 1000000:
        return f"Rp{amount/1000000:,.1f}jt".replace(",", ".")
    elif amount >= 1000:
        return f"Rp{amount:,.0f}".replace(",", ".")
    else:
        return f"Rp{amount}"
