"""
Reminder Service — Kirim reminder WhatsApp terjadwal
  - Jam 12:00 WIB: cek pencatatan hari ini
  - Jam 20:00 WIB: cek pencatatan hari ini
  - Cek langganan mau berakhir
"""
import logging
from datetime import datetime
import pytz

from config import OWNER_PHONE
from waha import send_text

logger = logging.getLogger(__name__)
WIB = pytz.timezone("Asia/Jakarta")


async def cek_dan_kirim_reminder():
    """Cek apakah ada transaksi hari ini, kirim reminder kalau belum."""
    from firestore_db import get_verified_users_for_reminder, hitung_total_hari_ini

    now = datetime.now(WIB)
    jam = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")

    users = get_verified_users_for_reminder()
    logger.info(f"Checking reminders for {len(users)} users...")

    for user in users:
        phone = user.get("waPhone")
        if not phone:
            continue

        catatan = hitung_total_hari_ini(phone)
        jumlah = len(catatan["catatan"])

        if jumlah == 0:
            if int(now.strftime("%H")) < 15:
                msg = (
                    f"☀️ Selamat siang!\n\n"
                    f"Kamu belum catat pengeluaran hari ini ({today}).\n\n"
                    f"Ketik contoh:\n"
                    f"• *catat 25000 makan*\n"
                    f"• *50rb transport grab*\n"
                    f"• Atau kirim foto struk\n\n"
                    f"Jangan lupa catat ya! 📝"
                )
            else:
                msg = (
                    f"🌙 Malam!\n\n"
                    f"Hari ini ({today}) belum ada pencatatan sama sekali.\n\n"
                    f"Sebelum tidur, coba catat pengeluaran hari ini:\n"
                    f"• *catat 25000 makan*\n"
                    f"• *100rb belanja*\n"
                    f"• *foto struk*\n\n"
                    f"Catatan kecil = kontrol keuangan besar 💰"
                )

            await send_text(phone, msg)
            logger.info(f"Reminder sent to {phone} at {jam}, no records today")
        else:
            if int(now.strftime("%H")) >= 18:
                p = catatan["pengeluaran"]
                m = catatan["pemasukan"]
                msg = (
                    f"📊 Ringkasan hari ini ({today}):\n\n"
                    f"📝 {jumlah} transaksi\n"
                    f"💸 Pengeluaran: _Rp{p:,.0f}_\n".replace(",", ".")
                )
                if m > 0:
                    msg += f"💰 Pemasukan: _Rp{m:,.0f}_\n".replace(",", ".")
                msg += "\nSelamat istirahat! 😴"

                await send_text(phone, msg)
                logger.info(f"Summary sent to {phone} at {jam}, {jumlah} records today")


async def cek_langganan():
    """Cek apakah langganan user mau berakhir."""
    from google.cloud import firestore
    from config import FIRESTORE_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS

    db = firestore.Client.from_service_account_json(
        GOOGLE_APPLICATION_CREDENTIALS,
        project=FIRESTORE_PROJECT_ID,
    )
    now = datetime.now(WIB)

    docs = db.collection("langganan").where("user_phone", "==", OWNER_PHONE).stream()

    for doc in docs:
        data = doc.to_dict()
        tanggal_berakhir = data.get("tanggal_berakhir", "")
        if not tanggal_berakhir:
            continue

        try:
            berakhir = datetime.strptime(tanggal_berakhir, "%Y-%m-%d")
            berakhir = WIB.localize(berakhir)
            selisih = (berakhir - now).days
            nama = data.get("nama", "Flowku")

            if selisih == 3:
                msg = (
                    f"⚠️ Pengingat Langganan\n\n"
                    f"Langganan *{nama}* akan berakhir "
                    f"pada *{tanggal_berakhir}* (3 hari lagi).\n\n"
                    f"Segera perpanjang agar layanan tidak terputus."
                )
                await send_text(OWNER_PHONE, msg)

            elif selisih == 1:
                msg = (
                    f"🔴 URGENT: Langganan Besok!\n\n"
                    f"Langganan *{nama}* berakhir besok *{tanggal_berakhir}*.\n\n"
                    f"Perpanjang sekarang agar tetap bisa menggunakan layanan."
                )
                await send_text(OWNER_PHONE, msg)

            elif selisih == 0:
                msg = (
                    f"❌ Langganan Hari Ini!\n\n"
                    f"Langganan *{nama}* berakhir hari ini.\n\n"
                    f"Perpanjang sekarang untuk melanjutkan layanan."
                )
                await send_text(OWNER_PHONE, msg)

        except ValueError:
            continue
