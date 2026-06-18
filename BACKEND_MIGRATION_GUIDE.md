# Ringkasan Teknis Flow Backend Flowku & Detail Transaksi

Dokumen ini berisi rangkuman arsitektur backend aplikasi Flowku saat ini yang dibangun di atas ekosistem Firebase, beserta detail spesifik fungsi pencatatan transaksi. Rangkuman ini dibuat untuk mempermudah proses pemisahan backend (migrasi ke backend mandiri/terpisah di masa mendatang).

---

## Bagian 1: Arsitektur Saat Ini (Serverless Firebase)

Saat ini, Flowku beroperasi dengan arsitektur **Serverless** yang mengandalkan:
- **Firebase Auth**: Autentikasi pengguna.
- **Firestore (NoSQL)**: Basis data utama aplikasi.
- **Firebase Cloud Functions**: Menjalankan logika *backend-heavy*, webhooks, *cron jobs*, dan *database triggers*.
- **Firebase Cloud Messaging (FCM)**: Pengiriman *push notification*.
- **Firebase Storage**: Penyimpanan aset.

**Pola Komunikasi (Client-Backend):**
Klien (aplikasi React/Frontend) **langsung berinteraksi dengan Firestore** (baca & tulis) melalui *Firebase Client SDK* (contoh di `src/services/transactionService.js`). Keamanan data saat ini sepenuhnya dijaga oleh **Firestore Security Rules** (`firestore.rules`).

### Struktur Basis Data (Firestore Collections)
1. **`users`**: Profil, status premium (`isPremium`), waPhone, token FCM.
2. **`couples`**: Mode relasi (solo / couple) dengan status `pending`/`active`/`frozen`.
3. **`transactions`**: Data keuangan utama, terikat pada `coupleId` atau `uid`.
4. **`budgets`**: Limit anggaran per kategori per couple.
5. **`goals`**: Target tabungan & kontribusi.
6. **`paymentRequests`**: Permintaan *upgrade* premium.

---

## Bagian 2: Detail Fungsi Pencatatan Transaksi

Berikut adalah isi masing-masing fungsi yang terlibat secara spesifik dalam **alur pencatatan transaksi**. Alur ini mencakup pencatatan dari Aplikasi (Frontend), pencatatan dari Bot WhatsApp, serta *Trigger* yang berjalan otomatis setelah transaksi tersimpan.

### A. Fungsi Pencatatan dari Aplikasi (Frontend)
Saat pengguna menyimpan transaksi lewat aplikasi, fungsi `addTransaction` dipanggil. Fungsi ini langsung menulis ke collection `transactions` menggunakan SDK client.

```javascript
// File: src/services/transactionService.js

export const addTransaction = async (coupleId, userId, data) => {
  const ref = await addDoc(collection(db, "transactions"), {
    coupleId: coupleId,
    uid: userId,           // Standar baru untuk ID pembuat
    userId: userId,        // Untuk backward compatibility
    type: data.type,       // "income" atau "expense"
    amount: data.amount,   // Nominal uang
    category: data.category, // Kategori (food, transport, dll)
    description: data.description || "",
    notes: data.notes || "",
    photoUrl: data.photoUrl || null,
    who: data.who || userId, // Siapa yang mencatat
    date: data.date
      ? Timestamp.fromDate(new Date(data.date))
      : serverTimestamp(),
    source: data.source || "app", // Sumber ("app")
    createdAt: serverTimestamp(),
  });

  // Analytics
  logEvent("transaction_created", { /* ... */ });

  return ref.id; 
};
```

### B. Fungsi Pencatatan dari Bot WhatsApp (Backend)
Saat pengguna chat bot WhatsApp (misal: "Makan siang 50000"), webhook dari WAHA memicu Cloud Function `whatsappWebhook`.

```javascript
// File: functions/index.js (Bagian dari fungsi whatsappWebhook)

// 1. NLP / Parsing Regex untuk menangkap nominal & tipe transaksi dari teks chat
const priceRegex = /(?:rp\.?\s*)?(\d{1,3}(?:[\.,]\d{3})*|\d+)\s*(k|rb|ribu|jt|juta)?/gi;

// 2. Menentukan tipe (income/expense)
let type = 'expense';
const incomeKeywords = ['gaji', 'pemasukan', 'hadiah', 'transfer masuk', 'cair', 'untung'];
if (incomeKeywords.some(kw => description.toLowerCase().includes(kw))) {
  type = 'income';
}

// 3. Menentukan Kategori otomatis
let category = 'other';
if (type === 'expense') {
  const categoryKeywords = {
    food: ['makan', 'minum', 'kopi', 'gofood', 'bakso', 'sate', 'nasi'],
    transport: ['bensin', 'parkir', 'gojek', 'grab', 'tol', 'motor', 'kereta'],
    // ...
  };
}

// 4. Menyimpan data ke Firestore backend-side
const txRef = db.collection('transactions').doc();
const newTx = {
  txId: txRef.id,
  coupleId: coupleId || `solo_${userId}`,
  uid: userId,
  userId: userId,
  uids: uids, // Array yang berisi UID pengguna & UID pasangan
  type,
  amount,
  category,
  description,
  notes: 'Dicatat otomatis via WhatsApp Bot',
  who: userId,
  date: admin.firestore.Timestamp.now(),
  source: 'wa_bot', // Penanda sumber dari Bot
  createdAt: admin.firestore.Timestamp.now(),
  updatedAt: admin.firestore.Timestamp.now()
};

await txRef.set(newTx);
// Lalu mengirim balasan chat ke WhatsApp & Push Notification
```

### C. Fungsi Trigger Pasca-Pencatatan (Backend)
Setiap ada transaksi baru, fungsi otomatis `onTransactionCreated` berjalan untuk mengurus notifikasi dan kalkulasi peringatan anggaran.

```javascript
// File: functions/index.js

exports.onTransactionCreated = onDocumentCreated("transactions/{txId}", async (event) => {
  const txData = event.data.data();
  const uid = txData.uid || txData.userId;
  const { coupleId, type, amount, category, description } = txData;

  // 1. Notifikasi Pribadi (Jika manual dari app)
  if (uid && txData.source !== 'wa_bot') {
    await sendPushNotification(uid, "Transaksi Dicatat!", `...`);
  }

  // 2. Notifikasi ke Pasangan
  if (coupleId && !coupleId.startsWith('solo_')) {
    // ... logic mencari data pasangan
    await sendPushNotification(partnerId, "Transaksi Dicatat Pasangan", `...`);
  }

  // 3. Peringatan Limit Anggaran
  if (type === 'expense' && coupleId) {
    const budgetSnap = await db.collection('budgets').doc(coupleId).get();
    const limit = budgetSnap.data()?.categories?.[category];

    if (limit && limit > 0) {
      // (Query totalSpent bulan ini...)
      if (totalSpentSebelumnya < limit && totalSpentSekarang >= limit) {
         await sendBudgetNotification(coupleId, `🚨 Batas Anggaran Terlampaui`, `...`);
      } else if (totalSpentSebelumnya < limit * 0.8 && totalSpentSekarang >= limit * 0.8) {
         await sendBudgetNotification(coupleId, `⚠️ Peringatan Anggaran`, `...`);
      }
    }
  }
});
```

---

## Panduan untuk Migrasi

Saat memindahkan sistem ke backend relasional/tersendiri (Express/NestJS/Go), alur *event-driven* ini harus diubah menjadi **Endpoint Linier**:

1. Buat endpoint `POST /api/transactions`.
2. Lakukan operasi penyisipan (insert) ke database.
3. Alih-alih mengandalkan *Database Trigger*, panggil langsung *service* notifikasi dan pengecekan anggaran secara *synchronous* atau oper ke *Message Queue* di dalam *controller* setelah insert berhasil. 
4. Ganti penggunaan Firestore Client SDK di frontend dengan pemanggilan HTTP `fetch` atau `axios` ke endpoint tersebut.
