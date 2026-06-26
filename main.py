"""
Flowku WhatsApp Chatbot — Main FastAPI App
Menerima webhook dari WAHA, proses pesan, simpan ke Firestore.
Schema sesuai BACKEND_MIGRATION_GUIDE.md
"""
import logging
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Header
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import pytz

CATEGORY_EMOJIS = {
    "food": "🍔", "transport": "🚗", "shopping": "🛍️", "health": "💊",
    "entertainment": "🎮", "bills": "⚡", "education": "📚", "beauty": "💄",
    "home": "🏠", "investment": "📈", "social": "🎁", "saving": "🎯",
    "other_expense": "📦", "salary": "💰", "freelance": "💻", "business": "🏪",
    "investment_in": "📈", "bonus": "🎉", "transfer": "💸", "other_income": "✨"
}

from config import APP_PORT, WEBHOOK_SECRET, OWNER_PHONE, REMINDER_HOUR_1, REMINDER_HOUR_2
from parser import parse_catatan, parse_ocr_items, format_rupiah
from firestore_db import (
    catat_transaksi, hitung_total_hari_ini, hitung_total_bulan_ini,
    save_ocr_result, get_budget_status, get_user_by_phone, verify_whatsapp,
    save_pending_transaction,
)
from waha import send_text
from ocr import extract_text_from_image, extract_items_from_image
from reminder import cek_dan_kirim_reminder, cek_langganan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WIB = pytz.timezone("Asia/Jakarta")

# Scheduler for reminders
scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup & shutdown events."""
    scheduler.add_job(
        cek_dan_kirim_reminder, "cron",
        hour=REMINDER_HOUR_1, minute=0,
        id="reminder_siang", replace_existing=True,
    )
    scheduler.add_job(
        cek_dan_kirim_reminder, "cron",
        hour=REMINDER_HOUR_2, minute=0,
        id="reminder_malam", replace_existing=True,
    )
    scheduler.add_job(
        cek_langganan, "cron",
        hour=8, minute=0,
        id="cek_langganan", replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started — reminders at {REMINDER_HOUR_1}:00 & {REMINDER_HOUR_2}:00 WIB")

    yield

    scheduler.shutdown()


app = FastAPI(title="Flowku Chatbot", lifespan=lifespan)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def format_ocr_preview(items: list, ocr_label: str = "🤖 AI") -> str:
    """Format preview OCR items sebelum konfirmasi."""
    total = sum(item["harga"] for item in items)
    msg = f"{ocr_label} Struk terbaca! {len(items)} item ditemukan:\n\n"
    for i, item in enumerate(items, 1):
        emoji = CATEGORY_EMOJIS.get(item["kategori"], "•")
        msg += f"  {i}. {emoji} {item['nama']}: {format_rupiah(item['harga'])} ({item['kategori']})\n"
    msg += f"\n💸 Total: {format_rupiah(total)}\n"
    msg += f"\n💾 Simpan semua item ke catatan?"
    msg += f"\n• Balas *Ya* / *Ok* untuk simpan"
    msg += f"\n• Balas *Batal* untuk batal"
    msg += f"\n• *hapus 1,3* — hapus item no 1 & 3"
    msg += f"\n• *edit 1 5000 makan* — ubah item no 1"
    return msg


def format_catatan_msg(saved: dict, catatan: dict, phone: str, uid: str = None) -> str:
    """Format pesan konfirmasi setelah catat."""
    emoji = "💸" if catatan["type"] == "expense" else "💰"
    tipe_label = "Pengeluaran" if catatan["type"] == "expense" else "Pemasukan"

    msg = (
        f"✅ {tipe_label} tercatat!\n\n"
        f"{emoji} *{format_rupiah(catatan['amount'])}*\n"
        f"📂 Kategori: {catatan['category'].replace('_', ' ').capitalize()}\n"
    )
    if catatan.get("description"):
        msg += f"📝 {catatan['description']}\n"

    # Ringkasan hari ini
    total = hitung_total_hari_ini(phone, uid=uid)
    msg += (
        f"\n📊 Hari ini:\n"
        f"  💸 Keluar: {format_rupiah(total['pengeluaran'])}\n"
    )
    if total['pemasukan'] > 0:
        msg += f"  💰 Masuk: {format_rupiah(total['pemasukan'])}\n"
    msg += f"  📝 {len(total['catatan'])} transaksi"

    # Budget warning (kalau ada)
    budget = get_budget_status(phone)
    if budget and catatan["category"] in budget:
        b = budget[catatan["category"]]
        if b["percentage"] >= 80:
            msg += f"\n\n⚠️ Anggaran {catatan['category'].capitalize()}: {b['percentage']}% terpakai!"

    return msg


def format_laporan(catatan: list, total_pengeluaran: int, total_pemasukan: int, label: str) -> str:
    """Format laporan ringkasan."""
    msg = f"📊 Laporan {label}\n\n"

    if not catatan:
        msg += "Belum ada transaksi."
        return msg

    # Group by category
    by_cat = {}
    for t in catatan:
        if t.get("type") == "expense":
            cat = t.get("category", "other_expense")
            by_cat[cat] = by_cat.get(cat, 0) + t.get("amount", 0)

    if by_cat:
        msg += "Pengeluaran per kategori:\n"
        for cat, jumlah in sorted(by_cat.items(), key=lambda x: -x[1]):
            emoji = CATEGORY_EMOJIS.get(cat, "•")
            msg += f"  {emoji} {cat.replace('_', ' ').capitalize()}: {format_rupiah(jumlah)}\n"

    msg += f"\n💸 Total Keluar: {format_rupiah(total_pengeluaran)}"
    if total_pemasukan > 0:
        msg += f"\n💰 Total Masuk: {format_rupiah(total_pemasukan)}"
        msg += f"\n📉 Selisih: {format_rupiah(total_pemasukan - total_pengeluaran)}"

    msg += f"\n📝 {len(catatan)} transaksi"
    return msg


# ─────────────────────────────────────────────
# COMMANDS
# ─────────────────────────────────────────────

async def cmd_help() -> str:
    return (
        "💰 *Flowku Bot* — Asisten Keuangan Pribadimu\n\n"

        "━━━━━━━━━━━━━━━━━━━\n"
        "📝 *CATAT PENGELUARAN*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Cukup ketik nominalnya, langsung tercatat!\n"
        "  • `50rb makan siang`\n"
        "  • `catat 25000 kopi`\n"
        "  • `tagihan wifi 300rb`\n"
        "  • `80rb skincare vitamin c`\n\n"

        "━━━━━━━━━━━━━━━━━━━\n"
        "💰 *CATAT PEMASUKAN*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "  • `pemasukan 3jt gaji bulanan`\n"
        "  • `masuk 500rb bonus`\n"
        "  • `1jt freelance desain logo`\n\n"

        "━━━━━━━━━━━━━━━━━━━\n"
        "📊 *LAPORAN & CEK*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "  • *hari ini* — ringkasan transaksi hari ini\n"
        "  • *bulan ini* — ringkasan & saldo bulanan\n"
        "  • *anggaran* — cek sisa budget per kategori\n"
        "  • *kategori* — lihat semua kategori\n\n"

        "━━━━━━━━━━━━━━━━━━━\n"
        "📸 *SCAN STRUK*\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Kirim *foto struk* langsung ke chat ini,\n"
        "Flowku akan baca & catat otomatis!\n\n"

        "💡 *Tips:*\n"
        "Nominal bisa pakai: `rb`, `k`, `ribu`, `jt`, `juta`\n"
        "Contoh: `50rb` = `50k` = `50000`\n"
        "Ketik *bantuan* kapan saja untuk tampilkan menu ini."
    )


async def cmd_kategori() -> str:
    msg = "📂 *Kategori Default Flowku*\n\n"
    msg += "*💸 PENGELUARAN:*\n"
    expense_cats = [
        ("food", "🍔", "Makan & Minum"),
        ("transport", "🚗", "Transportasi"),
        ("shopping", "🛍️", "Belanja"),
        ("health", "💊", "Kesehatan"),
        ("entertainment", "🎮", "Hiburan"),
        ("bills", "⚡", "Tagihan & Utilitas"),
        ("education", "📚", "Pendidikan"),
        ("beauty", "💄", "Kecantikan"),
        ("home", "🏠", "Rumah Tangga"),
        ("investment", "📈", "Investasi"),
        ("social", "🎁", "Sosial & Hadiah"),
        ("saving", "🎯", "Tabungan Goal"),
        ("other_expense", "📦", "Lainnya"),
    ]
    for cat, emoji, label in expense_cats:
        msg += f"  {emoji} {label} (`{cat}`)\n"
        
    msg += "\n*💰 PEMASUKAN:*\n"
    income_cats = [
        ("salary", "💰", "Gaji"),
        ("freelance", "💻", "Freelance"),
        ("business", "🏪", "Bisnis"),
        ("investment_in", "📈", "Hasil Investasi"),
        ("bonus", "🎉", "Bonus"),
        ("transfer", "💸", "Transfer Masuk"),
        ("other_income", "✨", "Lainnya"),
    ]
    for cat, emoji, label in income_cats:
        msg += f"  {emoji} {label} (`{cat}`)\n"
        
    msg += "\nContoh: *catat 50000 makan*"
    return msg


async def cmd_hari_ini(phone: str) -> str:
    total = hitung_total_hari_ini(phone)
    return format_laporan(total["catatan"], total["pengeluaran"], total["pemasukan"], "Hari Ini")


async def cmd_bulan_ini(phone: str) -> str:
    total = hitung_total_bulan_ini(phone)
    return format_laporan(total["catatan"], total["pengeluaran"], total["pemasukan"], "Bulan Ini")


async def cmd_anggaran(phone: str) -> str:
    budget = get_budget_status(phone)
    if not budget:
        return "Belum ada anggaran yang diset. Set di aplikasi Flowku dulu ya."

    msg = "📊 Status Anggaran Bulan Ini\n\n"

    for cat, info in budget.items():
        emoji = CATEGORY_EMOJIS.get(cat, "•")
        pct = info["percentage"]
        status = "✅" if pct < 80 else "⚠️" if pct < 100 else "🚨"
        msg += (
            f"{status} {emoji} {cat.replace('_', ' ').capitalize()}\n"
            f"   {format_rupiah(info['spent'])} / {format_rupiah(info['limit'])} ({pct}%)\n\n"
        )

    return msg


# ─────────────────────────────────────────────
# SUSPICIOUS TRANSACTION DETECTOR
# ─────────────────────────────────────────────

import re as _re

# Suffix-like karakter yang sering jadi typo (bukan rb/k/ribu/jt/juta)
# Hanya tangkap suffix yang LANGSUNG menempel atau 1 spasi setelah angka,
# dan suffix tersebut berdiri sendiri (tidak diikuti huruf lain = bukan bagian kata)
_TYPO_SUFFIX_PATTERN = _re.compile(
    r"(?<!\w)(\d+)\s{0,1}([a-z]{1,3})(?!\w)",
    _re.IGNORECASE,
)
_VALID_SUFFIXES = {"rb", "k", "ribu", "jt", "juta", "rp"}


def is_suspicious_transaction(raw_text: str, catatan: dict) -> tuple[bool, str]:
    """
    Deteksi apakah transaksi terlihat mencurigakan / typo.
    Returns: (is_suspicious: bool, reason: str)
    """
    amount = catatan.get("amount", 0)
    raw_lower = raw_text.strip().lower()

    # 1. Nominal terlalu kecil (< Rp500) — kemungkinan lupa suffix
    if 0 < amount < 500:
        return True, f"Nominal {format_rupiah(amount)} sangat kecil, mungkin ada typo? (contoh: '10rb' bukan '10 m')"

    # 2. Nominal sangat besar (> Rp 100.000.000)
    if amount > 100_000_000:
        return True, f"Nominal {format_rupiah(amount)} sangat besar, pastikan sudah benar"

    # 3. Ada suffix tidak dikenal langsung setelah angka (kemungkinan typo suffix)
    # mis. "10 m makan" → suffix 'm' tidak valid
    # mis. "50rb makan" → suffix 'rb' valid, skip
    # mis. "10 makan" → 'makan' adalah kata panjang, tidak tertangkap regex ini
    for match in _TYPO_SUFFIX_PATTERN.finditer(raw_lower):
        suffix = match.group(2).lower()
        if suffix not in _VALID_SUFFIXES:
            return True, f"Suffix '*{suffix}*' tidak dikenal setelah angka {match.group(1)}, mungkin typo? (gunakan: rb, k, jt, juta)"

    return False, ""


# ─────────────────────────────────────────────
# MESSAGE HANDLER
# ─────────────────────────────────────────────

async def handle_text_message(phone: str, text: str) -> str:
    """Proses pesan teks dan return balasan."""
    msg = text.strip().lower()

    # 1. Lookup user from Firestore
    user = get_user_by_phone(phone)
    if not user:
        return (
            "⚠️ *Nomor WhatsApp Belum Terdaftar*\n\n"
            "Nomor Anda belum terdaftar di sistem Flowku.\n"
            "Silakan daftar/masuk ke aplikasi Flowku dan simpan nomor WhatsApp Anda di halaman Profil."
        )

    # 2. Check if verification command is sent
    if msg == "mulai flowku":
        success = verify_whatsapp(phone)
        if success:
            return (
                "🎉 *WhatsApp Berhasil Diverifikasi!*\n\n"
                "Selamat! WhatsApp Bot Flowku Anda telah aktif. Sekarang Anda dapat mulai mencatat keuangan langsung dari chat ini.\n\n"
                "Coba ketik: *catat 50rb makan siang*"
            )
        else:
            return "❌ Gagal melakukan verifikasi. Silakan coba lagi nanti."

    # 3. Enforce verification check
    if not user.get("waVerified", False):
        return (
            "⚠️ *Verifikasi Diperlukan*\n\n"
            "Nomor WhatsApp Anda sudah disimpan di Profil, tetapi belum diaktifkan.\n\n"
            "Silakan kirim pesan *Mulai Flowku* (tanpa tanda kutip) ke chat ini untuk mengaktifkan bot."
        )

    # 3b. Check for pending confirmation flow
    pending = user.get("pendingTransaction")
    if pending:
        # ── OCR: HAPUS ITEMS ──
        if pending.get("type") == "ocr_items" and msg.startswith("hapus"):
            nums_str = msg.replace("hapus", "").strip()
            try:
                indices = [int(n.strip()) - 1 for n in nums_str.split(",") if n.strip().isdigit()]
                items = pending["items"]
                removed = [items[i] for i in indices if 0 <= i < len(items)]
                if not removed:
                    return "❌ Nomor item tidak valid. Contoh: *hapus 1,3*"
                # Remove items (reverse order to keep indices valid)
                for i in sorted(indices, reverse=True):
                    if 0 <= i < len(items):
                        items.pop(i)
                if not items:
                    save_pending_transaction(phone, None)
                    return "❌ Semua item dihapus. Tidak ada yang tersimpan.\nKirim foto struk baru atau catat manual."
                # Update pending & show preview
                pending["items"] = items
                save_pending_transaction(phone, pending)
                nama_removed = ", ".join(r["nama"] for r in removed)
                return f"🗑️ Dihapus: {nama_removed}\n\n" + format_ocr_preview(items)
            except (ValueError, IndexError):
                return "❌ Format salah. Contoh: *hapus 1,3*"

        # ── OCR: EDIT ITEM ──
        if pending.get("type") == "ocr_items" and msg.startswith("edit"):
            parts = msg.split(None, 3)  # ["edit", "1", "5000", "makan siang"]
            if len(parts) < 3:
                return "❌ Format: *edit [no] [harga] [nama]*\nContoh: *edit 1 5000 makan siang*"
            try:
                idx = int(parts[1]) - 1
                items = pending["items"]
                if idx < 0 or idx >= len(items):
                    return f"❌ Item no {idx+1} tidak ada. Pilih 1-{len(items)}"
                new_harga = int(parts[2].replace(".", "").replace(",", ""))
                new_nama = parts[3].strip() if len(parts) > 3 else items[idx]["nama"]
                # Detect category from new name
                from parser import detect_category
                custom_categories = user.get("customCategories", [])
                new_kategori = detect_category(new_nama, tx_type="expense", custom_categories=custom_categories)
                old = items[idx].copy()
                items[idx] = {"nama": new_nama, "harga": new_harga, "kategori": new_kategori}
                save_pending_transaction(phone, pending)
                return (
                    f"✏️ Item {idx+1} diubah:\n"
                    f"  ❌ {old['nama']}: {format_rupiah(old['harga'])} ({old['kategori']})\n"
                    f"  ✅ {new_nama}: {format_rupiah(new_harga)} ({new_kategori})\n\n"
                    + format_ocr_preview(items)
                )
            except (ValueError, IndexError):
                return "❌ Format: *edit [no] [harga] [nama]*\nContoh: *edit 1 5000 makan siang*"

        if msg in ("ya", "y", "ok", "oke", "yes", "simpan"):
            # ── OCR BATCH ITEMS ──
            if pending.get("type") == "ocr_items":
                items = pending["items"]
                raw_text = pending.get("raw_text", "")
                total = 0
                saved_items = []
                for item in items:
                    result = catat_transaksi(
                        user_phone=phone,
                        tipe="expense",
                        jumlah=item["harga"],
                        kategori=item["kategori"],
                        keterangan=item["nama"],
                        source="wa_bot_ocr",
                    )
                    if result:
                        total += item["harga"]
                        saved_items.append(item)
                save_ocr_result(phone, raw_text, saved_items)
                save_pending_transaction(phone, None)
                if saved_items:
                    uid = user.get("uid")
                    daily = hitung_total_hari_ini(phone, uid=uid)
                    msg_out = f"✅ {len(saved_items)} item tersimpan!\n\n"
                    for item in saved_items:
                        emoji = CATEGORY_EMOJIS.get(item["kategori"], "•")
                        msg_out += f"  {emoji} {item['nama']}: {format_rupiah(item['harga'])} ({item['kategori']})\n"
                    msg_out += f"\n💸 Total: {format_rupiah(total)}"
                    msg_out += f"\n\n📊 Total hari ini: {format_rupiah(daily['pengeluaran'])}"
                    return msg_out
                else:
                    return "❌ Gagal menyimpan item. Silakan hubungi admin."

            # ── SINGLE TRANSACTION (existing) ──
            saved = catat_transaksi(
                user_phone=phone,
                tipe=pending["type"],
                jumlah=pending["amount"],
                kategori=pending["category"],
                keterangan=pending.get("description", ""),
            )
            save_pending_transaction(phone, None)
            if saved:
                uid = user.get("uid")
                return format_catatan_msg(saved, pending, phone, uid=uid)
            else:
                return "❌ Gagal menyimpan transaksi. Silakan hubungi admin."
        elif msg in ("batal", "b", "tidak", "no", "cancel", "t"):
            save_pending_transaction(phone, None)
            return "❌ *Pencatatan dibatalkan*\n\nTransaksi Anda tidak disimpan."
        else:
            # ── OCR pending: JANGAN auto-cancel, minta user pilih ──
            if pending.get("type") == "ocr_items":
                return (
                    "⏳ Masih ada struk yang belum disimpan.\n\n"
                    "Pilih dulu:\n"
                    "• *Ya* — simpan semua item\n"
                    "• *Batal* — buang semua\n"
                    "• *hapus [no]* — hapus item\n"
                    "• *edit [no] [harga] [nama]* — ubah item"
                )
            # Single transaction: auto-cancel seperti biasa
            save_pending_transaction(phone, None)

    # 4. If verified, continue to standard commands & parsing
    custom_categories = user.get("customCategories", [])

    if msg in ["help", "bantuan", "menu", "/start", "/help"]:
        return await cmd_help()

    if msg in ["kategori", "categories", "category"]:
        return await cmd_kategori()

    if msg in ["hari ini", "today", "laporan hari ini"]:
        return await cmd_hari_ini(phone)

    if msg in ["bulan ini", "this month", "laporan bulan ini"]:
        return await cmd_bulan_ini(phone)

    if msg in ["anggaran", "budget", "budget status"]:
        return await cmd_anggaran(phone)

    # Try parse as catatan
    catatan = parse_catatan(text, custom_categories=custom_categories)
    if catatan:
        # Check if transaction is ambiguous ("rancu") or suspicious (typo/nyeleneh)
        is_rancu = catatan["category"] in ("other_expense", "other_income") or not catatan.get("description")
        suspicious, suspicious_reason = is_suspicious_transaction(text, catatan)

        if suspicious:
            save_pending_transaction(phone, catatan)
            emoji = "💸" if catatan["type"] == "expense" else "💰"
            desc_label = catatan.get("description") or "-"
            return (
                "⚠️ *Konfirmasi Transaksi*\n\n"
                f"Ada yang perlu dikonfirmasi: _{suspicious_reason}_\n\n"
                f"{emoji} *{format_rupiah(catatan['amount'])}*\n"
                f"📂 Kategori: {catatan['category'].replace('_', ' ').capitalize()}\n"
                f"📝 Keterangan: {desc_label}\n\n"
                "Apakah ini benar?\n"
                "• Balas *Ya* / *Ok* untuk menyimpan\n"
                "• Balas *Batal* / *Tidak* untuk membatalkan"
            )

        if is_rancu:
            save_pending_transaction(phone, catatan)
            emoji = "💸" if catatan["type"] == "expense" else "💰"
            desc_label = catatan.get("description") or "-"
            return (
                "🔍 *Transaksi Kurang Detail / Kategori Lainnya*\n\n"
                "Kami mendeteksi pencatatan Anda kurang detail:\n"
                f"{emoji} *{format_rupiah(catatan['amount'])}* (Kategori: {catatan['category'].replace('_', ' ').capitalize()})\n"
                f"📝 Keterangan: {desc_label}\n\n"
                "Apakah Anda ingin menyimpan transaksi ini?\n"
                "• Balas *Ya* / *Ok* untuk menyimpan\n"
                "• Balas *Batal* / *Tidak* untuk membatalkan"
            )

        saved = catat_transaksi(
            user_phone=phone,
            tipe=catatan["type"],
            jumlah=catatan["amount"],
            kategori=catatan["category"],
            keterangan=catatan.get("description", ""),
        )
        if saved:
            uid = user.get("uid")
            return format_catatan_msg(saved, catatan, phone, uid=uid)
        else:
            return "❌ Gagal menyimpan transaksi. Silakan hubungi admin."

    # Unknown command
    return (
        "Hmm, gue ga ngerti pesannya 🤔\n\n"
        "Coba ketik *bantuan* untuk liat perintah yang tersedia.\n\n"
        "Contoh: *catat 25000 makan*"
    )


async def handle_image_message(phone: str, media_url: str, base64_data: str = None) -> str:
    """Proses gambar (foto struk) via OCR."""
    # 1. Lookup user from Firestore
    user = get_user_by_phone(phone)
    if not user:
        return (
            "⚠️ *Nomor WhatsApp Belum Terdaftar*\n\n"
            "Nomor Anda belum terdaftar di sistem Flowku.\n"
            "Silakan daftar/masuk ke aplikasi Flowku dan simpan nomor WhatsApp Anda di halaman Profil."
        )

    # 2. Enforce verification check
    if not user.get("waVerified", False):
        return (
            "⚠️ *Verifikasi Diperlukan*\n\n"
            "Nomor WhatsApp Anda belum diaktifkan.\n\n"
            "Silakan kirim pesan *Mulai Flowku* (tanpa tanda kutip) ke chat ini untuk mengaktifkan bot."
        )

    custom_categories = user.get("customCategories", [])

    if not media_url and not base64_data:
        return "Gagal terima gambar. Coba kirim ulang."

    # ── CEK: ada struk pending belum disimpan? ──
    pending = user.get("pendingTransaction")
    if pending and pending.get("type") == "ocr_items":
        old_count = len(pending.get("items", []))
        old_total = sum(i["harga"] for i in pending.get("items", []))
        from parser import format_rupiah
        logger.info(f"Replacing pending OCR ({old_count} items, {format_rupiah(old_total)}) with new image")
        save_pending_transaction(phone, None)
        replace_warning = f"⚠️ Struk sebelumnya ({old_count} item, {format_rupiah(old_total)}) dibatalkan.\n\n"
    else:
        replace_warning = ""

    # ── PIPELINE: Pre-check (Tesseract) → Gemini structured OCR ──
    result = await extract_items_from_image(media_url, base64_data=base64_data)

    # Pre-check gagal → bukan struk
    if not result["is_receipt"]:
        reason = result["reason"]
        error_messages = {
            "GAMBAR_TIDAK_ADA_TEKS": (
                "❌ Foto ini sepertinya bukan struk/nota.\n\n"
                "Tidak terdeteksi teks pada gambar. Kemungkinan:\n"
                "• Foto gelap atau buram\n"
                "• Foto bukan struk (misal: selfie, pemandangan, screenshot chat)\n\n"
                "📋 *Kirim foto struk/nota yang valid:*\n"
                "• Struk belanja (Alfamart, Indomaret, supermarket)\n"
                "• Nota makan di restoran/warung\n"
                "• Struk SPBU (bensin)\n"
                "• Bukti transfer/QRIS\n"
                "• Invoice belanja online\n\n"
                "💡 *Tips foto yang bagus:*\n"
                "• Pastikan cahaya cukup terang\n"
                "• Foto dari atas, tegak lurus\n"
                "• Semua teks harus terbaca jelas"
            ),
            "BUKAN_STRUK": (
                "❌ Gambar ini bukan struk atau nota belanja.\n\n"
                "Flowku hanya bisa membaca foto struk/nota/bukti transaksi.\n\n"
                "📋 *Yang bisa dibaca:*\n"
                "• Struk minimarket (Alfamart, Indomaret, Circle K)\n"
                "• Nota restoran/warung/kafe\n"
                "• Struk SPBU (Pertamina, Shell, BP)\n"
                "• Bukti pembayaran QRIS/transfer\n"
                "• Invoice e-commerce (Shopee, Tokopedia, dll)\n\n"
                "Ketik *catat 25000 makan* untuk input manual."
            ),
            "GAMBAR_TIDAK_JELAS": (
                "❌ Foto kurang jelas, tidak bisa dibaca.\n\n"
                "💡 *Coba lagi dengan:*\n"
                "• Foto dari atas (bird's eye view)\n"
                "• Pastikan cahaya terang dan tidak ada bayangan\n"
                "• Jangan goyang saat foto\n"
                "• Semua tulisan harus terbaca\n\n"
                "Atau ketik *catat 25000 makan* untuk input manual."
            ),
        }
        msg = error_messages.get(reason, error_messages["GAMBAR_TIDAK_JELAS"])
        return msg

    items = result["items"]
    raw_text = ""
    gemini_tried = False

    if items:
        logger.info(f"Gemini structured OCR: {len(items)} items directly")
        gemini_tried = True
    else:
        # Gemini return None/empty → kemungkinan bukan struk
        gemini_tried = True
        # Fallback: Tesseract text + regex parsing
        raw_text = result.get("reason", "")
        if raw_text:
            logger.info(f"Tesseract fallback: {len(raw_text)} chars")
            items = parse_ocr_items(raw_text, custom_categories=custom_categories)

    if not items:
        # Kalau Gemini sudah coba dan return kosong → bukan struk
        if gemini_tried and not raw_text:
            return (
                "❌ Foto ini bukan struk atau nota belanja.\n\n"
                "Tidak ditemukan item belanja pada gambar.\n\n"
                "📋 *Kirim foto yang valid:*\n"
                "• Struk minimarket (Alfamart, Indomaret)\n"
                "• Nota restoran/warung\n"
                "• Struk SPBU (bensin)\n"
                "• Bukti pembayaran QRIS\n\n"
                "Atau ketik *catat 25000 makan* untuk input manual."
            )
        return (
            "❌ Struk terbaca tapi tidak ditemukan item yang jelas.\n\n"
            "Kemungkinan:\n"
            "• Struk kosong atau tidak lengkap\n"
            "• Format struk tidak umum\n"
            "• Foto terpotong atau terlalu buram\n\n"
            "📋 *Coba:*\n"
            "• Foto ulang dengan lebih jelas\n"
            "• Atau ketik manual: *catat 25000 makan siang*"
        )

    # ── KONFIRMASI DULU SEBELUM SIMPAN ──
    ocr_label = "🤖 AI" if not raw_text else "📸"

    # Simpan ke pending (belum simpan ke transaksi)
    save_pending_transaction(phone, {
        "type": "ocr_items",
        "items": items,
        "raw_text": raw_text or f"[Gemini structured OCR: {len(items)} items]",
    })

    return replace_warning + format_ocr_preview(items, ocr_label)


# ─────────────────────────────────────────────
# WEBHOOK ENDPOINT
# ─────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    """Terima webhook dari WAHA."""
    # Validasi webhook secret header
    secret = request.headers.get("x-webhook-secret")
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = body.get("event", "")
    payload = body.get("payload", {})
    session = body.get("session", "")

    logger.info(f"Webhook: event={event}, session={session}")

    if session != "default":
        return {"status": "ignored", "reason": "wrong session"}

    if event == "message":
        await handle_incoming_message(payload)

    return {"status": "ok"}


async def handle_incoming_message(payload: dict):
    """Proses pesan masuk dari WAHA webhook."""
    if payload.get("fromMe", False):
        return

    # Extract phone - support both legacy (chatId) and GOWS (from/_data) formats
    chat_id = payload.get("chatId", "")
    if chat_id:
        phone = chat_id.replace("@c.us", "").replace("@g.us", "")
    else:
        # GOWS format: _data may be dict or JSON string
        
        _data = payload.get("_data", {})
        if isinstance(_data, str):
            try:
                _data = json.loads(_data)
            except Exception:
                _data = {}
        _info = _data.get("Info", {}) if isinstance(_data, dict) else {}
        sender_alt = _info.get("SenderAlt", "")
        if sender_alt:
            phone = sender_alt
            phone = phone.replace("@s.whatsapp.net", "").replace("@c.us", "")
            phone = phone.split(":")[0]  # strip device suffix
        else:
            # Try Chat field - might be phone@s.whatsapp.net
            chat_raw = _info.get("Chat", "")
            phone = chat_raw.replace("@s.whatsapp.net", "").replace("@c.us", "").replace("@g.us", "")
            if not phone or "@" in phone:
                # Last resort: try from field
                from_raw = payload.get("from", "")
                phone = from_raw.replace("@c.us", "").replace("@s.whatsapp.net", "")
                if "@" in phone:
                    phone = ""

    # Extract type - GOWS may not send type, detect from payload
    msg_type = payload.get("type", "")
    body = payload.get("body", "")
    has_media = payload.get("hasMedia", False)

    if not msg_type:
        if has_media or payload.get("media"):
            msg_type = "image"
        elif body:
            msg_type = "chat"

    logger.info(f"Incoming: type={msg_type}, from={phone}, body={body[:50]}")

    if not phone:
        logger.warning(f"Could not extract phone from payload")
        return

    try:
        if msg_type in ("text", "chat"):
            response = await handle_text_message(phone, body)
            await send_text(phone, response)

        elif msg_type == "image":
            media_url = payload.get("mediaUrl", "")
            base64_data = None

            if not media_url:
                media_raw = payload.get("media", "")
                # GOWS sends media as dict with url/mimetype/base64 fields
                if isinstance(media_raw, dict):
                    logger.info(f"GOWS media dict keys: {list(media_raw.keys())}")
                    media_url = media_raw.get("url", "") or media_raw.get("directDownloadURL", "")
                    if not media_url and media_raw.get("base64"):
                        base64_data = media_raw["base64"]
                        logger.info("Got base64 media from payload.media dict")
                    elif not media_url and media_raw.get("data"):
                        base64_data = media_raw["data"]
                        logger.info("Got base64 data from payload.media dict")
                elif isinstance(media_raw, str) and media_raw:
                    # String — could be URL or base64
                    if media_raw.startswith("http://") or media_raw.startswith("https://"):
                        media_url = media_raw
                    elif media_raw.startswith("data:") or len(media_raw) > 500:
                        base64_data = media_raw
                        logger.info("Got base64 media data string from payload.media")

            if not media_url and not base64_data:
                media_url = payload.get("_data", {}).get("mediaData", {}).get("mediaUrl", "")

            # Also check _data.Message for image message data
            if not media_url and not base64_data:
                _data = payload.get("_data", {})
                if isinstance(_data, str):
                    import json as _json
                    try:
                        _data = _json.loads(_data)
                    except Exception:
                        _data = {}
                msg_data = _data.get("Message", {})
                if isinstance(msg_data, dict):
                    img_msg = msg_data.get("imageMessage", {})
                    if isinstance(img_msg, dict):
                        # GOWS may have directDownloadURL or url
                        media_url = img_msg.get("directDownloadURL", "") or img_msg.get("url", "")
                        if not media_url and img_msg.get("mediaKey"):
                            logger.info("Image has mediaKey but no direct URL — may need WAHA media API")

            logger.info(f"Image processing: media_url={'yes' if media_url else 'no'}, base64={'yes' if base64_data else 'no'}")
            # Quick response sambil tunggu OCR
            await send_text(phone, "📸 Sedang membaca struk...")
            response = await handle_image_message(phone, media_url, base64_data=base64_data)
            await send_text(phone, response)

        else:
            await send_text(phone, "Ketik *bantuan* untuk liat perintah yang tersedia.")

    except Exception as e:
        logger.error(f"Error handling message: {e}", exc_info=True)
        await send_text(phone, "Ada error, coba lagi ya 😅")


# ─────────────────────────────────────────────
# HEALTH & INFO ENDPOINTS
# ─────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "Flowku WhatsApp Chatbot", "status": "running", "version": "1.0.0"}


@app.get("/health")
async def health():
    from waha import check_session
    session = await check_session()

    # Check Firestore connection
    try:
        user = get_user_by_phone(OWNER_PHONE)
        firestore_ok = True
        user_found = user is not None
    except Exception:
        firestore_ok = False
        user_found = False

    return {
        "status": "ok",
        "waha_session": session.get("status", "UNKNOWN"),
        "firestore": "connected" if firestore_ok else "error",
        "user_registered": user_found,
        "owner_phone": OWNER_PHONE or "NOT SET",
        "reminders": f"{REMINDER_HOUR_1}:00 & {REMINDER_HOUR_2}:00 WIB",
    }


@app.post("/test/send")
async def test_send(phone: str, text: str, x_webhook_secret: str = Header(None)):
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    result = await send_text(phone, text)
    return {"sent": result, "to": phone}


@app.post("/test/reminder")
async def test_reminder(x_webhook_secret: str = Header(None)):
    if x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    await cek_dan_kirim_reminder()
    return {"status": "reminder sent"}


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Flowku Chatbot on port {APP_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
