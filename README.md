# Flowku WhatsApp Chatbot

WhatsApp chatbot for Flowku financial recording app. Receives messages via WAHA (WhatsApp HTTP API), parses transactions, and saves to Firestore.

## Features

- 💸 Catat pengeluaran via teks: `catat 25000 makan`
- 💰 Catat pemasukan: `pemasukan 500000 gaji`
- 📸 OCR foto struk: kirim gambar, otomatis tercatat
- 📊 Laporan harian & bulanan
- ⏰ Reminder otomatis (12:00 & 20:00 WIB)
- 🎯 Auto-detect kategori (food, transport, shopping, dll)

## Architecture

```
WhatsApp User → WAHA (port 3000) → Webhook → FastAPI (port 8700) → Firestore
```

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/YOUR_USERNAME/flowku-bot.git
cd flowku-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your values
```

Required variables:
- `WAHA_BASE_URL` - WAHA API URL (default: http://127.0.0.1:3000)
- `WAHA_API_KEY` - WAHA API key
- `FIRESTORE_PROJECT_ID` - Firebase project ID
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON
- `OWNER_PHONE` - Phone number for reminders (format: 628xxx)

### 3. Setup WAHA

Install WAHA via Docker:
```bash
# See https://waha.devlike.pro/docs/how-to/install/
docker run -it --rm -v ./.sessions:/app/.sessions -p 3000:3000 devlikeapro/waha:gows
```

### 4. Run

```bash
python main.py
```

Or with systemd:
```bash
sudo cp flowku-bot.service /etc/systemd/system/
sudo systemctl enable flowku-bot
sudo systemctl start flowku-bot
```

## Commands (WhatsApp)

| Command | Description |
|---------|-------------|
| `bantuan` | Show help menu |
| `catat 25000 makan` | Record expense |
| `pemasukan 500000 gaji` | Record income |
| `hari ini` | Today's summary |
| `bulan ini` | Monthly summary |
| `anggaran` | Budget status |
| `kategori` | List categories |
| [photo] | OCR receipt |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check |
| `/webhook` | POST | WAHA webhook receiver |
| `/test/send` | POST | Test send message |
| `/test/reminder` | POST | Test reminder |

## Project Structure

```
flowku-bot/
├── main.py            # FastAPI app + webhook handler
├── firestore_db.py    # Firestore CRUD (schema Flowku)
├── parser.py          # Text parser (multi-category)
├── ocr.py             # OCR for receipt photos
├── waha.py            # WAHA API client
├── reminder.py        # Scheduled reminders
├── config.py          # Configuration
├── .env.example       # Environment template
├── requirements.txt   # Python dependencies
└── .gitignore
```

## Schema

Transactions are saved to Firestore `transactions` collection matching Flowku's existing schema (see `BACKEND_MIGRATION_GUIDE.md`).

## License

Private - Flowku Project
