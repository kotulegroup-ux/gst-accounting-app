import sys
import os
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.database import init_db, get_db
from app.reports import get_gstr1_report, get_gstr3b_report, get_party_ledger, export_gstr1_excel
from app.gst_utils import amount_to_words_indian, calculate_item_taxes

def test_gst_utils():
    print("Testing GST utils...")
    words = amount_to_words_indian(125400.50)
    print(f"Amount in words: {words}")
    assert "One Lakh Twenty Five Thousand Four Hundred" in words
    assert "Fifty Paise" in words

    # Test Intra-state tax split
    intra = calculate_item_taxes(10000.0, 18.0, is_interstate_flag=False)
    assert intra["cgst_amount"] == 900.0
    assert intra["sgst_amount"] == 900.0
    assert intra["igst_amount"] == 0.0
    assert intra["total_amount"] == 11800.0

    # Test Inter-state tax split
    inter = calculate_item_taxes(10000.0, 18.0, is_interstate_flag=True)
    assert inter["cgst_amount"] == 0.0
    assert inter["sgst_amount"] == 0.0
    assert inter["igst_amount"] == 1800.0
    assert inter["total_amount"] == 11800.0
    print("GST calculations verified successfully!")

def test_web_flow():
    print("\nTesting Web Application Endpoints...")
    init_db()
    client = TestClient(app)

    # 1. Login page
    r = client.get("/login")
    assert r.status_code == 200
    assert "GST Accounting Portal" in r.text
    print("[OK] Login page loads")

    # 2. Client Login (9876543210 / client123)
    login_data = {"username": "9876543210", "password": "client123"}
    r = client.post("/login", data=login_data, follow_redirects=True)
    assert r.status_code == 200
    assert "Sharma Trading Corporation" in r.text
    print("[OK] Client login successful")

    # 3. View Sales list
    r = client.get("/sales")
    assert r.status_code == 200
    assert "STC/26-27/001" in r.text
    print("[OK] Sales list accessible")

    # 4. View Tax Invoice Print View
    r = client.get("/sales/1/print")
    assert r.status_code == 200
    assert "TAX INVOICE" in r.text
    assert "Industrial Network Routers Pro" in r.text
    assert "Apex Infotech Pvt Ltd" in r.text
    print("[OK] GST Tax Invoice A4 print view verified")

    # 5. View Purchases
    r = client.get("/purchases")
    assert r.status_code == 200
    assert "BES-2026-904" in r.text
    print("[OK] Purchases list verified")

    # 6. View Ledger Statement
    r = client.get("/ledger?party_id=1")
    assert r.status_code == 200
    assert "LEDGER STATEMENT OF ACCOUNT" in r.text
    assert "Apex Infotech Pvt Ltd" in r.text
    print("[OK] Party ledger statement verified")

    # 7. Check GSTR-1 and GSTR-3B Reports
    r = client.get("/reports/gst")
    assert r.status_code == 200
    assert "GSTR-3B Tax Liability & ITC Computation" in r.text
    assert "GSTR-1 Outward Supplies Summary" in r.text
    print("[OK] GSTR-1 & GSTR-3B report center verified")

    # 8. Test Excel Export
    r = client.get("/reports/gst/export-excel")
    assert r.status_code == 200
    assert len(r.content) > 1000
    print(f"[OK] GSTR-1 Excel export generated ({len(r.content)} bytes)")

    # 9. Admin Login
    client.get("/logout")
    r = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=True)
    assert r.status_code == 200
    assert "ADMIN" in r.text
    print("[OK] Master Administrator login verified")

    # 10. Admin Client Management
    r = client.get("/admin/clients")
    assert r.status_code == 200
    assert "Sharma Trading Corporation" in r.text
    print("[OK] Admin client management directory verified")

    # 11. Admin Audit Trail
    r = client.get("/admin/audit-log")
    assert r.status_code == 200
    print("[OK] Admin audit trail verified")

    print("\nALL AUTOMATED TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_gst_utils()
    test_web_flow()
