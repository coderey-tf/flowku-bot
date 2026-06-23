import httpx
import json
import sys

def test_webhook():
    url = "http://127.0.0.1:8700/webhook"
    
    # Mock payload dari WAHA (simulasi pesan WhatsApp masuk)
    payload = {
        "event": "message",
        "session": "default",
        "payload": {
            "id": "false_6281234567890@c.us_3EB0C34B8F3C",
            "timestamp": 1690000000,
            "type": "chat",
            "body": "catat 50rb makan siang",
            "from": "6281234567890@c.us",
            "to": "6289999999999@c.us",
            "chatId": "6281234567890@c.us",
            "fromMe": False
        }
    }
    
    print(f"Mengirim mock payload ke {url}...")
    try:
        headers = {
            "Content-Type": "application/json",
            "x-webhook-secret": "flowku-waha-webhook-2026"
        }
        resp = httpx.post(url, json=payload, headers=headers)
        print(f"Response Status: {resp.status_code}")
        print(f"Response Body: {resp.text}")
    except Exception as e:
        print(f"\n❌ Gagal terhubung ke server lokal: {e}")
        print("Pastikan Anda sudah menjalankan server bot terlebih dahulu menggunakan perintah:")
        print("   uvicorn main:app --port 8700 --reload")

if __name__ == "__main__":
    test_webhook()
