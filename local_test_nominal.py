import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from parser import parse_amount, parse_catatan

SEP = '=' * 62

# ─── TEST 1: parse_amount ────────────────────────────────────────
print(SEP)
print('  TEST parse_amount — Semua Format Nominal')
print(SEP)

cases = [
    # (label,       input,         expected)
    ('rb',          '50rb',        50_000),
    ('rb spasi',    '50 rb',       50_000),
    ('k',           '15k',         15_000),
    ('k spasi',     '15 k',        15_000),
    ('ribu',        '25ribu',      25_000),
    ('ribu spasi',  '25 ribu',     25_000),
    ('jt',          '3jt',         3_000_000),
    ('jt spasi',    '3 jt',        3_000_000),
    ('juta',        '2juta',       2_000_000),
    ('juta spasi',  '2 juta',      2_000_000),
    # Desimal
    ('1.5jt',       '1.5jt',       1_500_000),
    ('2,5jt',       '2,5jt',       2_500_000),
    ('1.5juta',     '1.5juta',     1_500_000),
    ('0.5jt',       '0.5jt',         500_000),
    # Plain angka
    ('plain',       '50000',        50_000),
    ('dot-sep',     '50.000',       50_000),
    ('1jt plain',   '1000000',   1_000_000),
    ('1jt dots',    '1.000.000', 1_000_000),
    # rp prefix
    ('rp+angka',    'rp50000',      50_000),
    ('rp+spasi',    'rp 50.000',    50_000),
    ('rp+rb',       'rp50rb',       50_000),
    ('rp+jt',       'rp3jt',     3_000_000),
]

PASS = FAIL = 0
print(f"  {'Format':<14} {'Input':<14} {'Expected':>12} {'Got':>12}  Status")
print('  ' + '-' * 58)
for fmt, text, expected in cases:
    got = parse_amount(text)
    ok = got == expected
    if ok: PASS += 1
    else: FAIL += 1
    status = 'OK' if ok else 'FAIL <---'
    print(f"  {fmt:<14} {text:<14} {expected:>12,} {got:>12,}  {status}")

print()
print(f'  Hasil: {PASS}/{len(cases)} lulus, {FAIL} gagal')
print(SEP)

# ─── TEST 2: parse_catatan (kalimat lengkap) ─────────────────────
print()
print(SEP)
print('  TEST parse_catatan — Format Lengkap Kalimat')
print(SEP)

sentence_cases = [
    # (input,                        type,      amount)
    ('50rb makan siang',             'expense', 50_000),
    ('catat 25000 kopi',             'expense', 25_000),
    ('tagihan wifi 300rb',           'expense', 300_000),
    ('15k parkir motor',             'expense', 15_000),
    ('80rb skincare vitamin c',      'expense', 80_000),
    ('catat 1.5jt laptop accessories','expense',1_500_000),
    ('3jt gaji bulanan',             'income',  3_000_000),
    ('masuk 500rb bonus',            'income',  500_000),
    ('1jt freelance desain',         'income',  1_000_000),
    ('pemasukan 2.5jt gaji',         'income',  2_500_000),
    ('catat rp50.000 makan',         'expense', 50_000),
    ('transfer masuk 200rb mama',    'income',  200_000),
]

PASS2 = FAIL2 = 0
print(f"  {'Input':<33} {'Type':<8} {'Exp':>10}  Status")
print('  ' + '-' * 62)
for text, exp_type, exp_amount in sentence_cases:
    result = parse_catatan(text)
    if result is None:
        ok = False
        got_info = 'None (gagal parse)'
    else:
        ok = result['type'] == exp_type and result['amount'] == exp_amount
        got_info = f"{result['type']}/{result['amount']:,}"
    if ok: PASS2 += 1
    else: FAIL2 += 1
    status = 'OK' if ok else f'FAIL -> {got_info}'
    print(f"  {text:<33} {exp_type:<8} {exp_amount:>10,}  {status}")

print()
print(f'  Hasil: {PASS2}/{len(sentence_cases)} lulus, {FAIL2} gagal')
print(SEP)
