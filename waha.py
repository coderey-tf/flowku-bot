"""
WAHA Service — Kirim pesan WhatsApp via WAHA API
"""
import httpx
import logging
from config import WAHA_BASE_URL, WAHA_API_KEY, WAHA_SESSION

logger = logging.getLogger(__name__)

HEADERS = {
    "x-api-key": WAHA_API_KEY,
    "Content-Type": "application/json",
}


async def send_text(phone: str, text: str) -> bool:
    """Kirim pesan teks ke nomor WhatsApp."""
    # Normalize phone (hapus +, spasi, strip)
    phone = phone.replace("+", "").replace(" ", "").replace("-", "")

    # Pastikan format 62xxx
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    elif not phone.startswith("62"):
        phone = "62" + phone

    url = f"{WAHA_BASE_URL}/api/sendText"
    payload = {
        "chatId": f"{phone}@c.us",
        "text": text,
        "session": WAHA_SESSION,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=HEADERS)
            if resp.status_code in (200, 201):
                logger.info(f"Message sent to {phone}")
                return True
            else:
                logger.error(f"Failed to send to {phone}: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Error sending message to {phone}: {e}")
        return False


async def send_image(phone: str, image_url: str, caption: str = "") -> bool:
    """Kirim gambar ke nomor WhatsApp."""
    phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "62" + phone[1:]
    elif not phone.startswith("62"):
        phone = "62" + phone

    url = f"{WAHA_BASE_URL}/api/sendImage"
    payload = {
        "chatId": f"{phone}@c.us",
        "file": {"mimetype": "image/jpeg", "url": image_url},
        "caption": caption,
        "session": WAHA_SESSION,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=HEADERS)
            return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Error sending image to {phone}: {e}")
        return False


async def check_session() -> dict:
    """Cek status WAHA session."""
    url = f"{WAHA_BASE_URL}/api/sessions/{WAHA_SESSION}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=HEADERS)
            if resp.status_code in (200, 201):
                return resp.json()
    except Exception as e:
        logger.error(f"Error checking session: {e}")
    return {"status": "UNKNOWN"}
