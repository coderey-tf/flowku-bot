import sys
from parser import parse_catatan, parse_amount, detect_category

def test_parser():
    print("=== Testing Flowku Bot Parser ===")
    test_cases = [
        "catat 50rb asdfg",
        "catat 50.000 asdfg",
        "pemasukan 1jt gaji bulanan",
        "catat 25000 makan siang",
        "150rb beli skincare",
        "200rb investasi saham",
        "500rb transfer masuk",
        "catat 10k ojek",
    ]
    
    for text in test_cases:
        res = parse_catatan(text)
        print(f"Input: '{text}'")
        if res:
            print(f"  Parsed -> Type: {res['type']}, Amount: {res['amount']}, Category: {res['category']}, Description: '{res['description']}'")
        else:
            print("  Parsed -> Failed to parse!")
        print("-" * 50)

if __name__ == "__main__":
    test_parser()
