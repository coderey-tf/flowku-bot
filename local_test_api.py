import os
os.environ["TESTING"] = "true"
import unittest.mock as mock
import sys
import io

# Force UTF-8 output agar emoji di respons bot tidak error di Windows CP1252
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Mock all dependencies BEFORE importing main to avoid firebase/firestore/scheduler imports
sys.modules["firestore_db"] = mock.MagicMock()
sys.modules["waha"] = mock.MagicMock()
sys.modules["ocr"] = mock.MagicMock()
sys.modules["reminder"] = mock.MagicMock()
sys.modules["apscheduler"] = mock.MagicMock()
sys.modules["apscheduler.schedulers"] = mock.MagicMock()
sys.modules["apscheduler.schedulers.asyncio"] = mock.MagicMock()

from fastapi.testclient import TestClient
import main
from main import app

# Inisialisasi FastAPI TestClient
client = TestClient(app)

def run_tests():
    print("=== Running Flowku Bot Webhook Tests (Offline & Mocked) ===")
    
    # User mock data
    mock_user_verified = {
        "uid": "user123",
        "waPhone": "6281234567890",
        "waVerified": True,
        "customCategories": [
            {"id": "custom_beauty", "label": "skincare", "type": "expense"}
        ]
    }
    
    mock_user_unverified = {
        "uid": "user123",
        "waPhone": "6281234567890",
        "waVerified": False,
        "customCategories": []
    }

    # Helper untuk mengirim request ke endpoint /webhook
    def send_webhook(body_text: str, phone: str = "6281234567890"):
        payload = {
            "event": "message",
            "session": "default",
            "payload": {
                "id": "msg_id_12345",
                "timestamp": 1690000000,
                "type": "chat",
                "body": body_text,
                "chatId": f"{phone}@c.us",
                "fromMe": False
            }
        }
        headers = {"x-webhook-secret": "flowku-waha-webhook-2026"}
        return client.post("/webhook", json=payload, headers=headers)

    # Mock database queries dan WAHA API
    with mock.patch("main.get_user_by_phone") as mock_get_user, \
         mock.patch("main.verify_whatsapp") as mock_verify_wa, \
         mock.patch("main.catat_transaksi") as mock_catat, \
         mock.patch("main.hitung_total_hari_ini") as mock_hari_ini, \
         mock.patch("main.hitung_total_bulan_ini") as mock_bulan_ini, \
         mock.patch("main.get_budget_status") as mock_budget, \
         mock.patch("main.send_text", new_callable=mock.AsyncMock) as mock_send_text:
         
        # Set default mock return values
        mock_hari_ini.return_value = {"pengeluaran": 25000, "pemasukan": 0, "catatan": []}
        mock_bulan_ini.return_value = {"pengeluaran": 1200000, "pemasukan": 5000000, "catatan": []}
        mock_budget.return_value = {}
        mock_send_text.return_value = True
        
        # Test Case 1: User belum terdaftar
        print("\n[Test 1] User belum terdaftar di Flowku:")
        mock_get_user.return_value = None
        send_webhook("catat 50k makan")
        sent_msg = mock_send_text.call_args[0][1]
        print(f"-> Respons Bot:\n{sent_msg}")
        print("-" * 50)
        
        # Test Case 2: User terdaftar tetapi belum verifikasi
        print("\n[Test 2] User terdaftar tetapi belum verifikasi:")
        mock_get_user.return_value = mock_user_unverified
        send_webhook("catat 50k makan")
        sent_msg = mock_send_text.call_args[0][1]
        print(f"-> Respons Bot:\n{sent_msg}")
        print("-" * 50)
        
        # Test Case 3: Menjalankan perintah "mulai flowku"
        print("\n[Test 3] Pengguna mengirim perintah 'Mulai Flowku' untuk verifikasi:")
        mock_get_user.return_value = mock_user_unverified
        mock_verify_wa.return_value = True
        send_webhook("mulai flowku")
        sent_msg = mock_send_text.call_args[0][1]
        print(f"-> Respons Bot:\n{sent_msg}")
        print("-" * 50)
        
        # Test Case 4: Pengguna terverifikasi mencatat pengeluaran biasa (makan)
        print("\n[Test 4] Pengguna terverifikasi mencatat pengeluaran bawaan ('catat 25000 makan siang'):")
        mock_get_user.return_value = mock_user_verified
        mock_catat.return_value = {
            "txId": "tx_123", "uid": "user123", "coupleId": "solo_user123",
            "type": "expense", "amount": 25000, "category": "food"
        }
        send_webhook("catat 25000 makan siang")
        sent_msg = mock_send_text.call_args[0][1]
        print(f"-> Respons Bot:\n{sent_msg}")
        print("-" * 50)

        # Test Case 5: Pengguna terverifikasi mencatat menggunakan kategori kustom (skincare)
        print("\n[Test 5] Pengguna terverifikasi mencatat kategori kustom ('150rb skincare'):")
        mock_get_user.return_value = mock_user_verified
        mock_catat.return_value = {
            "txId": "tx_456", "uid": "user123", "coupleId": "solo_user123",
            "type": "expense", "amount": 150000, "category": "custom_beauty"
        }
        send_webhook("150rb skincare")
        sent_msg = mock_send_text.call_args[0][1]
        print(f"-> Respons Bot:\n{sent_msg}")
        print("-" * 50)

if __name__ == "__main__":
    run_tests()
