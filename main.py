"""
Flowku WhatsApp Chatbot — Main FastAPI App
Menerima webhook dari WAHA, proses pesan, simpan ke Firestore.
Schema sesuai BACKEND_MIGRATION_GUIDE.md
"""
import logging
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import pytz

from config import APP_PORT, WEBHOOK_SECRET, OWNER_PHONE, REMINDER_HOUR_1, REMINDER_HOUR_2
from parser import parse_catatan, parse_ocr_items, format_rupiah
from firestore_db import (
    catat_transaksi, hitung_total_hari_ini, hitung_total_bulan_ini,
    save_ocr_result, get_budget_status, get_user_by_phone, verify_whatsapp,
)
from waha import send_text
from ocr import extract_text_from_image
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

def format_catatan_msg(saved: dict, catatan: dict, phone: str) -> str:
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
    total = hitung_total_hari_ini(phone)
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

    emojis = {
        "food": "🍔", "transport": "🚗", "shopping": "🛍️", "health": "💊",
        "entertainment": "🎮", "bills": "⚡", "education": "📚", "beauty": "💄",
        "home": "🏠", "investment": "📈", "social": "🎁", "saving": "🎯",
        "other_expense": "📦",
    }

    if by_cat:
        msg += "Pengeluaran per kategori:\n"
        for cat, jumlah in sorted(by_cat.items(), key=lambda x: -x[1]):
            emoji = emojis.get(cat, "•")
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
        "🤖 *Flowku Bot*\n\n"
        "Perintah yang tersedia:\n\n"
        "*Catat Pengeluaran:*\n"
        "  • catat 25000 makan\n"
        "  • 50rb transport grab\n"
        "  • pengeluaran 100000 belanja\n\n"
        "*Catat Pemasukan:*\n"
        "  • pemasukan 500000 gaji\n"
        "  • masuk 200rb jualan\n\n"
        "*Laporan:*\n"
        "  • *hari ini* — ringkasan hari ini\n"
        "  • *bulan ini* — ringkasan bulanan\n\n"
        "*Foto Struk:*\n"
        "  Kirim foto struk, otomatis tercatat\n\n"
        "*Lainnya:*\n"
        "  • *bantuan* — tampilkan menu ini\n"
        "  • *kategori* — daftar kategori\n"
        "  • *anggaran* — cek status anggaran"
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
    emojis = {
        "food": "🍔", "transport": "🚗", "shopping": "🛍️", "health": "💊",
        "entertainment": "🎮", "bills": "⚡", "education": "📚", "beauty": "💄",
        "home": "🏠", "investment": "📈", "social": "🎁", "saving": "🎯",
        "other_expense": "📦",
    }

    for cat, info in budget.items():
        emoji = emojis.get(cat, "•")
        pct = info["percentage"]
        status = "✅" if pct < 80 else "⚠️" if pct < 100 else "🚨"
        msg += (
            f"{status} {emoji} {cat.replace('_', ' ').capitalize()}\n"
            f"   {format_rupiah(info['spent'])} / {format_rupiah(info['limit'])} ({pct}%)\n\n"
        )

    return msg


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
        saved = catat_transaksi(
            user_phone=phone,
            tipe=catatan["type"],
            jumlah=catatan["amount"],
            kategori=catatan["category"],
            keterangan=catatan.get("description", ""),
        )
        if saved:
            return format_catatan_msg(saved, catatan, phone)
        else:
            return "❌ Gagal menyimpan transaksi. Silakan hubungi admin."

    # Unknown command
    return (
        "Hmm, gue ga ngerti pesannya 🤔\n\n"
        "Coba ketik *bantuan* untuk liat perintah yang tersedia.\n\n"
        "Contoh: *catat 25000 makan*"
    )


async def handle_image_message(phone: str, media_url: str) -> str:
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

    if not media_url:
        return "Gagal terima gambar. Coba kirim ulang."

    raw_text = await extract_text_from_image(media_url)

    if not raw_text.strip():
        return (
            "Gagal baca struk 😅\n\n"
            "Tips:\n"
            "• Foto harus jelas & terang\n"
            "• Pastikan teks terbaca\n"
            "• Atau catat manual: *catat 25000 makan*"
        )

    items = parse_ocr_items(raw_text, custom_categories=custom_categories)

    if not items:
        return (
            f"Struk terbaca tapi ga ketemu item yang jelas 😅\n\n"
            f"Teks: {raw_text[:200]}...\n\n"
            f"Coba catat manual: *catat 25000 makan*"
        )

    # Save all items
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

    msg = f"📸 Struk terbaca! {len(saved_items)} item tercatat:\n\n"
    for item in saved_items:
        msg += f"  • {item['nama']}: {format_rupiah(item['harga'])}\n"
    msg += f"\n💸 Total: {format_rupiah(total)}"

    daily = hitung_total_hari_ini(phone)
    msg += f"\n\n📊 Total hari ini: {format_rupiah(daily['pengeluaran'])}"

    return msg


# ─────────────────────────────────────────────
# WEBHOOK ENDPOINT
# ─────────────────────────────────────────────

@app.post("/webhook")
async def webhook(request: Request):
    """Terima webhook dari WAHA."""
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
            if not media_url:
                media_url = payload.get("media", "")
            if not media_url:
                media_url = payload.get("_data", {}).get("mediaData", {}).get("mediaUrl", "")

            response = await handle_image_message(phone, media_url)
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
async def test_send(phone: str, text: str):
    result = await send_text(phone, text)
    return {"sent": result, "to": phone}


@app.post("/test/reminder")
async def test_reminder():
    await cek_dan_kirim_reminder()
    return {"status": "reminder sent"}


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Flowku Chatbot on port {APP_PORT}")
    uvicorn.run(app, host="0.0.0.0", port=APP_PORT)
