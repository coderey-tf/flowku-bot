# Flowku WhatsApp Chatbot Configuration
import os
from dotenv import load_dotenv

load_dotenv()

# WAHA
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://127.0.0.1:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "d454e5177a8849889c205a891429e4bc")
WAHA_SESSION = os.getenv("WAHA_SESSION", "default")

# Firestore
FIRESTORE_PROJECT_ID = os.getenv("FIRESTORE_PROJECT_ID", "flowku-95fb4")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# App
APP_PORT = int(os.getenv("APP_PORT", "8700"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "flowku-waha-webhook-2026")

# Reminder times (WIB = UTC+7, so 12:00 WIB = 05:00 UTC, 20:00 WIB = 13:00 UTC)
REMINDER_HOUR_1 = 12  # WIB
REMINDER_HOUR_2 = 20  # WIB

# Owner phone (for receiving reminders)
OWNER_PHONE = os.getenv("OWNER_PHONE", "")  # e.g. "6281234567890"

# Categories
CATEGORIES = [
    "makan", "minum", "transport", "belanja", "hiburan",
    "tagihan", "kesehatan", "pendidikan", "lainnya"
]
